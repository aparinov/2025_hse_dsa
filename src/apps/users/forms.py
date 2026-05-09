from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _
import json

from .models import User

STUDENT_BIO_MIN_LEN = 50
STUDENT_MIN_INTERESTS = 3


class CustomUserCreationForm(UserCreationForm):
    """
    Форма для создания нового пользователя.
    Наследуется от стандартной формы Django и добавляет кастомные поля.
    """

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'role',
            'campus',
            'program',
            'study_year',
            'degree_level',
            'bio',
            'cover_letter',
            'interests',
        )
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3}),
            'cover_letter': forms.Textarea(attrs={'rows': 4}),
            'interests': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bio'].required = False
        self.fields['interests'].required = False

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        if role != User.Role.STUDENT:
            return cleaned
        bio = (cleaned.get('bio') or '').strip()
        if len(bio) < STUDENT_BIO_MIN_LEN:
            self.add_error(
                'bio',
                _('Укажите не менее %(min)d символов о себе.') % {'min': STUDENT_BIO_MIN_LEN},
            )
        interests = cleaned.get('interests')
        count = interests.count() if interests is not None else 0
        if count < STUDENT_MIN_INTERESTS:
            self.add_error(
                'interests',
                _('Выберите не менее %(n)d научных интересов.') % {'n': STUDENT_MIN_INTERESTS},
            )
        return cleaned


class UserProfileForm(forms.ModelForm):
    """
    Форма для редактирования профиля пользователя в личном кабинете.
    """
    grades_json = forms.CharField(
        required=False,
        label=_('Оценки'),
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text=_('JSON-объект вида {"Machine Learning": 8, "Data Science": 7}.'),
    )

    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'campus',
            'program',
            'study_year',
            'degree_level',
            'bio',
            'cover_letter',
            'contacts',
            'interests',
            'grades_json',
        )
        
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3}),
            'cover_letter': forms.Textarea(attrs={'rows': 4}),
            'interests': forms.CheckboxSelectMultiple,
        }
        
        help_texts = {
            'interests': _('Выберите теги, которые описывают ваши научные и профессиональные интересы.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        grades = self.instance.grades_json if self.instance and self.instance.pk else {}
        self.fields['grades_json'].initial = json.dumps(grades, ensure_ascii=False, indent=2) if grades else ''

    def clean_grades_json(self):
        value = self.cleaned_data['grades_json'].strip()
        if not value:
            return {}
        return json.loads(value)
