"""
Django settings for Student Projects Platform MVP.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR.parent / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-me-in-production')
CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://93.77.183.209:8080']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,93.77.183.209').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Local apps
    'apps.users',
    'apps.projects',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'cusrach_db'),
        'USER': os.getenv('POSTGRES_USER', 'cusrach_user'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'cusrach_pass'),
        'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/
LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static_root'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR.parent / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Login/Logout URLs
LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'

# Явный маппинг "тег проекта -> релевантные предметы" для интерпретируемого
# преподавательского скоринга и описания эксперимента в статье.
PROJECT_TAG_SUBJECTS = {
    'Analytics': ['Statistics', 'Probability Theory', 'Data Analysis', 'Business Analytics'],
    'Backend': ['Python', 'Databases', 'Software Engineering', 'Web Development'],
    'Business Analysis': ['Business Analytics', 'Systems Analysis', 'Product Management'],
    'Computer Vision': ['Machine Learning', 'Deep Learning', 'Computer Vision'],
    'Data Science': ['Machine Learning', 'Statistics', 'Data Analysis', 'Python'],
    'Design': ['UX Research', 'Product Design', 'Human-Computer Interaction'],
    'DevOps': ['Operating Systems', 'Computer Networks', 'Cloud Computing'],
    'Economics': ['Econometrics', 'Microeconomics', 'Macroeconomics', 'Statistics'],
    'Education': ['Educational Technologies', 'Research Methods', 'Data Analysis'],
    'Finance': ['Finance', 'Econometrics', 'Statistics', 'Risk Management'],
    'Frontend': ['Web Development', 'JavaScript', 'Human-Computer Interaction'],
    'Legal Tech': ['Legal Tech', 'Information Systems', 'Data Analysis'],
    'Machine Learning': ['Machine Learning', 'Deep Learning', 'Statistics', 'Python'],
    'Marketing': ['Marketing Analytics', 'Statistics', 'Business Analytics'],
    'NLP': ['Natural Language Processing', 'Machine Learning', 'Deep Learning'],
    'Product Management': ['Product Management', 'Business Analytics', 'UX Research'],
    'Recommendation Systems': ['Recommendation Systems', 'Machine Learning', 'Data Analysis'],
    'Research': ['Research Methods', 'Statistics', 'Data Analysis'],
    'Strategy': ['Strategic Management', 'Business Analytics', 'Economics'],
    'Web Development': ['Web Development', 'Python', 'Databases', 'JavaScript'],
}

