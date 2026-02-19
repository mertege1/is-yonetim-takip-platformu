from django import forms
from django.core.exceptions import ValidationError
from datetime import date
from decimal import Decimal, InvalidOperation

from .models import Task, CustomUser, WorkLog

class TaskForm(forms.ModelForm):
    """
    Görev oluşturma ve düzenleme formudur.
    Rol bazlı yetkilendirme (RBAC) kuralları __init__ metodunda queryset seviyesinde uygulanmıştır.
    """
    roadmap_summary = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 20,
                "placeholder": (
                    "1) Analiz | 2.0\n"
                    "2) Tasarım | 3.0\n"
                    "3) Geliştirme | 8.0\n"
                    "...\n"
                    "Yol haritası adımlarını detaylı ve anlaşılır biçimde giriniz."
                ),
            }
        ),
        required=True,
        label="Yol Haritası (En az 20 satır)",
        help_text="Her satır bir adım olmalı. İstersen 'Açıklama | 2.5' şeklinde tahmini süre yazabilirsin.",
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "priority",
            "status",
            "size",
            "assigned_to",
            "partners",
            "informees",
            "start_date",
            "due_date",
            "planned_hours",
            "spent_hours",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Görevin kısa başlığı"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Detaylı açıklama..."}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "size": forms.Select(attrs={"class": "form-select"}),
            "assigned_to": forms.Select(attrs={"class": "form-select"}),
            "partners": forms.SelectMultiple(attrs={"class": "form-select", "size": "6"}),
            "informees": forms.SelectMultiple(attrs={"class": "form-select", "size": "4"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "planned_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.5", "min": "0.5"}),
            "spent_hours": forms.NumberInput(attrs={"class": "form-control bg-light", "step": "0.1", "readonly": "readonly"}),
        }
        labels = {
            "title": "İş Tanımı*",
            "priority": "Öncelik*",
            "status": "İşin Durumu*",
            "size": "İş Büyüklüğü* (1-5)",
            "assigned_to": "Çalışan*",
            "partners": "İş Ortakları (max 5)",
            "informees": "Bilgilendirilecek Kişiler",
            "start_date": "Başlangıç Tarihi*",
            "due_date": "Tamamlanma Tarihi*",
            "planned_hours": "Planlanan İşçilik Süresi* (Adam×Saat)",
            "spent_hours": "Harcanan İşçilik Süresi (Otomatik / Adam×Saat)",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Harcanan efor sadece Worklog üzerinden hesaplanmalıdır
        self.fields["spent_hours"].required = False
        self.fields["spent_hours"].disabled = True

        def user_label(u: CustomUser):
            name = (u.get_full_name() or u.username or "").strip()
            sicil = (u.title or "-").strip()
            return f"{name} — {sicil}"

        for fname in ("assigned_to", "partners", "informees"):
            if fname in self.fields:
                self.fields[fname].label_from_instance = user_label

        # Rol ve Ekip bazlı QuerySet filtrelemeleri
        if self.user and self.user.team:
            team_users = CustomUser.objects.filter(team=self.user.team)
            self.fields["informees"].queryset = team_users
            self.fields["partners"].queryset = team_users.filter(role="employee")

        if self.user and self.user.role == "employee":
            self.fields["assigned_to"].queryset = CustomUser.objects.filter(id=self.user.id)
            if not self.instance.pk:
                self.fields["assigned_to"].initial = self.user
            
            self.fields["assigned_to"].disabled = True

            if self.user.team:
                self.fields["partners"].queryset = (
                    CustomUser.objects.filter(team=self.user.team, role="employee")
                    .exclude(id=self.user.id)
                )

        if self.user and self.user.role == "manager" and self.user.team:
            team_users = CustomUser.objects.filter(team=self.user.team)
            self.fields["assigned_to"].queryset = team_users.filter(role="employee")
            self.fields["partners"].queryset = team_users.filter(role="employee")
            self.fields["informees"].queryset = team_users

        # Partner (iş ortağı) sadece kendi adımını/eforunu yönetebilir, ana metrikleri değiştiremez
        if self.instance.pk and self.user:
            is_manager = (self.user.role == 'manager')
            is_assigned_user = (self.instance.assigned_to_id == self.user.id)
            is_partner = self.instance.partners.filter(id=self.user.id).exists()

            if is_partner and not is_assigned_user and not is_manager:
                readonly_fields = [
                    'title', 'description', 'priority', 'status', 'size', 
                    'assigned_to', 'partners', 'informees', 'start_date', 
                    'due_date', 'planned_hours', 'roadmap_summary'
                ]
                for field_name in readonly_fields:
                    if field_name in self.fields:
                        self.fields[field_name].disabled = True
                        self.fields[field_name].required = False

    def clean_partners(self):
        partners = self.cleaned_data.get("partners")
        assigned_to = self.cleaned_data.get("assigned_to") or getattr(self.instance, "assigned_to", None)

        if partners and partners.count() > 5:
            raise ValidationError("En fazla 5 iş ortağı seçebilirsiniz.")

        if assigned_to and partners and partners.exclude(team=assigned_to.team).exists():
            raise ValidationError("İş ortakları, görevin atandığı kişiyle aynı ekipten olmalıdır.")

        if assigned_to and partners and partners.filter(id=assigned_to.id).exists():
            raise ValidationError("Atanan çalışan, iş ortağı listesinde olamaz.")

        return partners

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        due_date = cleaned.get("due_date")

        if start_date and due_date and due_date < start_date:
            self.add_error("due_date", "Tamamlanma tarihi, başlangıç tarihinden önce olamaz.")

        if "roadmap_summary" in self.fields and not self.fields["roadmap_summary"].disabled:
            roadmap_text = (cleaned.get("roadmap_summary") or "").strip()
            lines = [ln.strip() for ln in roadmap_text.splitlines() if ln.strip()]
            if len(lines) < 1:
                self.add_error("roadmap_summary", "Yol haritası boş bırakılamaz.")

        return cleaned

class WorkLogForm(forms.ModelForm):
    """
    Kişisel efor (harcanan zaman) girişlerinin yapıldığı formdur.
    Tarih validasyonları aracılığıyla geleceğe dönük efor girilmesi engellenmiştir.
    """
    class Meta:
        model = WorkLog
        fields = ["hours", "date", "description"]
        widgets = {
            "hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.1",
                    "placeholder": "Örn: 2.5",
                    "min": "0.1",
                    "required": "true",
                }
            ),
            "date": forms.DateInput(
                attrs={"class": "form-control", "type": "date", "required": "true"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Bugün bu iş için neler yaptınız?",
                    "required": "true",
                }
            ),
        }
        labels = {
            "hours": "Çalışılan Süre (Saat)",
            "date": "Çalışma Tarihi",
            "description": "İş Açıklaması",
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].widget.attrs['max'] = date.today().strftime('%Y-%m-%d')
        
    def clean_date(self):
        date_val = self.cleaned_data.get('date')
        if date_val and date_val > date.today():
            raise forms.ValidationError("Gelecek bir tarihe efor kaydı giremezsiniz.")
        return date_val     
        
class RoadmapEditForm(forms.Form):
    """
    Yol haritası (Roadmap) adımlarının toplu halde Textarea üzerinden güncellenmesini sağlayan formdur.
    """
    roadmap_text = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 20,
                "placeholder": (
                    "1) Analiz | 2.0\n"
                    "2) Tasarım | 3.0\n"
                    "3) Geliştirme | 8.0\n"
                    "...\n"
                    "(En az 20 satır. Süre opsiyonel: Açıklama | 2.5)"
                ),
            }
        ),
        label="Yol Haritası (En az 20 satır)",
        help_text="Her satır bir adım olmalı. İstersen 'Açıklama | 2.5' şeklinde tahmini süre yazabilirsin.",
    )

    def clean_roadmap_text(self):
        text = (self.cleaned_data.get("roadmap_text") or "").strip()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) < 1:
            raise ValidationError("Yol haritası boş bırakılamaz.")
        return text