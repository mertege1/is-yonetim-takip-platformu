from django.urls import path
from . import views

urlpatterns = [
    # Ana sayfa (Yönlendirici - Giriş sonrası buraya düşer)
    path('', views.home, name='home'),
    
    # Çalışan Paneli Adresi
    path('dashboard/employee/', views.employee_dashboard, name='employee_dashboard'),
    
    # Yönetici Paneli Adresi
    path('dashboard/manager/', views.manager_dashboard, name='manager_dashboard'),

    # Görev Oluşturma
    path('task/create/', views.create_task, name='create_task'),

    # Görev Detay ve Düzenleme
    # <int:pk> kısmı, URL'deki sayıyı alıp fonksiyona 'pk' (ID) olarak gönderir.
    path('task/<int:pk>/', views.task_detail, name='task_detail'),
    path('task/<int:pk>/edit/', views.update_task, name='update_task'),
    
    path('task/<int:pk>/delete/', views.delete_task, name='delete_task'),
    
        # Bildirim Merkezi (Inbox)
    # Bildirim Merkezi (Inbox)
    path("notifications/", views.notifications_inbox, name="notifications_inbox"),
    path("notifications/<int:pk>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("notifications/read-all/", views.notifications_mark_all_read, name="notifications_mark_all_read"),

    # Navbar için mini API
    path("notifications/unread-count/", views.notifications_unread_count, name="notifications_unread_count"),
    # Navbar için mini API
    path("notifications/api/unread-count/", views.notifications_unread_count, name="notifications_unread_count_api"),
    
    # ✅ Dropdown preview API
    path("notifications/api/latest/", views.notifications_latest_api, name="notifications_latest_api"),
    path("notifications/<int:pk>/delete/", views.notification_delete, name="notification_delete"),
    path("tasks/<int:task_pk>/roadmap/<int:item_pk>/toggle/", views.roadmap_toggle, name="roadmap_toggle"),
    
    path("tasks/<int:task_pk>/roadmap/edit/", views.roadmap_edit, name="roadmap_edit"),

    path("roadmap/<int:item_id>/toggle/", views.roadmap_toggle_complete, name="roadmap_toggle_complete"),
    path("notifications/delete-all/", views.notifications_delete_all, name="notifications_delete_all"),
    path("notifications/delete-read/", views.notifications_delete_read, name="notifications_delete_read"),
    path('history/', views.task_history, name='task_history'),

    path('worklog/<int:pk>/edit/', views.edit_worklog, name='edit_worklog'),
    path('worklog/<int:pk>/delete/', views.delete_worklog, name='delete_worklog'),
]