from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import User


class CustomUserCreationForm(UserCreationForm):
    """
    Форма для создания нового пользователя.
    Наследуется от стандартной формы Django и добавляет кастомные поля.
    """
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'role')


class UserProfileForm(forms.ModelForm):
    """
    Форма для редактирования профиля пользователя в личном кабинете.
    """
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'bio', 'contacts', 'interests')
        
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3}),
            'interests': forms.CheckboxSelectMultiple,
        }
        
        help_texts = {
            'interests': _('Выберите теги, которые описывают ваши научные и профессиональные интересы.'),
        }
