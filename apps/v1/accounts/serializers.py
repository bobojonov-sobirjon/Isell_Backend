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
            'city', 'street', 'house', 'apartment', 'postal_index'
        ]
        read_only_fields = ['id']
