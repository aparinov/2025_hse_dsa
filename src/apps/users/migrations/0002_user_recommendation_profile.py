from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='campus',
            field=models.CharField(blank=True, max_length=100, verbose_name='Кампус'),
        ),
        migrations.AddField(
            model_name='user',
            name='cover_letter',
            field=models.TextField(
                blank=True,
                help_text='Коротко опишите, какие проекты вам интересны и почему.',
                verbose_name='Мотивационное письмо',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='degree_level',
            field=models.CharField(
                blank=True,
                choices=[('BACHELOR', 'Бакалавриат'), ('MASTER', 'Магистратура')],
                max_length=20,
                verbose_name='Уровень образования',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='grades_json',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='JSON-объект вида {"Machine Learning": 8, "Data Science": 7}.',
                verbose_name='Оценки',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='program',
            field=models.CharField(blank=True, max_length=255, verbose_name='Образовательная программа'),
        ),
        migrations.AddField(
            model_name='user',
            name='study_year',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Курс'),
        ),
    ]
