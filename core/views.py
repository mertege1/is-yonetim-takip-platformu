from collections import defaultdict
from datetime import date, timedelta, datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Sum, Q, Value, DecimalField, Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Task, RoadmapItem, CustomUser, WorkLog, Notification
from .forms import TaskForm, WorkLogForm, RoadmapEditForm
from .utils import calculate_workload_distribution


# =========================================================
# YETKİLENDİRME (RBAC) YARDIMCI FONKSİYONLARI
# =========================================================
def _user_can_view_task(user, task):
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) == "manager":
        return bool(user.team) and task.assigned_to.team == user.team
    if task.assigned_to_id == user.id:
        return True
    if task.partners.filter(id=user.id).exists():
        return True
    if user.team and task.assigned_to.team == user.team:
        return True
    return False

def _user_can_edit_task(user, task):
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) == "manager":
        return bool(user.team) and task.assigned_to.team == user.team
    if task.created_by_id == user.id:
        return True
    return task.assigned_to_id == user.id or task.partners.filter(id=user.id).exists()

def _user_can_delete_task(user, task):
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) == "manager":
        return bool(user.team) and task.assigned_to.team == user.team
    return task.created_by_id == user.id

def _user_can_toggle_roadmap(user, task):
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) == "manager":
        return bool(user.team) and task.assigned_to.team == user.team
    if task.created_by_id == user.id or task.assigned_to_id == user.id:
        return True
    if task.partners.filter(id=user.id).exists():
        return True
    return False

def _user_can_edit_roadmap(user, task):
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) == "manager":
        return bool(user.team) and task.assigned_to.team == user.team
    if task.created_by_id == user.id or task.partners.filter(id=user.id).exists():
        return True
    return False


# =========================================================
# BİLDİRİM VE E-POSTA YARDIMCI FONKSİYONLARI
# =========================================================
def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"

def _notify(recipients, *, title, message, url="", actor=None, level="info", task=None):
    if not recipients:
        return
    uniq_ids = set()
    objs = []
    for u in recipients:
        if not u or (actor and u.id == actor.id) or u.id in uniq_ids:
            continue
        uniq_ids.add(u.id)
        objs.append(Notification(
            recipient=u, actor=actor, task=task,
            title=title[:160], message=message, url=url, level=level
        ))
    if objs:
        Notification.objects.bulk_create(objs)

def _task_related_users(task):
    users = []
    if getattr(task, "created_by", None):
        users.append(task.created_by)
    if getattr(task, "assigned_to", None):
        users.append(task.assigned_to)
    users.extend(list(task.partners.all()))
    users.extend(list(task.informees.all()))
    
    if getattr(task, "assigned_to", None) and getattr(task.assigned_to, "team", None):
        managers = CustomUser.objects.filter(role="manager", team=task.assigned_to.team)
        users.extend(list(managers))
        
    uniq = {u.id: u for u in users if u and u.id}
    return list(uniq.values())

def _send_task_event_mail(request, task, *, subject, actor, body_lines):
    users = _task_related_users(task)
    actor_id = actor.id if actor else None
    recipient_list = sorted({u.email for u in users if u.email and u.id != actor_id})

    if not recipient_list:
        return

    actor_name = (actor.get_full_name() or actor.username) if actor else "Sistem"
    task_url = request.build_absolute_uri(reverse("task_detail", args=[task.pk]))

    msg = "\n".join([
        "Merhaba,", "",
        f"Görev: {task.title}",
        f"İşlemi yapan: {actor_name}",
        *body_lines, "",
        f"Görev linki: {task_url}",
    ])

    send_mail(
        subject=subject, message=msg,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list, fail_silently=True,
    )


# =========================================================
# ANA YÖNLENDİRİCİLER VE DASHBOARD'LAR
# =========================================================
@login_required
def home(request):
    if request.user.role == "manager":
        return redirect("manager_dashboard")
    return redirect("employee_dashboard")

@login_required
def employee_dashboard(request):
    today = timezone.now().date()
    strategy = request.GET.get("strategy", "balanced")
    date_range = request.GET.get("range", "month")
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    view_start = today
    view_end = today + timedelta(days=29)

    if date_range == "custom" and start_str and end_str:
        try:
            view_start = datetime.strptime(start_str, "%Y-%m-%d").date()
            view_end = datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    elif date_range == "week":
        view_end = view_start + timedelta(days=6)
    elif date_range == "year":
        view_end = view_start + timedelta(days=364)

    if request.GET.get("ajax") == "true":
        chart_data = calculate_workload_distribution(request.user, strategy=strategy, view_start=view_start, view_end=view_end)
        return JsonResponse({"labels": chart_data["labels"], "data": chart_data["data"], "strategy": strategy})

    # Alt sorgu: Kullanıcının ilgili göreve harcadığı kişisel efor toplamını getirir (şişmeyi önler)
    user_contrib_sq = (
        WorkLog.objects
        .filter(task=OuterRef("pk"), user=request.user)
        .values("task")
        .annotate(total=Sum("hours"))
        .values("total")[:1]
    )

    tasks = (
        Task.objects.filter(Q(assigned_to=request.user) | Q(partners=request.user))
        .distinct()
        .annotate(
            user_contribution=Coalesce(
                Subquery(user_contrib_sq, output_field=DecimalField(max_digits=6, decimal_places=2)),
                Value(0, output_field=DecimalField(max_digits=6, decimal_places=2)),
            ),
            total_steps=Count("roadmap", distinct=True),
            completed_steps=Count("roadmap", filter=Q(roadmap__is_completed=True), distinct=True),
        ).order_by("due_date")
    )

    alerts = []
    total_remaining_hours = 0.0
    total_completed_steps_agg = 0

    for task in tasks:
        total_completed_steps_agg += int(task.completed_steps or 0)
        if task.status not in ["tamamlandi", "iptal"]:
            spent = float(task.spent_hours or 0)
            planned = float(task.planned_hours or 0)
            total_remaining_hours += max(0.0, planned - spent)

        if task.status in ["tamamlandi", "iptal"]:
            continue
        if task.due_date < today:
            alerts.append({"task": task, "type": "danger", "msg": "GECİKMİŞ GÖREV!"})
            continue
        if task.status == "baslanmadi" and (task.due_date - today).days <= 2:
            alerts.append({"task": task, "type": "warning", "msg": "VADE YAKLAŞIYOR! (Henüz başlanmadı)"})

    urgent_task = alerts[0]["task"] if alerts else tasks.exclude(status__in=["tamamlandi", "iptal"]).first()

    today_tasks = tasks.filter(start_date__lte=today, due_date__gte=today).exclude(status__in=["tamamlandi", "iptal"])
    modal_key = f"today_modal_shown_{request.user.id}_{today.isoformat()}"
    show_today_modal = False
    if today_tasks.exists() and not request.session.get(modal_key, False):
        show_today_modal = True
        request.session[modal_key] = True

    team_task_groups = []
    if request.user.team:
        team_members = CustomUser.objects.filter(team=request.user.team, role="employee").order_by("first_name", "last_name")
        team_tasks_qs = Task.objects.filter(assigned_to__team=request.user.team).exclude(status__in=["tamamlandi", "iptal"]).select_related("assigned_to").order_by("assigned_to__first_name", "due_date")
        
        grouped = defaultdict(list)
        for t in team_tasks_qs:
            grouped[t.assigned_to_id].append(t)

        for member in team_members:
            m_tasks = grouped.get(member.id, [])
            team_task_groups.append({
                "member": member,
                "tasks": m_tasks,
                "count": len(m_tasks),
                "next_due": min([x.due_date for x in m_tasks], default=None),
                "overdue": sum(1 for x in m_tasks if x.due_date < today),
                "due_soon": sum(1 for x in m_tasks if 0 <= (x.due_date - today).days <= 2),
            })

    chart_data = calculate_workload_distribution(request.user, strategy=strategy, view_start=view_start, view_end=view_end)

    context = {
        "tasks": tasks, "today_tasks": today_tasks, "alerts": alerts, "page_title": "Görevlerim ve Ekip Takibi",
        "chart_labels": chart_data["labels"], "chart_data": chart_data["data"],
        "current_strategy": strategy, "current_range": date_range,
        "start_date_val": view_start.strftime("%Y-%m-%d"), "end_date_val": view_end.strftime("%Y-%m-%d"),
        "today": today, "show_today_modal": show_today_modal, "team_task_groups": team_task_groups,
        "total_remaining_hours": round(total_remaining_hours, 1), "total_completed_steps_agg": total_completed_steps_agg,
        "urgent_task": urgent_task,
    }
    return render(request, "dashboard_employee.html", context)

@login_required
def manager_dashboard(request):
    if request.user.role != "manager":
        return redirect("employee_dashboard")

    team = request.user.team
    if not team:
        messages.error(request, "Yönetici hesabında takım tanımı yok. Admin panelden team seçin.")
        return render(request, "dashboard_manager.html", {
            "page_title": "Ekip Yönetim Paneli", "today": timezone.now().date(),
            "team_task_groups": [], "today_tasks": [], "show_today_modal": False,
            "delayed_tasks": [], "employees": [], "selected_user_id": None,
            "current_strategy": "balanced", "current_range": "month",
            "chart_context": {"type": "aggregate", "labels": [], "planned": [], "spent": []}, "tasks": [],
        })

    today = timezone.now().date()
    selected_user_id = request.GET.get("user_id", "all")
    strategy = request.GET.get("strategy", "balanced")
    date_range = request.GET.get("range", "month")
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    view_start = today
    view_end = today + timedelta(days=29)

    if date_range == "custom" and start_str and end_str:
        try:
            view_start = datetime.strptime(start_str, "%Y-%m-%d").date()
            view_end = datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    elif date_range == "week":
        view_end = view_start + timedelta(days=6)
    elif date_range == "year":
        view_end = view_start + timedelta(days=364)

    employees = CustomUser.objects.filter(team=team).exclude(Q(role="manager") | Q(is_superuser=True)).order_by("first_name", "last_name")

    team_tasks_qs = Task.objects.filter(assigned_to__team=team).exclude(status__in=["tamamlandi", "iptal"]).select_related("assigned_to").prefetch_related("partners").order_by("due_date")
    
    assigned_map = defaultdict(list)
    partner_map = defaultdict(list)
    for t in team_tasks_qs:
        assigned_map[t.assigned_to_id].append(t)
        for p in t.partners.all():
            if getattr(p, "team", None) == team and getattr(p, "role", None) != "manager" and p.id != t.assigned_to_id:
                partner_map[p.id].append(t)

    team_task_groups = []
    for member in employees:
        combined = assigned_map.get(member.id, []) + partner_map.get(member.id, [])
        uniq = {x.id: x for x in combined}
        m_tasks = sorted(uniq.values(), key=lambda x: x.due_date)
        team_task_groups.append({
            "member": member, "tasks": m_tasks, "count": len(m_tasks),
            "next_due": m_tasks[0].due_date if m_tasks else None,
            "overdue": sum(1 for x in m_tasks if x.due_date < today),
            "due_soon": sum(1 for x in m_tasks if 0 <= (x.due_date - today).days <= 2),
        })

    today_tasks = Task.objects.filter(assigned_to__team=team, start_date__lte=today, due_date__gte=today).exclude(status__in=["tamamlandi", "iptal"]).select_related("assigned_to").order_by("due_date")
    modal_key = f"today_team_modal_shown_{request.user.id}_{today.isoformat()}"
    show_today_modal = False
    if today_tasks.exists() and not request.session.get(modal_key, False):
        show_today_modal = True
        request.session[modal_key] = True

    delayed_tasks = Task.objects.filter(assigned_to__team=team).filter(
        (Q(due_date__lt=today) & ~Q(status__in=["tamamlandi", "iptal"])) |
        (Q(status="baslanmadi") & Q(due_date__range=[today, today + timedelta(days=3)]))
    ).select_related("assigned_to").distinct().order_by("due_date")

    def attach_progress(task_list):
        for t in task_list:
            planned = float(t.planned_hours or 0)
            spent = float(t.spent_hours or 0)
            raw = int(round((spent / planned) * 100)) if planned > 0 else 0
            t.progress_pct_raw = raw
            t.progress_pct_bar = max(0, min(raw, 100))

    target_user = None
    tasks_qs = Task.objects.none()

    if selected_user_id and selected_user_id != "all":
        target_user = get_object_or_404(CustomUser, id=selected_user_id, team=team)
        tasks_qs = (
            Task.objects.filter(assigned_to__team=team)
            .filter(Q(assigned_to=target_user) | Q(partners=target_user))
            .distinct().select_related("assigned_to")
            .annotate(
                total_steps=Count("roadmap", distinct=True),
                completed_steps=Count("roadmap", filter=Q(roadmap__is_completed=True), distinct=True),
            ).order_by("due_date")
        )
    else:
        tasks_qs = (
            Task.objects.filter(assigned_to__team=team)
            .select_related("assigned_to")
            .annotate(
                total_steps=Count("roadmap", distinct=True),
                completed_steps=Count("roadmap", filter=Q(roadmap__is_completed=True), distinct=True),
            ).order_by("due_date")
        )

    tasks_list = list(tasks_qs)
    attach_progress(tasks_list)
    
    tasks_active = [t for t in tasks_list if t.status not in ["tamamlandi", "iptal"]]
    active_tasks_count = len(tasks_active)
    total_remaining_hours = sum(max(0.0, float(t.planned_hours or 0) - float(t.spent_hours or 0)) for t in tasks_active)
    total_completed_steps_agg = sum(int(getattr(t, "completed_steps", 0) or 0) for t in tasks_list)

    selection_delayed = sorted([t for t in tasks_active if t.due_date and ((t.due_date < today) or (t.status == "baslanmadi" and 0 <= (t.due_date - today).days <= 3))], key=lambda x: x.due_date)
    urgent_task = selection_delayed[0] if selection_delayed else (sorted(tasks_active, key=lambda x: x.due_date or today)[0] if tasks_active else None)

    def _is_focus_task(t):
        if t.status in ["tamamlandi", "iptal"]: return False
        if t.status == "calisiliyor" or t.priority == "yuksek": return True
        if t.due_date and (t.due_date < today or 0 <= (t.due_date - today).days <= 2): return True
        return False

    focus_tasks_list = [t for t in tasks_list if _is_focus_task(t)]

    if target_user:
        workload = calculate_workload_distribution(target_user, strategy=strategy, view_start=view_start, view_end=view_end, team_filter=team)
        chart_context = {"type": "individual", "labels": workload["labels"], "data": workload["data"], "user": target_user}
        selected_user_id_for_template = int(selected_user_id)
    else:
        employee_names, planned_data, spent_data = [], [], []
        for u in employees:
            user_tasks = Task.objects.filter(Q(assigned_to=u) | Q(partners=u), assigned_to__team=team).distinct()
            u_total_planned = sum((float(t.planned_hours) / (1 + t.partners.count())) for t in user_tasks if t.planned_hours)
            
            u_total_spent = float(WorkLog.objects.filter(task__in=user_tasks, user=u).aggregate(total=Coalesce(Sum("hours"), Value(0, output_field=DecimalField())))["total"] or 0)

            if u_total_planned > 0 or u_total_spent > 0:
                employee_names.append(u.get_full_name() or u.username)
                planned_data.append(round(u_total_planned, 2))
                spent_data.append(round(u_total_spent, 2))

        chart_context = {"type": "aggregate", "labels": employee_names, "planned": planned_data, "spent": spent_data}
        selected_user_id_for_template = None

    if request.GET.get("ajax") == "true":
        table_rows_all_html = render_to_string("partials/manager_tasks_rows.html", {"tasks": tasks_list, "today": today}, request=request)
        table_rows_focus_html = render_to_string("partials/manager_tasks_rows.html", {"tasks": focus_tasks_list, "today": today}, request=request)
        
        kpi_payload = {
            "active_count": active_tasks_count,
            "remaining_hours": round(total_remaining_hours, 1),
            "completed_steps": total_completed_steps_agg,
            "urgent_due": urgent_task.due_date.strftime("%d %b") if urgent_task and urgent_task.due_date else "",
            "urgent_title": urgent_task.title if urgent_task else "",
        }

        if target_user:
            return JsonResponse({
                "mode": "individual", "user_id": str(selected_user_id), "user_name": target_user.get_full_name() or target_user.username,
                "strategy": strategy, "labels": chart_context["labels"], "data": chart_context["data"],
                "table_rows_all_html": table_rows_all_html, "table_rows_focus_html": table_rows_focus_html, "kpi": kpi_payload,
            })
        return JsonResponse({
            "mode": "aggregate", "user_id": "all", "labels": chart_context["labels"], "planned": chart_context.get("planned", []), "spent": chart_context.get("spent", []),
            "table_rows_all_html": table_rows_all_html, "table_rows_focus_html": table_rows_focus_html, "kpi": kpi_payload,
        })

    context = {
        "page_title": "Ekip Yönetim Paneli", "today": today, "team_task_groups": team_task_groups,
        "today_tasks": today_tasks, "show_today_modal": show_today_modal, "delayed_tasks": delayed_tasks,
        "employees": employees, "selected_user_id": selected_user_id_for_template,
        "current_strategy": strategy, "current_range": date_range, "start_date_val": view_start.strftime("%Y-%m-%d"),
        "end_date_val": view_end.strftime("%Y-%m-%d"), "chart_context": chart_context,
        "tasks": tasks_list, "active_tasks_count": active_tasks_count, "total_remaining_hours": round(total_remaining_hours, 1),
        "total_completed_steps_agg": total_completed_steps_agg, "urgent_task": urgent_task, "focus_tasks": focus_tasks_list,
    }
    return render(request, "dashboard_manager.html", context)


# =========================================================
# GÖREV VE YOL HARİTASI İŞLEMLERİ
# =========================================================
@login_required
@require_POST
def roadmap_toggle_complete(request, item_id):
    item = get_object_or_404(RoadmapItem, pk=item_id)
    return roadmap_toggle(request, task_pk=item.task_id, item_pk=item.pk)

@login_required
@require_POST
def roadmap_toggle(request, task_pk, item_pk):
    task = get_object_or_404(Task, pk=task_pk)
    if not _user_can_view_task(request.user, task): return HttpResponseForbidden("Bu görevi görme yetkiniz yok.")
    if not _user_can_toggle_roadmap(request.user, task): return HttpResponseForbidden("Roadmap güncelleme yetkiniz yok.")

    item = get_object_or_404(RoadmapItem, pk=item_pk, task_id=task_pk)
    item.is_completed = not item.is_completed
    item.save(update_fields=["is_completed"])
    
    actor_name = request.user.get_full_name() or request.user.username
    status_text = "tamamladı ✅" if item.is_completed else "geri aldı ⏳"
    
    _send_task_event_mail(
        request, task, subject=f"{actor_name} Adım {item.order}'ü {status_text}: {task.title}",
        actor=request.user, body_lines=[f"Adım: {item.order} - {item.description}"]
    )

    _notify(
        _task_related_users(task), title="Yol haritası güncellendi",
        message=f"{actor_name}, '{task.title}' görevinde Adım {item.order}'ü {status_text}: {item.description}",
        url=reverse("task_detail", args=[task.pk]), actor=request.user, level="info", task=task,
    )
    return redirect("task_detail", pk=task.pk)

@login_required
@require_POST
def roadmap_edit(request, task_pk):
    task = get_object_or_404(Task, pk=task_pk)
    if not _user_can_view_task(request.user, task): return HttpResponseForbidden("Bu görevi görme yetkiniz yok.")
    if not _user_can_edit_roadmap(request.user, task): return HttpResponseForbidden("Yol haritasını düzenleme yetkiniz yok.")

    form = RoadmapEditForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.errors.get("roadmap_text", ["Yol haritası hatalı."])[0])
        return redirect("task_detail", pk=task.pk)

    raw_text = form.cleaned_data["roadmap_text"]
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    existing_by_order = {it.order: it for it in task.roadmap.all().order_by("order")}

    max_order_new = len(lines)
    for idx, line in enumerate(lines, start=1):
        desc, dur = line, None
        if "|" in line:
            left, right = line.split("|", 1)
            desc, right = left.strip(), right.strip()
            if right:
                try: dur = Decimal(right)
                except (InvalidOperation, ValueError): dur = None

        if idx in existing_by_order:
            it = existing_by_order[idx]
            it.description = desc[:300]
            it.estimated_duration = dur
            it.save(update_fields=["description", "estimated_duration"])
        else:
            RoadmapItem.objects.create(task=task, order=idx, description=desc[:300], estimated_duration=dur, is_completed=False)

    task.roadmap.filter(order__gt=max_order_new).delete()

    actor_name = request.user.get_full_name() or request.user.username
    _notify(
        _task_related_users(task), title="Yol haritası düzenlendi",
        message=f"{actor_name}, '{task.title}' görevinde yol haritasını düzenledi.",
        url=reverse("task_detail", args=[task.pk]), actor=request.user, level="info", task=task,
    )

    messages.success(request, "Yol haritası güncellendi.")
    return redirect("task_detail", pk=task.pk)

@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not _user_can_view_task(request.user, task):
        messages.error(request, "Bu görevi görüntüleme yetkiniz yok.")
        return redirect("home")

    today = timezone.now().date()

    if request.method == "POST" and "worklog_submit" in request.POST:
        if task.assigned_to == request.user or task.partners.filter(id=request.user.id).exists():
            log_form = WorkLogForm(request.POST)
            if log_form.is_valid():
                work_log = log_form.save(commit=False)
                work_log.task = task
                work_log.user = request.user
                work_log.save()

                task.spent_hours = WorkLog.objects.filter(task=task).aggregate(total=Sum("hours")).get("total") or 0
                task.save(update_fields=["spent_hours"])

                actor_name = request.user.get_full_name() or request.user.username
                _send_task_event_mail(
                    request, task, subject=f"{actor_name} {work_log.hours} saat efor girdi: {task.title}",
                    actor=request.user, body_lines=[f"Tarih: {work_log.date}", f"Süre: {work_log.hours} saat", f"Açıklama: {work_log.description}"]
                )

                _notify(
                    _task_related_users(task), title="Efor girişi yapıldı",
                    message=f"{actor_name}, '{task.title}' için {work_log.hours} saat efor girdi.",
                    url=reverse("task_detail", args=[task.pk]), actor=request.user, level="info", task=task
                )
                messages.success(request, "Çalışma kaydınız başarıyla eklendi.")
                return redirect("task_detail", pk=task.pk)
            messages.error(request, "Efor kaydı hatalı. Lütfen alanları kontrol edin.")
            return redirect("task_detail", pk=task.pk)
        messages.error(request, "Bu göreve efor girme yetkiniz yok.")
        return redirect("task_detail", pk=task.pk)

    log_form = WorkLogForm(initial={"date": today})
    work_logs = task.work_logs.all().select_related("user").order_by("-date", "-created_at")

    total_steps_real = task.roadmap.count()
    completed_steps_count = task.roadmap.filter(is_completed=True).count()
    total_spent_float = float(task.spent_hours or 0)

    contrib_qs = (
        WorkLog.objects.filter(task=task)
        .values("user_id", "user__first_name", "user__last_name", "user__username")
        .annotate(total=Coalesce(Sum("hours"), Value(0, output_field=DecimalField(max_digits=8, decimal_places=2))))
        .order_by("-total")
    )

    contribution_rows = []
    for r in contrib_qs:
        hrs = float(r["total"] or 0)
        pct = (hrs / total_spent_float * 100.0) if total_spent_float > 0 else 0.0
        contribution_rows.append({
            "user_id": r["user_id"],
            "name": (f'{r["user__first_name"]} {r["user__last_name"]}').strip() or r["user__username"],
            "hours": round(hrs, 2), "pct": round(pct, 1),
        })

    context = {
        "task": task, "page_title": f"Görev Detayı: {task.title}", "today": today,
        "log_form": log_form, "work_logs": work_logs,
        "can_toggle_roadmap": _user_can_toggle_roadmap(request.user, task),
        "can_edit_roadmap": _user_can_edit_roadmap(request.user, task),
        "total_steps_count": total_steps_real if total_steps_real > 0 else 1,
        "total_steps_real": total_steps_real, "completed_steps_count": completed_steps_count,
        "contribution_rows": contribution_rows, "total_spent": round(total_spent_float, 2),
    }
    return render(request, "task_detail.html", context)

@login_required
def create_task(request):
    if request.method == "POST":
        form = TaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            if request.user.role == "employee":
                task.assigned_to = request.user
            task.save()
            form.save_m2m()

            roadmap_text = form.cleaned_data.get("roadmap_summary")
            if roadmap_text:
                for i, step in enumerate(roadmap_text.split("\n"), 1):
                    if step.strip(): RoadmapItem.objects.create(task=task, order=i, description=step.strip())

            emails = [u.email for u in _task_related_users(task) if u.email]
            if emails:
                send_mail(
                    f"Yeni Görev: {task.title}", f"Merhaba, '{task.title}' başlıklı görevde isminiz geçmektedir.",
                    settings.DEFAULT_FROM_EMAIL, emails, fail_silently=True,
                )

            actor_name = request.user.get_full_name() or request.user.username
            _notify(
                _task_related_users(task), title="Yeni görev atandı 🚀",
                message=f"{actor_name}, '{task.title}' görevini oluşturdu.",
                url=reverse("task_detail", args=[task.pk]), actor=request.user, level="success", task=task
            )
            messages.success(request, "Görev başarıyla oluşturuldu!")
            return redirect("home")
    else:
        form = TaskForm(user=request.user)
    return render(request, "task_form.html", {"form": form, "page_title": "Yeni Görev Oluştur"})

@login_required
def update_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not _user_can_edit_task(request.user, task):
        messages.error(request, "Bu görevi düzenleme yetkiniz yok!")
        return redirect("home")

    if request.method == "POST":
        old_roadmap_text = "\n".join([item.description for item in task.roadmap.all().order_by('order')]).strip()
        form = TaskForm(request.POST, instance=task, user=request.user)
        
        if form.is_valid():
            changed_fields = [f for f in form.changed_data if f != 'roadmap_summary']
            new_roadmap_text = form.cleaned_data.get("roadmap_summary", "").strip()
            
            # Yol haritası değişikliklerini manuel kontrol ile tespit et
            if old_roadmap_text.replace('\r', '') != new_roadmap_text.replace('\r', ''):
                changed_fields.append('roadmap')

            task = form.save()

            if 'roadmap' in changed_fields:
                task.roadmap.all().delete()
                for i, step in enumerate(new_roadmap_text.split("\n"), 1):
                    if step.strip(): RoadmapItem.objects.create(task=task, order=i, description=step.strip())

            if changed_fields:
                field_labels = {'title': 'Başlık', 'description': 'Açıklama', 'status': 'Durum', 'priority': 'Öncelik', 'due_date': 'Bitiş Tarihi', 'start_date': 'Başlangıç Tarihi', 'assigned_to': 'Atanan Kişi', 'partners': 'Ortaklar', 'size': 'İş Büyüklüğü', 'roadmap': 'Yol Haritası'}
                changes_txt = ", ".join([field_labels.get(f, f) for f in changed_fields])
                msg = f"Değişenler: {changes_txt}"
            else:
                msg = "Detaylar güncellendi."

            actor_name = request.user.get_full_name() or request.user.username
            _notify(
                _task_related_users(task), title="Görev güncellendi 📝",
                message=f"{actor_name}, '{task.title}' görevini güncelledi. {msg}",
                url=reverse("task_detail", args=[task.pk]), actor=request.user, level="warning", task=task
            )
            messages.success(request, "Görev başarıyla güncellendi.")
            return redirect("task_detail", pk=task.pk)
    else:
        initial_roadmap = "".join([f"{item.description}\n" for item in task.roadmap.all()])
        form = TaskForm(instance=task, user=request.user, initial={"roadmap_summary": initial_roadmap})
    return render(request, "task_form.html", {"form": form, "page_title": "Görevi Düzenle"})

@login_required
def delete_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if _user_can_delete_task(request.user, task):
        actor_name = request.user.get_full_name() or request.user.username
        _notify(
            _task_related_users(task), title="Görev Silindi 🗑️",
            message=f"'{task.title}' görevi, {actor_name} tarafından silindi.",
            url="", actor=request.user, level="danger", task=None
        )
        task.delete()
        messages.success(request, "Görev başarıyla silindi ve ilgililere bildirildi.")
    else:
        messages.error(request, "Bu görevi silme yetkiniz bulunmamaktadır.")
    return redirect("home")

@login_required
def task_history(request):
    current_year = timezone.now().year
    try: selected_year = int(request.GET.get('year', current_year))
    except ValueError: selected_year = current_year

    if request.user.role == 'manager' and request.user.team:
        tasks = Task.objects.filter(assigned_to__team=request.user.team)
    else:
        tasks = Task.objects.filter(Q(assigned_to=request.user) | Q(partners=request.user))
    
    tasks = tasks.filter(due_date__year=selected_year).distinct().order_by('-due_date')

    total_count = tasks.count()
    completed_count = tasks.filter(status='tamamlandi').count()
    total_spent = tasks.aggregate(Sum('spent_hours'))['spent_hours__sum'] or 0

    context = {
        'page_title': 'Görev Geçmişi ve Arşiv', 'tasks': tasks, 'selected_year': selected_year,
        'years': range(current_year, current_year - 5, -1),
        'stats': {'total': total_count, 'completed': completed_count, 'spent': round(total_spent, 1), 'ratio': int((completed_count/total_count)*100) if total_count > 0 else 0}
    }
    return render(request, 'task_history.html', context)


# =========================================================
# EFOR (WORKLOG) İŞLEMLERİ (DÜZENLEME VE SİLME)
# =========================================================
@login_required
def edit_worklog(request, pk):
    log = get_object_or_404(WorkLog, pk=pk)
    task = log.task
    
    if log.user != request.user and getattr(request.user, "role", None) != "manager":
        messages.error(request, "Bu efor kaydını düzenleme yetkiniz yok.")
        return redirect("task_detail", pk=task.pk)

    if request.method == "POST":
        old_hours = log.hours 
        form = WorkLogForm(request.POST, instance=log)
        
        if form.is_valid():
            work_log = form.save()
            task.spent_hours = WorkLog.objects.filter(task=task).aggregate(total=Sum("hours"))["total"] or 0
            task.save(update_fields=["spent_hours"])
            
            actor_name = request.user.get_full_name() or request.user.username
            
            # E-posta Bildirimi
            _send_task_event_mail(
                request, task, subject=f"{actor_name} efor kaydını güncelledi: {task.title}",
                actor=request.user, body_lines=[f"Eski Süre: {old_hours} saat", f"Yeni Süre: {work_log.hours} saat", f"Açıklama: {work_log.description}"]
            )

            # Sistem İçi Bildirim
            _notify(
                _task_related_users(task), title="Efor kaydı güncellendi",
                message=f"{actor_name}, '{task.title}' için girdiği eforu {old_hours} saatten {work_log.hours} saate güncelledi.",
                url=reverse("task_detail", args=[task.pk]), actor=request.user, level="warning", task=task,
            )

            messages.success(request, "Efor kaydı başarıyla güncellendi.")
            return redirect("task_detail", pk=task.pk)
    else:
        form = WorkLogForm(instance=log)

    return render(request, "worklog_form.html", {"form": form, "task": task, "page_title": "Efor Kaydını Düzenle"})

@login_required
@require_POST
def delete_worklog(request, pk):
    log = get_object_or_404(WorkLog, pk=pk)
    task = log.task
    
    if log.user != request.user and getattr(request.user, "role", None) != "manager":
        messages.error(request, "Bu efor kaydını silme yetkiniz yok.")
        return redirect("task_detail", pk=task.pk)
        
    deleted_hours = log.hours 
    log.delete()
    
    task.spent_hours = WorkLog.objects.filter(task=task).aggregate(total=Sum("hours"))["total"] or 0
    task.save(update_fields=["spent_hours"])
    
    actor_name = request.user.get_full_name() or request.user.username
    
    # E-posta Bildirimi
    _send_task_event_mail(
        request, task, subject=f"{actor_name} efor kaydını sildi: {task.title}",
        actor=request.user, body_lines=[f"Silinen Süre: {deleted_hours} saat", "İlgili efor kaydı sistemden tamamen kaldırılmıştır."]
    )

    # Sistem İçi Bildirim
    _notify(
        _task_related_users(task), title="Efor kaydı silindi",
        message=f"{actor_name}, '{task.title}' görevine ait {deleted_hours} saatlik efor kaydını sildi.",
        url=reverse("task_detail", args=[task.pk]), actor=request.user, level="danger", task=task,
    )
    
    messages.success(request, "Efor kaydı başarıyla silindi.")
    return redirect("task_detail", pk=task.pk)


# =========================================================
# BİLDİRİM (INBOX) API VE ENDPOINT'LERİ
# =========================================================
@login_required
def notifications_inbox(request):
    qs = Notification.objects.filter(recipient=request.user).select_related("actor", "task").order_by("-created_at")
    return render(request, "notifications/inbox.html", {"page_title": "Bildirim Merkezi", "notifications": qs[:200], "unread_count": qs.filter(is_read=False).count()})

@login_required
def notifications_unread_count(request):
    return JsonResponse({"unread": Notification.objects.filter(recipient=request.user, is_read=False).count()})

@login_required
@require_POST
def notification_mark_read(request, pk):
    n = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not n.is_read:
        n.is_read = True
        n.save(update_fields=["is_read"])
    return JsonResponse({"ok": True}) if _is_ajax(request) else redirect("notifications_inbox")

@login_required
@require_POST
def notifications_mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"ok": True}) if _is_ajax(request) else redirect("notifications_inbox")

@login_required
@require_POST
def notifications_delete_all(request):
    Notification.objects.filter(recipient=request.user).delete()
    return JsonResponse({"ok": True}) if _is_ajax(request) else redirect("notifications_inbox")

@login_required
@require_POST
def notification_delete(request, pk):
    get_object_or_404(Notification, pk=pk, recipient=request.user).delete()
    return JsonResponse({"ok": True}) if _is_ajax(request) else redirect("notifications_inbox")

@login_required
@require_POST
def notifications_delete_read(request):
    Notification.objects.filter(recipient=request.user, is_read=True).delete()
    return JsonResponse({"ok": True}) if _is_ajax(request) else redirect("notifications_inbox")

@login_required
@require_GET
def notifications_latest_api(request):
    limit = max(1, min(int(request.GET.get("limit", "5") if request.GET.get("limit", "5").isdigit() else 5), 20))
    qs = Notification.objects.filter(recipient=request.user).select_related("actor", "task").order_by("-created_at")[:limit]
    
    items = [{
        "id": n.id, "title": n.title, "message": (n.message or "")[:140],
        "url": n.url or (reverse("task_detail", args=[n.task_id]) if n.task_id else ""),
        "is_read": n.is_read, "level": n.level,
        "created_at": timezone.localtime(n.created_at).isoformat(),
        "created_at_display": timezone.localtime(n.created_at).strftime("%d %b %Y %H:%M"),
        "actor": (n.actor.get_full_name() or n.actor.username) if n.actor else "",
    } for n in qs]
    return JsonResponse({"items": items})