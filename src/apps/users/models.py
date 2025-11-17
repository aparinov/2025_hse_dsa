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

    role = models.CharField(
        max_length=15,
        choices=Role.choices,
        default=Role.STUDENT,
        verbose_name=_('Роль')
    )
    
    bio = models.TextField(
        blank=True,
        verbose_name=_('О себе'),
        help_text=_('Расскажите немного о себе, своих навыках и опыте.')
    )
    
    contacts = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Контакты'),
        help_text=_('Например, ваш Telegram, почта или другой способ связи.')
    )
    
    interests = models.ManyToManyField(
        'projects.Tag',  # Ссылаемся на модель Tag из другого приложения строкой
        blank=True,
        verbose_name=_('Научные интересы'),
        related_name='users'
    )

    def __str__(self):
        return self.get_full_name() or self.username
    
    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

