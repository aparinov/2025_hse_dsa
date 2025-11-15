from django import forms
from django.core.exceptions import ValidationError
from .models import Project, Tag


class ProjectForm(forms.ModelForm):
    """Форма для создания и редактирования проектов."""
    
    class Meta:
        model = Project
        fields = [
            'title',
            'description',
            'max_participants',
            'application_deadline',
            'end_date',
            'tags',
            'milestones',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите название проекта'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Опишите суть проекта'
            }),
            'max_participants': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1
            }),
            'application_deadline': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'tags': forms.CheckboxSelectMultiple(),
            'milestones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Каждая контрольная точка с новой строки'
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        application_deadline = cleaned_data.get('application_deadline')
        end_date = cleaned_data.get('end_date')
        
        if application_deadline and end_date:
            if end_date <= application_deadline:
                raise ValidationError(
                    'Дата завершения проекта должна быть позже срока подачи заявок.'
                )
        
        return cleaned_data

