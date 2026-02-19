from datetime import date, timedelta
from collections import defaultdict
from django.db.models import Q
from .models import Task

def calculate_workload_distribution(user, strategy='balanced', view_start=None, view_end=None, team_filter=None):
    """
    Belirli bir kullanıcının zaman çizelgesindeki tahmini iş yükü dağılımını hesaplar.
    Görevlerin öncelik, büyüklük veya vade (deadline) parametrelerine göre farklı 
    matematiksel ağırlıklandırma (weighting) algoritmaları uygular.
    
    Args:
        user (CustomUser): İş yükü hesaplanacak kullanıcı.
        strategy (str): Dağılım stratejisi ('balanced', 'priority_weighted', 'size_weighted', 'deadline_weighted').
        view_start (date, optional): Analiz başlangıç tarihi. Varsayılan: Bugün.
        view_end (date, optional): Analiz bitiş tarihi. Varsayılan: Bugünden 14 gün sonrası.
        team_filter (str, optional): Yönetici görünümleri için takım bazlı queryset filtresi.
        
    Returns:
        dict: Grafik render süreçleri (Chart.js vb.) için formatlanmış 'labels', 'data' ve 'strategy' sözlüğü.
    """
    
    base_query = Q(assigned_to=user) | Q(partners=user)
    tasks = Task.objects.filter(base_query).distinct()

    if team_filter:
        tasks = tasks.filter(assigned_to__team=team_filter)
    
    tasks = tasks.filter(status__in=['baslanmadi', 'calisiliyor', 'duraklatildi'])
    
    today = date.today()
    view_start = view_start or today
    view_end = view_end or (view_start + timedelta(days=14))

    daily_workload = defaultdict(float)

    for task in tasks:
        total_remaining = float(task.planned_hours) - float(task.spent_hours)
        if total_remaining <= 0:
            continue
            
        # Görev yükünü, sorumlu ve ortakların sayısına eşit böler (Çift efor sayımını engeller)
        person_count = 1 + task.partners.count()
        my_share = total_remaining / person_count

        effective_start = max(task.start_date, today) 
        
        # Gecikmiş görevlerin kalan tüm eforu, simülasyonda bugünün yükü olarak kabul edilir
        if task.due_date < effective_start:
            daily_workload[today] += my_share
            continue

        days_total = (task.due_date - effective_start).days + 1
        
        if days_total <= 0:
            daily_workload[today] += my_share
            continue

        # Stratejiye uygun dağılım matrisinin oluşturulması
        if strategy == 'priority_weighted':
            distribution = _algo_priority(my_share, days_total, task.priority)
        elif strategy == 'size_weighted':
            distribution = _algo_size(my_share, days_total, task.size)
        elif strategy == 'deadline_weighted':
            distribution = _algo_deadline(my_share, days_total)
        else:
            distribution = [my_share / days_total] * days_total

        # Hesaplanmış matrisi analiz takvimine (view aralığına) işler
        for i, hours in enumerate(distribution):
            current_day = effective_start + timedelta(days=i)
            
            if view_start <= current_day <= view_end:
                daily_workload[current_day] += hours

    # Güvenlik ve performans için analiz limitlerini sabitleme
    delta = max(1, min((view_end - view_start).days + 1, 366))
    
    labels = []
    data = []
    
    for i in range(delta):
        day = view_start + timedelta(days=i)
        labels.append(day.strftime("%d %b"))
        data.append(round(daily_workload.get(day, 0), 2))
        
    return {'labels': labels, 'data': data, 'strategy': strategy}


def _algo_priority(hours, days, priority):
    """
    Öncelik (Priority) parametresine göre iş yükünü lineer olarak kaydırır.
    Yüksek öncelik: İlk günlere yığılım. Düşük öncelik: Son günlere yığılım.
    """
    if days == 1: 
        return [hours]

    if priority == 'yuksek':
        weights = [days - i for i in range(days)]
    elif priority == 'dusuk':
        weights = [i + 1 for i in range(days)]
    else: 
        weights = [1] * days

    total_w = sum(weights)
    return [(w / total_w) * hours for w in weights]


def _algo_size(hours, days, size):
    """
    İş büyüklüğüne (Size) göre efor eylemsizliğini (inertia) hesaplar.
    Büyük işler (4-5), sürecin ilk %33'lük diliminde analiz/kurulum nedeniyle %50 daha fazla efor gerektirir.
    """
    if days == 1: 
        return [hours]

    if size >= 4:
        weights = [1.5 if i < days/3.0 else 1.0 for i in range(days)]
    else:
        weights = [1.0] * days

    total_w = sum(weights)
    return [(w / total_w) * hours for w in weights]


def _algo_deadline(hours, days):
    """
    Üstel (Exponential) büyüme formülü (x^1.5) uygulayarak "Öğrenci Sendromu / Deadline Crunch" simülasyonu yapar.
    Teslim tarihine yaklaştıkça harcanan günlük mesai artar.
    """
    if days == 1: 
        return [hours]
    
    weights = [(i + 1)**1.5 for i in range(days)]
    total_w = sum(weights)
    return [(w / total_w) * hours for w in weights]