from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from .forms import CustomUserCreationForm, UserProfileForm
from .models import User

class SignUpView(CreateView):
    """
    Представление для регистрации нового пользователя.
    """
    form_class = CustomUserCreationForm
    template_name = 'users/signup.html'
    success_url = reverse_lazy('users:login')

class ProfileView(LoginRequiredMixin, UpdateView):
    """
    Представление для просмотра и редактирования профиля пользователя.
    Доступно только для авторизованных пользователей.
    """
    model = User
    form_class = UserProfileForm
    template_name = 'users/profile.html'
    
    def get_object(self, queryset=None):
        """
        Возвращает объект текущего пользователя, чтобы
        гарантировать, что пользователь редактирует только свой профиль.
        """
        return self.request.user

    def get_success_url(self):
        """
        После успешного обновления профиля, перенаправляем пользователя
        обратно на эту же страницу.
        """
        return reverse_lazy('users:profile')

