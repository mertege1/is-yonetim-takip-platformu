from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Task, RoadmapItem, WorkLog, Notification

# Admin paneli global görsel ayarları
admin.site.site_header = "ASELSAN İş Yönetim Platformu"
admin.site.site_title = "İş Takip Admin Paneli"
admin.site.index_title = "Yönetim Merkezi"

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient", "title", "level", "is_read", "created_at")
    list_filter = ("level", "is_read", "created_at")
    search_fields = ("title", "message", "recipient__username", "recipient__email")
    ordering = ("-created_at",)

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'team', 'title']
    fieldsets = UserAdmin.fieldsets + (
        ('Şirket Bilgileri', {'fields': ('role', 'team', 'title')}),
    )

# Task detay ekranında roadmap ve logları tek sayfada yönetmek için inline yapıları
class RoadmapInline(admin.TabularInline):
    model = RoadmapItem
    extra = 1

class WorkLogInline(admin.TabularInline):
    model = WorkLog
    extra = 0  # Sadece girilmiş mevcut kayıtları göster, fazladan boş satır açma
    readonly_fields = ['created_at']
    fields = ['user', 'hours', 'date', 'description']

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'assigned_to', 'priority', 'status', 'due_date', 'planned_hours', 'spent_hours']
    # Atanan kişinin takımına (assigned_to__team) göre hızlı filtreleme yeteneği eklendi
    list_filter = ['status', 'priority', 'assigned_to', 'assigned_to__team'] 
    search_fields = ['title', 'description']
    inlines = [RoadmapInline, WorkLogInline]

# Efor kayıtlarını görevden bağımsız, toplu olarak filtreleyip analiz edebilmek için
@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ['task', 'user', 'hours', 'date']
    list_filter = ['date', 'user', 'task']
    search_fields = ['description', 'task__title', 'user__username']