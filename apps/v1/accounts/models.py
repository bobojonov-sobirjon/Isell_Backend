from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from apps.v1.accounts.managers import CustomUserManager


class CustomUser(AbstractUser):
    phone_number = models.CharField(
        unique=True,
        max_length=15,
        blank=True,
        null=True,
        verbose_name="Номер телефона",
        help_text="Необязательно. Введите ваш номер телефона."
    )
    date_of_birth = models.DateField(
        blank=True,
        null=True,
        verbose_name="Дата рождения",
        help_text="Необязательно. Введите вашу дату рождения."
    )
    avatar = models.ImageField(
        upload_to='avatars/',
        blank=True,
        null=True,
        verbose_name="Аватар",
        help_text="Необязательно. Загрузите ваше фото профиля."
    )
    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="Адрес",
        help_text="Необязательно. Введите ваш адрес."
    )
    city = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Город",
        help_text="Необязательно. Введите ваш город."
    )
    street = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Улица",
        help_text="Необязательно. Введите вашу улицу."
    )
    house = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Дом",
        help_text="Необязательно. Введите номер дома."
    )
    apartment = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Квартира",
        help_text="Необязательно. Введите номер квартиры."
    )
    postal_index = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Индекс",
        help_text="Необязательно. Введите почтовый индекс."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )
    reset_token = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Токен сброса пароля",
        help_text="Токен для сброса пароля"
    )
    reset_token_expires = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Время истечения токена"
    )

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']
    
    objects = CustomUserManager()

    class Meta:
        verbose_name = "01. Пользователь"
        verbose_name_plural = "01. Пользователи"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.phone_number} ({self.get_full_name()})"

    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.phone_number

    def get_short_name(self):
        return self.first_name if self.first_name else self.phone_number


class SmsCode(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sms_codes')
    code = models.CharField(max_length=6, verbose_name="Код")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    expires_at = models.DateTimeField(verbose_name="Дата истечения")
    is_used = models.BooleanField(default=False, verbose_name="Использован")

    class Meta:
        verbose_name = "02. SMS код"
        verbose_name_plural = "02. SMS коды"
        ordering = ['-created_at']

    def __str__(self):     
        return f"{self.user.phone_number} - {self.code}"
    
    def is_expired(self):
        """Проверка на истечение срока кода"""
        from django.utils import timezone
        return timezone.now() > self.expires_at


class EskizToken(models.Model):
    """Model for storing Eskiz API token"""
    token = models.TextField(verbose_name="Token")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    expires_at = models.DateTimeField(verbose_name="Дата истечения")
    
    class Meta:
        verbose_name = "03. Eskiz Token"
        verbose_name_plural = "03. Eskiz Tokens"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Token created at {self.created_at}"
    
    def is_expired(self):
        """Проверка на истечение токена"""
        from django.utils import timezone
        return timezone.now() > self.expires_at