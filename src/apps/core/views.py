"""Вспомогательные представления ядра приложения."""

from django.db.models import Case, Count, F, IntegerField, Value, When
from django.views.generic import TemplateView

from apps.projects.models import Project
from apps.projects.services import get_recommended_projects


class HomeView(TemplateView):
    """
    Главная страница платформы.

    Отображает блок рекомендованных проектов:
    - для студента с указанными интересами: персональные рекомендации
      на основе пересечения тегов;
    - для остальных пользователей: несколько последних открытых проектов.
    """

    template_name = "home.html"
    max_recommended = 6
    fallback_limit = 6

    def get_recommended_for_user(self, user):
        """
        Возвращает список рекомендованных проектов для переданного пользователя.

        Для студентов с интересами используется сервис рекомендаций.
        Для остальных пользователей возвращается пустой QuerySet.
        """
        if not user.is_authenticated or not getattr(user, "is_student", False):
            return Project.objects.none()

        return get_recommended_projects(user)[: self.max_recommended]

    def get_fallback_projects(self):
        """
        Возвращает резервный список проектов, если персональные рекомендации пусты.

        Используются последние проекты со статусом RECRUITMENT.
        """
        return (
            Project.objects.filter(status=Project.Status.RECRUITMENT)
            .select_related("creator")
            .prefetch_related("tags")
            .annotate(participant_count=Count("participants", distinct=True))
            .annotate(
                _is_full=Case(
                    When(participant_count__gte=F("max_participants"), then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
            .order_by("_is_full", "-created_at")[: self.fallback_limit]
        )

    def get_context_data(self, **kwargs):
        """
        Добавляет в контекст рекомендованные и резервные проекты.
        """
        context = super().get_context_data(**kwargs)

        user = self.request.user
        recommended = (
            self.get_recommended_for_user(user)
            .select_related("creator")
            .prefetch_related("tags")
        )

        # Если персональных рекомендаций нет, используем fallback-список
        if not recommended:
            recommended = self.get_fallback_projects()

        context["recommended_projects"] = recommended
        return context


