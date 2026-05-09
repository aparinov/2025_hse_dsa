from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0003_project_source_project_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='embedding',
            field=models.JSONField(
                blank=True,
                help_text='Эмбеддинг названия тега для маппинга предметов и семантики.',
                null=True,
                verbose_name='Вектор тега',
            ),
        ),
        migrations.AddField(
            model_name='project',
            name='embedding',
            field=models.JSONField(
                blank=True,
                help_text='Эмбеддинг названия, описания и тегов для рекомендаций.',
                null=True,
                verbose_name='Вектор проекта',
            ),
        ),
    ]
