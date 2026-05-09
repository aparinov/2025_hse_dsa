from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Кастомизированное представление модели User в админ-панели.
    """

    readonly_fields = (*UserAdmin.readonly_fields, 'profile_embedding')
    # Добавляем наши кастомные поля в fieldsets для отображения
    # на странице редактирования пользователя.
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        # Наша новая секция для кастомных полей
        (
            _("Профиль"),
            {
                "fields": (
                    "role",
                    "campus",
                    "program",
                    "study_year",
                    "degree_level",
                    "bio",
                    "cover_letter",
                    "contacts",
                    "interests",
                    "grades_json",
                    "grade_profile",
                    "profile_embedding",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    # Добавляем роль в список колонок на странице со всеми пользователями
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff")
    
    # Добавляем фильтрацию по роли
    list_filter = ("role", "is_staff", "is_superuser", "is_active", "groups")

