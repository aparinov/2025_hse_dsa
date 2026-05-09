from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_recommendation_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='grade_profile',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Средние оценки по осям-тегам после маппинга предметов.',
                verbose_name='Профиль оценок по тегам',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='profile_embedding',
            field=models.JSONField(
                blank=True,
                help_text='Эмбеддинг мотивационного письма, био и программы.',
                null=True,
                verbose_name='Вектор профиля',
            ),
        ),
    ]
