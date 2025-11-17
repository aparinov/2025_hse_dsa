from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

class Tag(models.Model):
    """Модель для тегов, используемых в интересах и проектах."""
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_('Название тега')
    )

    class Meta:
        verbose_name = _('Тег')
        verbose_name_plural = _('Теги')
        ordering = ['name']

    def __str__(self):
        return self.name

class Project(models.Model):
    """Модель проекта."""
    class Status(models.TextChoices):
        RECRUITMENT = 'RECRUITMENT', _('Набор открыт')
        IN_PROGRESS = 'IN_PROGRESS', _('В процессе')
        COMPLETED = 'COMPLETED', _('Завершен')
        ARCHIVED = 'ARCHIVED', _('В архиве')
    
    title = models.CharField(max_length=250, verbose_name=_('Название проекта'))
    description = models.TextField(verbose_name=_('Описание'))
    
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_projects',
        verbose_name=_('Руководитель')
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECRUITMENT,
        verbose_name=_('Статус')
    )
    
    max_participants = models.PositiveIntegerField(
        default=3,
        verbose_name=_('Количество мест')
    )
    
    application_deadline = models.DateField(verbose_name=_('Срок подачи заявок'))
    end_date = models.DateField(verbose_name=_('Дата завершения проекта'))

    tags = models.ManyToManyField(
        Tag,
        blank=True,
        verbose_name=_('Теги проекта')
    )
    
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='projects',
        blank=True,
        verbose_name=_('Участники')
    )
    
    milestones = models.TextField(
        blank=True,
        verbose_name=_('Контрольные точки (списком)'),
        help_text=_('Каждая точка с новой строки.')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Проект')
        verbose_name_plural = _('Проекты')
        ordering = ['-created_at']

    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('projects:project-detail', kwargs={'pk': self.pk})

class Application(models.Model):
    """Модель заявки на участие в проекте."""
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('На рассмотрении')
        APPROVED = 'APPROVED', _('Принята')
        REJECTED = 'REJECTED', _('Отклонена')

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='applications',
        verbose_name=_('Проект')
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='applications',
        verbose_name=_('Студент')
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_('Статус заявки')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Заявка')
        verbose_name_plural = _('Заявки')
        # Гарантируем, что студент может подать только одну заявку на один проект
        unique_together = ('project', 'student')
        ordering = ['-created_at']

    def __str__(self):
        return f"Заявка от {self.student} на проект '{self.project.title}'"
