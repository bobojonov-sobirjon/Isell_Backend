from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from .models import CustomUser, SmsCode, EskizToken

try:
    admin.site.unregister(OutstandingToken)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(BlacklistedToken)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    Настройка админки для пользователей
    """
    list_display = ('phone_number', 'username', 'first_name', 'last_name', 'is_staff', 'is_active', 'created_at')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'created_at')
    search_fields = ('first_name', 'last_name', 'phone_number')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        ('Личная информация', {'fields': ('first_name', 'last_name', 'date_of_birth', 'avatar', 'address')}),
        ('Адрес', {'fields': ('city', 'street', 'house', 'apartment', 'postal_index')}),
        ('Права доступа', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Важные даты', {'fields': ('last_login', 'date_joined', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'date_joined', 'last_login', 'reset_token', 'reset_token_expires')

admin.site.site_header = "ISell Uzbekistan CRM Admin"
admin.site.site_title = "ISell Uzbekistan CRM Admin"
admin.site.index_title = "Welcome to ISell Uzbekistan CRM Admin"

admin.site.unregister(Site)