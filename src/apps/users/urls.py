from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'users'

urlpatterns = [
    # Маршруты для аутентификации
    path(
        'login/',
        auth_views.LoginView.as_view(template_name='users/login.html'),
        name='login'
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(template_name='users/logout.html'),
        name='logout'
    ),

    # Маршруты для регистрации и профиля
    path(
        'signup/',
        views.SignUpView.as_view(),
        name='signup'
    ),
    path(
        'profile/',
        views.ProfileView.as_view(),
        name='profile'
    ),
]

