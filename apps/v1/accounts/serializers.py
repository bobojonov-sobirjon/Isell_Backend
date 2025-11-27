from rest_framework import serializers
from apps.v1.accounts.models import CustomUser
import re


class PhoneLoginSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    
    def validate_phone_number(self, value):
        phone = re.sub(r'[\s\-\+]', '', value)
        
        if not re.match(r'^998\d{9}$', phone):
            raise serializers.ValidationError(
                "Введите корректный номер телефона в формате 998XXXXXXXXX"
            )
        
        return phone


class VerifySMSCodeSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    code = serializers.CharField(max_length=6)
    
    def validate_phone_number(self, value):
        phone = re.sub(r'[\s\-\+]', '', value)
        
        if not re.match(r'^998\d{9}$', phone):
            raise serializers.ValidationError(
                "Введите корректный номер телефона в формате 998XXXXXXXXX"
            )
        
        return phone
    
    def validate_code(self, value):
        if not re.match(r'^\d{4}$', value):
            raise serializers.ValidationError("Код должен содержать 4 цифры")
        
        return value


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'id', 'phone_number', 'first_name', 'last_name', 
            'email', 'date_of_birth', 'avatar', 'address',
            'city', 'country', 'region', 'street', 'house', 'apartment', 'postal_index',
            'pnfl', 'is_veriifed_my_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'phone_number', 'is_veriifed_my_id', 'created_at', 'updated_at']


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'email', 'date_of_birth', 
            'avatar', 'address', 'city', 'country', 'region', 
            'street', 'house', 'apartment', 'postal_index'
        ]


class MyIDSessionSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        max_length=13,
        min_length=12,
        required=False,
        allow_null=True,
        help_text="Номер телефона в формате 998901234567. + необязателен"
    )
    birth_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Дата рождения в формате YYYY-MM-DD"
    )
    pinfl = serializers.CharField(
        max_length=14,
        min_length=14,
        required=False,
        allow_null=True,
        help_text="14-значный персональный ID"
    )
    pass_data = serializers.CharField(
        max_length=9,
        min_length=9,
        required=False,
        allow_null=True,
        help_text="Серия и номер паспорта в формате ABxxxxxxx (2 буквы + 7 цифр)"
    )
    
    def validate_phone_number(self, value):
        if value:
            phone = re.sub(r'[\s\-\+]', '', value)
            if not re.match(r'^998\d{9}$', phone):
                raise serializers.ValidationError(
                    "Введите корректный номер телефона в формате 998XXXXXXXXX"
                )
            return phone
        return value
    
    def validate_pinfl(self, value):
        if value and not re.match(r'^\d{14}$', value):
            raise serializers.ValidationError("PINFL должен содержать 14 цифр")
        return value
    
    def validate_pass_data(self, value):
        if value and not re.match(r'^[A-Z]{2}\d{7}$', value.upper()):
            raise serializers.ValidationError(
                "Паспорт должен быть в формате ABxxxxxxx (2 буквы + 7 цифр)"
            )
        return value.upper() if value else value