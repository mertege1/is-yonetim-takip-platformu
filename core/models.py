from django.db import models
from django.contrib.auth.models import AbstractUser
from datetime import date
from django.utils import timezone


class CustomUser(AbstractUser):
    """
    Sisteme giriş yapacak kullanıcıların rol, unvan ve ekip atamalarını 
    tutan genişletilmiş özel kullanıcı modeli.
    """
    ROLE_CHOICES = (
        ('employee', 'Çalışan'),
        ('manager', 'Ekip Yöneticisi'),
    )
    
    TEAM_CHOICES = (
        ('team1', 'Yazılım Geliştirme Ekibi'),
        ('team2', 'Test ve Kalite Ekibi'),
        ('team3', 'DevOps Ekibi'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee', verbose_name='Rolü')
    title = models.CharField(max_length=100, verbose_name='Unvan / Sicil Bilgisi', blank=True)
    team = models.CharField(max_length=50, choices=TEAM_CHOICES, verbose_name='Ekip', blank=True, null=True)

    class Meta:
        verbose_name = 'Kullanıcı'
        verbose_name_plural = 'Kullanıcılar'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.username})"


class Task(models.Model):
    """
    Sistemdeki temel görev/iş birimi. 
    İşin durumunu, paydaşları ve efor metriklerini merkezi olarak yönetir.
    """
    PRIORITY_CHOICES = (
        ('yuksek', 'Yüksek'),
        ('orta', 'Orta'),
        ('dusuk', 'Düşük'),
    )
    STATUS_CHOICES = (
        ('baslanmadi', 'Başlanmadı'),
        ('calisiliyor', 'Üzerinde Çalışılıyor'),
        ('duraklatildi', 'Duraklatıldı'),
        ('tamamlandi', 'Tamamlandı'),
        ('iptal', 'İptal Edildi'),
    )
    SIZE_CHOICES = (
        (1, '1 - En Düşük'),
        (2, '2 - Düşük'),
        (3, '3 - Orta'),
        (4, '4 - Yüksek'),
        (5, '5 - En Yüksek'),
    )

    title = models.CharField(max_length=200, verbose_name='İş Tanımı')
    description = models.TextField(verbose_name='Detaylı Açıklama', blank=True)
    
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, verbose_name='Öncelik')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='baslanmadi', verbose_name='İşin Durumu')
    size = models.IntegerField(choices=SIZE_CHOICES, verbose_name='İş Büyüklüğü (1-5)')
    
    start_date = models.DateField(verbose_name='Başlangıç Tarihi')
    due_date = models.DateField(verbose_name='Tamamlanma Tarihi')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Oluşturulma Zamanı')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Son Güncelleme')

    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='created_tasks', verbose_name='Oluşturan Yönetici')
    assigned_to = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='assigned_tasks', verbose_name='Atanan Çalışan')
    
    partners = models.ManyToManyField(CustomUser, related_name='partner_tasks', blank=True, verbose_name='İş Ortakları')
    informees = models.ManyToManyField(CustomUser, related_name='informed_tasks', blank=True, verbose_name='Bilgilendirilecek Kişiler')

    planned_hours = models.DecimalField(max_digits=6, decimal_places=2, verbose_name='Planlanan Süre (Saat)')
    # Harcanan süre (spent_hours), WorkLog modeli üzerinden tetiklenen aksiyonlarla dinamik hesaplanır
    spent_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name='Harcanan Süre (Saat)')

    class Meta:
        verbose_name = 'Görev'
        verbose_name_plural = 'Görevler'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"


class RoadmapItem(models.Model):
    """
    Ana göreve bağlı alt adımları (Yol Haritası) temsil eder.
    """
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='roadmap', verbose_name='Bağlı Görev')
    order = models.PositiveIntegerField(default=1, verbose_name='Sıra No')
    description = models.CharField(max_length=300, verbose_name='Adım Açıklaması')
    is_completed = models.BooleanField(default=False, verbose_name='Tamamlandı mı?')
    estimated_duration = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name='Tahmini Süre (Saat)')
    
    completed_by = models.ForeignKey(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_roadmap_items',
        verbose_name='Tamamlayan'
    )
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Tamamlanma Zamanı')
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Yol Haritası Adımı'
        verbose_name_plural = 'Yol Haritası Adımları'

    def __str__(self):
        return f"{self.order}. {self.description}"


class WorkLog(models.Model):
    """
    Kullanıcıların görevler üzerinde harcadıkları günlük çalışma (efor) kayıtları.
    """
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='work_logs', verbose_name='İlgili Görev')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='work_logs', verbose_name='Çalışan')
    
    hours = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Harcanan Süre (Saat)')
    date = models.DateField(default=date.today, verbose_name='Tarih')
    description = models.TextField(verbose_name='Yapılan İş Açıklaması')
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Efor Kaydı'
        verbose_name_plural = 'Efor Kayıtları'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.task.title} ({self.hours} saat)"


class Notification(models.Model):
    """
    Sistem içi anlık bilgilendirme (Inbox) yapısı.
    """
    LEVEL_CHOICES = (
        ('info', 'Bilgi'),
        ('success', 'Başarılı'),
        ('warning', 'Uyarı'),
        ('danger', 'Kritik'),
    )

    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Alıcı'
    )
    actor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
        verbose_name='İşlemi Yapan'
    )
    task = models.ForeignKey(
        'Task',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name='İlgili Görev'
    )

    title = models.CharField(max_length=200, verbose_name='Başlık')
    message = models.TextField(blank=True, verbose_name='Mesaj')
    url = models.CharField(max_length=500, blank=True, verbose_name='Yönlendirme URL')

    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='info', verbose_name='Seviye')
    is_read = models.BooleanField(default=False, verbose_name='Okundu mu?')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Oluşturulma')

    class Meta:
        verbose_name = 'Bildirim'
        verbose_name_plural = 'Bildirimler'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"{self.recipient.username} - {self.title}"