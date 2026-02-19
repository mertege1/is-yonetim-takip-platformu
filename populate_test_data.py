import os
import django
from datetime import timedelta, date
from django.utils import timezone
from decimal import Decimal

# Django ortamını ayarla
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.models import CustomUser, Task, RoadmapItem, WorkLog, Notification

def run():
    print("Eski veriler temizleniyor.")
    Notification.objects.all().delete()
    WorkLog.objects.all().delete()
    RoadmapItem.objects.all().delete()
    Task.objects.all().delete()
    CustomUser.objects.filter(is_superuser=False).delete()
    
    if not CustomUser.objects.filter(username="admin").exists():
        CustomUser.objects.create_superuser("admin", "admin@aselsan.com", "admin123")

    now = timezone.now()
    today = now.date()

    print("Kullanıcılar ve Ekipler oluşturuluyor.")
    
    # --- YÖNETİCİLER ---
    m1 = CustomUser.objects.create_user(username="m.yilmaz", password="123", email="m.yilmaz@aselsan.com", first_name="Mehmet", last_name="Yılmaz", role="manager", team="team1", title="Yazılım Takım Lideri - 92451")
    m2 = CustomUser.objects.create_user(username="a.kaya", password="123", email="a.kaya@aselsan.com", first_name="Ayşe", last_name="Kaya", role="manager", team="team2", title="Test ve Kalite Lideri - 83721")

    # --- EKİP 1: YAZILIM (5 Kişi) ---
    t1_u1 = CustomUser.objects.create_user(username="a.demir", password="123", email="a.demir@aselsan.com", first_name="Ali", last_name="Demir", role="employee", team="team1", title="Kıdemli Yazılım Mühendisi - 10234")
    t1_u2 = CustomUser.objects.create_user(username="b.sahin", password="123", email="b.sahin@aselsan.com", first_name="Burak", last_name="Şahin", role="employee", team="team1", title="Yazılım Mühendisi - 11452")
    t1_u3 = CustomUser.objects.create_user(username="c.celik", password="123", email="c.celik@aselsan.com", first_name="Cemre", last_name="Çelik", role="employee", team="team1", title="Gömülü Sistem Mühendisi - 10567")
    t1_u4 = CustomUser.objects.create_user(username="d.ozturk", password="123", email="d.ozturk@aselsan.com", first_name="Deniz", last_name="Öztürk", role="employee", team="team1", title="Arayüz Geliştirici - 11890")
    t1_u5 = CustomUser.objects.create_user(username="e.arslan", password="123", email="e.arslan@aselsan.com", first_name="Emre", last_name="Arslan", role="employee", team="team1", title="Veritabanı Uzmanı - 10998")

    # --- EKİP 2: TEST (5 Kişi) ---
    t2_u1 = CustomUser.objects.create_user(username="f.koc", password="123", email="f.koc@aselsan.com", first_name="Fatih", last_name="Koç", role="employee", team="team2", title="Otomasyon Test Mühendisi - 20112")
    t2_u2 = CustomUser.objects.create_user(username="g.polat", password="123", email="g.polat@aselsan.com", first_name="Gizem", last_name="Polat", role="employee", team="team2", title="Sistem Test Uzmanı - 20443")
    t2_u3 = CustomUser.objects.create_user(username="h.can", password="123", email="h.can@aselsan.com", first_name="Hakan", last_name="Can", role="employee", team="team2", title="Performans Test Mühendisi - 21564")
    t2_u4 = CustomUser.objects.create_user(username="i.bulut", password="123", email="i.bulut@aselsan.com", first_name="İrem", last_name="Bulut", role="employee", team="team2", title="Kalite Güvence Uzmanı - 22675")
    t2_u5 = CustomUser.objects.create_user(username="k.yavuz", password="123", email="k.yavuz@aselsan.com", first_name="Kemal", last_name="Yavuz", role="employee", team="team2", title="Saha Test Sorumlusu - 20886")

    # YARDIMCI BİLDİRİM FONKSİYONU
    def make_notification(recipient, actor, task_obj, title, message, level, days_ago, hours_ago=0, is_read=False):
        n = Notification.objects.create(
            recipient=recipient, actor=actor, task=task_obj, title=title, message=message, level=level, is_read=is_read, url=f"/task/{task_obj.id}/" if task_obj else ""
        )
        fake_time = now - timedelta(days=days_ago, hours=hours_ago)
        Notification.objects.filter(id=n.id).update(created_at=fake_time)

    # YARDIMCI EFOR FONKSİYONU
    def add_worklog(task, user, hours, days_ago, desc):
        wl = WorkLog.objects.create(task=task, user=user, hours=hours, date=today - timedelta(days=days_ago), description=desc)
        WorkLog.objects.filter(id=wl.id).update(created_at=now - timedelta(days=days_ago))
        task.spent_hours = sum(w.hours for w in task.work_logs.all())
        task.save(update_fields=['spent_hours'])

    print("azılım Ekibi (Team 1) Görevleri")

    # T1: Devam Eden, Çok Ortaklı Büyük Proje (Ali, Burak, Cemre)
    task1 = Task.objects.create(
        title="Radar Sinyal İşleme Arayüzü V3.0", description="Sahadan gelen ham radar verilerinin işlenip operatör paneline saniyenin altında gecikmeyle yansıtılması.",
        priority="yuksek", status="calisiliyor", size=5, start_date=today - timedelta(days=10), due_date=today + timedelta(days=5), planned_hours=120.0, created_by=m1, assigned_to=t1_u1
    )
    task1.partners.add(t1_u2, t1_u3); task1.informees.add(m2)
    RoadmapItem.objects.create(task=task1, order=1, description="Mevcut V2.0 kodlarının analiz edilmesi", estimated_duration=10.0, is_completed=True)
    RoadmapItem.objects.create(task=task1, order=2, description="C++ ile sinyal ayrıştırma (parsing) modülünün yazılması", estimated_duration=40.0, is_completed=True)
    RoadmapItem.objects.create(task=task1, order=3, description="Python/Django Backend Socket entegrasyonu", estimated_duration=30.0, is_completed=False)
    add_worklog(task1, t1_u1, 15.5, 8, "Kod analizine başlandı, rapor çıkarıldı.")
    add_worklog(task1, t1_u2, 22.0, 5, "C++ ayrıştırma modülü %80 oranında tamamlandı.")
    add_worklog(task1, t1_u3, 10.0, 2, "Backend soket testleri başladı.")

    # T2: Geçmişte Tamamlanmış İş (Emre, Deniz)
    task2 = Task.objects.create(
        title="PostgreSQL İndeksleme ve Log Temizliği", description="Mevcut telemetri veritabanının yavaşlaması üzerine indeks yapısının onarılması.",
        priority="orta", status="tamamlandi", size=3, start_date=today - timedelta(days=30), due_date=today - timedelta(days=20), planned_hours=40.0, created_by=m1, assigned_to=t1_u5
    )
    task2.partners.add(t1_u4)
    RoadmapItem.objects.create(task=task2, order=1, description="Slow query loglarının analizi", estimated_duration=10.0, is_completed=True)
    RoadmapItem.objects.create(task=task2, order=2, description="İndeks oluşturma ve test", estimated_duration=30.0, is_completed=True)
    add_worklog(task2, t1_u5, 25.0, 25, "Tüm sorgular optimize edildi.")
    add_worklog(task2, t1_u4, 18.0, 22, "Arayüz sorgu süreleri %40 düştü, testler onaylandı.")

    # T3: Duraklatılmış İş (Cemre)
    task3 = Task.objects.create(
        title="TCP/IP Protokol Değişimi", description="Eski seri haberleşme yapısından TCP/IP tabanlı yeni protokole geçiş.",
        priority="orta", status="duraklatildi", size=4, start_date=today - timedelta(days=15), due_date=today + timedelta(days=15), planned_hours=80.0, created_by=m1, assigned_to=t1_u3
    )
    RoadmapItem.objects.create(task=task3, order=1, description="Donanım tedariği ve ağ kurulumu", estimated_duration=20.0, is_completed=False)
    add_worklog(task3, t1_u3, 12.0, 14, "Analiz yapıldı ancak donanım parçaları gümrükte takıldığı için iş duraklatıldı.")

    # T4: Düşük Öncelikli, Yeni Başlayacak İş (Deniz, Ali)
    task4 = Task.objects.create(
        title="Kullanıcı Arayüzü Dark Mode Entegrasyonu", description="Operatörlerin gece görevlerinde göz yorgunluğunu azaltmak için Dark Mode eklenmesi.",
        priority="dusuk", status="baslanmadi", size=2, start_date=today + timedelta(days=2), due_date=today + timedelta(days=10), planned_hours=30.0, created_by=m1, assigned_to=t1_u4
    )
    task4.partners.add(t1_u1)
    RoadmapItem.objects.create(task=task4, order=1, description="Renk paletlerinin belirlenmesi", estimated_duration=10.0, is_completed=False)
    RoadmapItem.objects.create(task=task4, order=2, description="CSS değişkenlerinin uygulanması", estimated_duration=20.0, is_completed=False)

    # T5: Kritik ve Aktif İş (Burak)
    task5 = Task.objects.create(
        title="API Gateway Optimizasyonu", description="Mikroservisler arası iletişimi hızlandırmak için Gateway yapısının Redis ile desteklenmesi.",
        priority="yuksek", status="calisiliyor", size=4, start_date=today - timedelta(days=5), due_date=today + timedelta(days=2), planned_hours=50.0, created_by=m1, assigned_to=t1_u2
    )
    RoadmapItem.objects.create(task=task5, order=1, description="Redis Cache implementasyonu", estimated_duration=25.0, is_completed=True)
    add_worklog(task5, t1_u2, 28.5, 3, "Cache mekanizması devreye alındı, response time 200ms altına düştü.")


    print("Test Ekibi (Team 2) Görevleri")

    # T6: Gecikmiş Kritik Test İşi (Kemal, Gizem)
    task6 = Task.objects.create(
        title="İHA Kamera Modülü - Gece Uçuş Testleri", description="Termal kameraların gece uçuşlarındaki hedef tespiti ve takibi testlerinin saha ortamında gerçekleştirilmesi.",
        priority="yuksek", status="calisiliyor", size=5, start_date=today - timedelta(days=12), due_date=today - timedelta(days=1), planned_hours=60.0, created_by=m2, assigned_to=t2_u5
    )
    task6.partners.add(t2_u2); task6.informees.add(m1)
    RoadmapItem.objects.create(task=task6, order=1, description="Test senaryoları hazırlığı", estimated_duration=10.0, is_completed=True)
    RoadmapItem.objects.create(task=task6, order=2, description="Saha uçuşu ve kayıt", estimated_duration=50.0, is_completed=False)
    add_worklog(task6, t2_u5, 20.0, 5, "Hazırlıklar tamam. Hava muhalefeti sebebiyle uçuşlar ertelendiği için görev gecikti.")
    add_worklog(task6, t2_u2, 15.0, 2, "Laboratuvar ortamında simülasyon testleri yapıldı.")

    # T7: Aktif Yük Testi (İrem, Hakan)
    task7 = Task.objects.create(
        title="Sunucu Yük ve Stres Testi", description="Sisteme anlık 10.000 kullanıcı bağlandığında yaşanacak darboğazların JMeter ile tespiti.",
        priority="yuksek", status="calisiliyor", size=4, start_date=today - timedelta(days=4), due_date=today + timedelta(days=6), planned_hours=80.0, created_by=m2, assigned_to=t2_u4
    )
    task7.partners.add(t2_u3)
    RoadmapItem.objects.create(task=task7, order=1, description="JMeter scriptlerinin yazılması", estimated_duration=30.0, is_completed=True)
    add_worklog(task7, t2_u4, 25.0, 2, "Scriptler hazırlandı, ilk deneme koşuldu.")
    add_worklog(task7, t2_u3, 10.5, 1, "Sunucu metrikleri (CPU/RAM) izlemeye alındı.")

    # T8: Tamamlanmış Otomasyon İşi (Gizem)
    task8 = Task.objects.create(
        title="Regresyon Test Otomasyonu", description="Her yeni sürüm çıkışında manuel yapılan regresyon testlerinin Selenium ile otomatize edilmesi.",
        priority="orta", status="tamamlandi", size=5, start_date=today - timedelta(days=45), due_date=today - timedelta(days=15), planned_hours=100.0, created_by=m2, assigned_to=t2_u2
    )
    RoadmapItem.objects.create(task=task8, order=1, description="Tüm modüllerin otomatize edilmesi", estimated_duration=100.0, is_completed=True)
    add_worklog(task8, t2_u2, 95.0, 16, "Süreç başarıyla tamamlandı, CI/CD pipeline'a eklendi.")

    # T9: Aktif Sızma Testi (Fatih)
    task9 = Task.objects.create(
        title="Siber Güvenlik Sızma Testi", description="Dış ağdan ve iç ağdan sisteme yapılabilecek olası saldırıların simüle edilmesi.",
        priority="orta", status="calisiliyor", size=3, start_date=today - timedelta(days=2), due_date=today + timedelta(days=8), planned_hours=40.0, created_by=m2, assigned_to=t2_u1
    )
    add_worklog(task9, t2_u1, 16.0, 1, "Nessus ile otomatik taramalar başlatıldı, ilk bulgular raporlanıyor.")

    # T10: Henüz Başlamamış İş (Hakan)
    task10 = Task.objects.create(
        title="Çevresel Koşullar Simülasyonu", description="Donanımların -40 ve +60 derece sıcaklıklarda çalışma dayanıklılığının test edilmesi.",
        priority="yuksek", status="baslanmadi", size=4, start_date=today + timedelta(days=5), due_date=today + timedelta(days=20), planned_hours=70.0, created_by=m2, assigned_to=t2_u3
    )
    RoadmapItem.objects.create(task=task10, order=1, description="İklimlendirme kabininin ayarlanması", estimated_duration=10.0, is_completed=False)


    # Ali'ye gelen bildirimler
    make_notification(t1_u1, m1, task1, "Yeni görev atandı 🚀", "Mehmet Yılmaz, 'Radar Sinyal İşleme Arayüzü V3.0' görevini oluşturdu.", "success", 10, is_read=True)
    make_notification(t1_u1, t1_u2, task1, "Yol haritası güncellendi", "Burak Şahin, 'C++ ayrıştırma' adımını tamamladı ✅", "info", 5, is_read=False)
    make_notification(t1_u1, m1, None, "Görev Silindi 🗑️", "Eski Sunucu Taşıma İşlemi görevi, Mehmet Yılmaz tarafından silindi.", "danger", 1, is_read=False)
    
    # Yönetici Mehmet'e gelen bildirimler
    make_notification(m1, t1_u2, task5, "Efor girişi yapıldı", "Burak Şahin, 'API Gateway' için 28.5 saat efor girdi.", "info", 3, is_read=True)
    make_notification(m1, t1_u5, task2, "Görev güncellendi 📝", "Emre Arslan, 'PostgreSQL İndeksleme' görevini Tamamlandı olarak işaretledi.", "warning", 20, is_read=True)
    make_notification(m1, t2_u5, task6, "Efor girişi yapıldı", "Takip ettiğiniz 'İHA Gece Uçuş Testleri' görevine Kemal Yavuz efor girdi (Hava Muhalefeti).", "info", 4, is_read=False)

    # Yönetici Ayşe'ye gelen bildirimler
    make_notification(m2, t2_u4, task7, "Efor kaydı güncellendi", "İrem Bulut, girdiği eforu 15 saatten 25 saate güncelledi.", "warning", 2, is_read=False)
    make_notification(m2, t2_u2, task8, "Görev güncellendi 📝", "Gizem Polat, 'Regresyon Otomasyonu' görevini Tamamlandı yaptı.", "warning", 15, is_read=True)

    print("\n" + "="*60)
    print("="*60)
    print("\n[ TEST HESAPLARI ] (Şifre: 123)")
    print("Yöneticiler : m.yilmaz (Yazılım) | a.kaya (Test)")
    print("Çalışanlar  : a.demir, b.sahin, e.arslan (Yazılım)")
    print("               : f.koc, k.yavuz, i.bulut (Test)")
    print("="*60)

if __name__ == "__main__":
    run()