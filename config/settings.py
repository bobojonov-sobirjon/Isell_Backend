# Import library configurations
from config.libraries.rest_framework import REST_FRAMEWORK
from config.libraries.jwt import SIMPLE_JWT
from config.libraries.cors import CSRF_TRUSTED_ORIGINS, CORS_ALLOWED_ORIGINS, CORS_ALLOW_ALL_ORIGINS, CORS_ORIGIN_ALLOW_ALL, CORS_ALLOW_CREDENTIALS, CORS_ORIGIN_WHITELIST
from config.libraries.email import EMAIL_BACKEND, EMAIL_HOST, EMAIL_PORT, EMAIL_USE_TLS, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL
from config.libraries.swagger import SWAGGER_SETTINGS, SWAGGER_UI_OAUTH2_CONFIG

import os
from datetime import timedelta
from pathlib import Path


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    load_dotenv = None


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-wb#%2kx-0o!ec!#-&9p=wu02er+f63qq9%o%ddwn*87c3fl595'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]


# Application definition

LOCAL_APPS = [
    'apps.v1.accounts',
    'apps.v1.products',
    'apps.v1.order',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_yasg',
    'corsheaders',
    'django_filters',
    'import_export',
    *LOCAL_APPS,
]

INSTALLED_APPS = [
    'django.contrib.sites',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    *THIRD_PARTY_APPS,
]

LOCAL_MIDDLEWARE = [
    'config.middleware.middleware.JsonErrorResponseMiddleware',
    'config.middleware.middleware.Custom404Middleware',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    *LOCAL_MIDDLEWARE,
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# Database settings with PostgreSQL

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "/var/www/media/")

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
)

AUTH_USER_MODEL = 'accounts.CustomUser'

SITE_ID = 1

# Eskiz SMS Configuration
ESKIZ_EMAIL = os.getenv('ESKIZ_EMAIL', 'info.isell.uz@gmail.com')
ESKIZ_PASSWORD = os.getenv('ESKIZ_PASSWORD', 'UWZMdzaSGbK7Q0lutLoIMpZJbYRYy9TqiiqnvUhM')

print(ESKIZ_EMAIL, ESKIZ_PASSWORD)
print(os.getenv('ISell_API_KEY'))
print(os.getenv('ISell_DOC_ID'))
print(os.getenv('ISell_PRODUCT_VARIATIONS'))
print(os.getenv('ISell_PRODUCT_PRICE'))
print(os.getenv('ISell_PROPERTY'))
print(os.getenv('ISell_PROPERTY_VALUE'))
print(os.getenv('ISell_PRODUCT_PROPERTY_VALUE'))
print(os.getenv('ISell_PRODUCT_CATEGORIES'))
print(os.getenv('ISell_TARIFFS'))
print(os.getenv('ISell_ADVANCED_PAYMENT_ASSESSMENT'))
print(os.getenv('ISell_RISK_CATEGORY'))
print(os.getenv('ISell_PRICE_CATEGORY'))