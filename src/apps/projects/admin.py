from django.contrib import admin
from .models import Tag, Project, Application


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Админ-панель для управления тегами."""
    list_display = ('name',)
    search_fields = ('name',)
    fields = ('name', 'embedding')
    readonly_fields = ('embedding',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """Админ-панель для управления проектами."""
    list_display = ('title', 'creator', 'status', 'application_deadline', 'created_at')
    list_filter = ('status', 'created_at', 'application_deadline')
    search_fields = ('title', 'description', 'creator__username')
    filter_horizontal = ('tags', 'participants')
    readonly_fields = ('created_at', 'updated_at', 'embedding')

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'creator', 'status', 'source_project_id')
        }),
        ('Параметры проекта', {
            'fields': ('max_participants', 'application_deadline', 'end_date')
        }),
        ('Теги и участники', {
            'fields': ('tags', 'participants')
        }),
        ('Контрольные точки', {
            'fields': ('milestones',)
        }),
        ('Служебная информация', {
            'fields': ('created_at', 'updated_at', 'embedding'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    """Админ-панель для управления заявками."""
    list_display = ('student', 'project', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('student__username', 'project__title')
    readonly_fields = ('created_at',)

