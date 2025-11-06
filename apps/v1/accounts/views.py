from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta
import random

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from apps.v1.accounts.models import CustomUser, SmsCode
from apps.v1.accounts.serializers import (
    PhoneLoginSerializer, 
    VerifySMSCodeSerializer,
    UserSerializer
)
from apps.v1.accounts.services import EskizSMSService


class PhoneLoginView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Аутентификация'],
        operation_summary="Вход по номеру телефона / Запрос SMS кода",
        operation_description="""
        Отправьте номер телефона и получите 4-значный SMS код.
        
        **Как это работает:**
        1. Отправляется номер телефона (в формате 998XXXXXXXXX)
        2. Если пользователь не существует, он создается автоматически
        3. 4-значный SMS код отправляется через сервис Eskiz
        4. Код действителен 5 минут
        
        **Примечание:** Номер телефона должен начинаться с 998 (Узбекистан)
        """,
        request_body=PhoneLoginSerializer,
        responses={
            200: openapi.Response(
                description="SMS код успешно отправлен",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "SMS код отправлен на ваш номер",
                        "data": {
                            "phone_number": "998901234567",
                            "user_created": True,
                            "expires_in": 300
                        }
                    }
                }
            ),
            400: openapi.Response(
                description="Неверный формат номера телефона",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Неверный формат данных",
                        "errors": {
                            "phone_number": ["Введите корректный номер телефона в формате 998XXXXXXXXX"]
                        }
                    }
                }
            ),
            500: openapi.Response(
                description="Ошибка отправки SMS",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Не удалось отправить SMS. Попробуйте позже."
                    }
                }
            )
        }
    )
    def post(self, request):
        serializer = PhoneLoginSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Неверный формат данных",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        phone_number = serializer.validated_data['phone_number']
        
        user, created = CustomUser.objects.get_or_create(
            phone_number=phone_number,
            defaults={
                'username': phone_number,
                'is_active': True
            }
        )
        
        code = str(random.randint(1000, 9999))
        expires_at = timezone.now() + timedelta(minutes=5)
        
        SmsCode.objects.create(
            user=user,
            code=code,
            expires_at=expires_at
        )
        
        sms_service = EskizSMSService()
        result = sms_service.send_verification_code(phone_number, code)
        
        if isinstance(result, dict):
            sms_sent = result.get('sms_sent', False)
            code_in_response = result.get('code')
            custom_message = result.get('message')
        else:
            sms_sent = result
            code_in_response = None
            custom_message = None
        
        response_data = {
            "phone_number": phone_number,
            "user_created": created,
            "expires_in": 300
        }
        
        if not sms_sent and code_in_response:
            response_data["code"] = code_in_response
            response_data["note"] = "SMS шаблон на модерации. Используйте код из ответа."
        
        if sms_sent:
            message = "SMS код отправлен на ваш номер"
        elif custom_message:
            message = custom_message
        else:
            message = "Код создан. SMS временно недоступна."
        
        return Response(
            {
                "success": True,
                "message": message,
                "data": response_data
            },
            status=status.HTTP_200_OK
        )


class VerifySMSCodeView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Аутентификация'],
        operation_summary="Проверка SMS кода и получение токенов",
        operation_description="""
        Проверьте код из SMS и получите JWT токены для авторизации.
        
        **Как это работает:**
        1. Отправьте номер телефона и 4-значный код
        2. Проверяется правильность кода и срок действия
        3. Проверяется, не использован ли код ранее (is_used)
        4. При успехе возвращаются Access и Refresh токены
        
        **Использование токенов:**
        - Access token: Для API запросов (действует 5 минут)
        - Refresh token: Для получения нового access token (действует 1 день)
        
        **Добавьте в заголовок запроса:**
        ```
        Authorization: Bearer YOUR_ACCESS_TOKEN
        ```
        """,
        request_body=VerifySMSCodeSerializer,
        responses={
            200: openapi.Response(
                description="Успешная аутентификация",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "Успешная авторизация",
                        "data": {
                            "user": {
                                "id": 1,
                                "phone_number": "998901234567",
                                "first_name": "",
                                "last_name": "",
                                "email": ""
                            },
                            "tokens": {
                                "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                                "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
                            }
                        }
                    }
                }
            ),
            400: openapi.Response(
                description="Неверный код или код уже использован",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Неверный код или код уже использован"
                    }
                }
            ),
            404: openapi.Response(
                description="Пользователь не найден",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Пользователь не найден"
                    }
                }
            )
        }
    )
    def post(self, request):
        serializer = VerifySMSCodeSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Неверный формат данных",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']
        
        try:
            user = CustomUser.objects.get(phone_number=phone_number)
        except CustomUser.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Пользователь не найден"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            sms_code = SmsCode.objects.filter(
                user=user,
                code=code,
                is_used=False
            ).latest('created_at')
        except SmsCode.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Неверный код или код уже использован"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if sms_code.is_expired():
            return Response(
                {
                    "success": False,
                    "message": "Код истек. Запросите новый код"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        sms_code.is_used = True
        sms_code.save()
        
        SmsCode.objects.filter(
            user=user,
            expires_at__lt=timezone.now()
        ).delete()
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        
        user_data = UserSerializer(user).data
        
        return Response(
            {
                "success": True,
                "message": "Успешная авторизация",
                "data": {
                    "user": user_data,
                    "tokens": {
                        "access": access_token,
                        "refresh": refresh_token
                    }
                }
            },
            status=status.HTTP_200_OK
        )


class ResendSMSCodeView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Аутентификация'],
        operation_summary="Повторная отправка SMS кода",
        operation_description="""
        Если SMS код не пришел или срок действия истек, получите новый код.
        
        **Как это работает:**
        1. Отправьте номер телефона
        2. Старые коды удаляются
        3. Генерируется новый 4-значный код
        4. Новый код отправляется через SMS
        5. Новый код действителен 5 минут
        
        **Примечание:** Сначала нужно запросить код через /login/
        """,
        request_body=PhoneLoginSerializer,
        responses={
            200: openapi.Response(
                description="SMS код повторно отправлен",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "SMS код повторно отправлен",
                        "data": {
                            "phone_number": "998901234567",
                            "expires_in": 300
                        }
                    }
                }
            ),
            400: openapi.Response(
                description="Неверный формат данных",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Неверный формат данных",
                        "errors": {
                            "phone_number": ["Введите корректный номер телефона в формате 998XXXXXXXXX"]
                        }
                    }
                }
            ),
            404: openapi.Response(
                description="Пользователь не найден",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Сначала запросите код через /login/"
                    }
                }
            ),
            500: openapi.Response(
                description="Ошибка отправки SMS",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Не удалось отправить SMS. Попробуйте позже."
                    }
                }
            )
        }
    )
    def post(self, request):
        serializer = PhoneLoginSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Неверный формат данных",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        phone_number = serializer.validated_data['phone_number']
        
        try:
            user = CustomUser.objects.get(phone_number=phone_number)
        except CustomUser.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Сначала запросите код через /login/"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        SmsCode.objects.filter(user=user).delete()
        
        code = str(random.randint(1000, 9999))
        expires_at = timezone.now() + timedelta(minutes=5)
        
        SmsCode.objects.create(
            user=user,
            code=code,
            expires_at=expires_at
        )
        
        sms_service = EskizSMSService()
        result = sms_service.send_verification_code(phone_number, code)
        
        if isinstance(result, dict):
            sms_sent = result.get('sms_sent', False)
            code_in_response = result.get('code')
            custom_message = result.get('message')
        else:
            sms_sent = result
            code_in_response = None
            custom_message = None
        
        response_data = {
            "phone_number": phone_number,
            "expires_in": 300
        }
        
        if not sms_sent and code_in_response:
            response_data["code"] = code_in_response
            response_data["note"] = "SMS шаблон на модерации. Используйте код из ответа."
        
        if sms_sent:
            message = "SMS код повторно отправлен"
        elif custom_message:
            message = custom_message
        else:
            message = "Код создан. SMS временно недоступна."
        
        return Response(
            {
                "success": True,
                "message": message,
                "data": response_data
            },
            status=status.HTTP_200_OK
        )
