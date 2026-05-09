from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    """
    Кастомная модель пользователя.
    Наследуется от AbstractUser, добавляя роли и дополнительную информацию.
    """
    class Role(models.TextChoices):
        STUDENT = 'STUDENT', _('Студент')
        TEACHER = 'TEACHER', _('Преподаватель')

    class DegreeLevel(models.TextChoices):
        BACHELOR = 'BACHELOR', _('Бакалавриат')
        MASTER = 'MASTER', _('Магистратура')

    role = models.CharField(
        max_length=15,
        choices=Role.choices,
        default=Role.STUDENT,
        verbose_name=_('Роль')
    )

    program = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Образовательная программа')
    )

    campus = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Кампус')
    )

    study_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Курс')
    )

    degree_level = models.CharField(
        max_length=20,
        choices=DegreeLevel.choices,
        blank=True,
        verbose_name=_('Уровень образования')
    )
    
    bio = models.TextField(
        blank=True,
        verbose_name=_('О себе'),
        help_text=_('Расскажите немного о себе, своих навыках и опыте.')
    )

    cover_letter = models.TextField(
        blank=True,
        verbose_name=_('Мотивационное письмо'),
        help_text=_('Коротко опишите, какие проекты вам интересны и почему.')
    )
    
    contacts = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Контакты'),
        help_text=_('Например, ваш Telegram, почта или другой способ связи.')
    )

    grades_json = models.JSONField(
        blank=True,
        default=dict,
        verbose_name=_('Оценки'),
        help_text=_('JSON-объект вида {"Machine Learning": 8, "Data Science": 7}.')
    )

    grade_profile = models.JSONField(
        blank=True,
        default=dict,
        verbose_name=_('Профиль оценок по тегам'),
        help_text=_('Средние оценки по осям-тегам после маппинга предметов.'),
    )

    profile_embedding = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Вектор профиля'),
        help_text=_('Эмбеддинг мотивационного письма, био и программы.'),
    )
    
    interests = models.ManyToManyField(
        'projects.Tag',  # Ссылаемся на модель Tag из другого приложения строкой
        blank=True,
        verbose_name=_('Научные интересы'),
        related_name='users'
    )

    def save(self, *args, **kwargs):
        grades_changed = True
        if self.pk:
            previous = (
                type(self)
                .objects.filter(pk=self.pk)
                .only('bio', 'cover_letter', 'program', 'grades_json')
                .first()
            )
            if previous:
                text_changed = (
                    previous.bio != self.bio
                    or previous.cover_letter != self.cover_letter
                    or previous.program != self.program
                )
                if text_changed:
                    self.profile_embedding = None
                grades_changed = previous.grades_json != self.grades_json
        super().save(*args, **kwargs)
        if self.role == self.Role.STUDENT and grades_changed:
            from apps.projects.grade_profile import rebuild_grade_profile

            rebuild_grade_profile(self)

    def __str__(self):
        return self.get_full_name() or self.username
    
    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

