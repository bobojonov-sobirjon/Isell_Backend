from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta
import random
import secrets
import re
from django.shortcuts import render

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from apps.v1.accounts.models import CustomUser, SmsCode
from apps.v1.accounts.serializers import (
    PhoneLoginSerializer, 
    VerifySMSCodeSerializer,
    UserSerializer,
    MyIDSessionSerializer,
    UserUpdateSerializer
)
from apps.v1.accounts.services import EskizSMSService
from apps.v1.accounts.services.myid_service import get_access_token, create_session, get_user_data


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
        
        try:
            user = CustomUser.objects.get(phone_number=phone_number)
            created = False
        except CustomUser.DoesNotExist:
            username_exists = CustomUser.objects.filter(username=phone_number).exists()
            if username_exists:
                import uuid
                username = f"{phone_number}_{uuid.uuid4().hex[:8]}"
            else:
                username = phone_number
            
            try:
                user = CustomUser.objects.create(
                    phone_number=phone_number,
                    username=username,
                    is_active=True
                )
                created = True
            except Exception as e:
                import uuid
                username = f"{phone_number}_{uuid.uuid4().hex[:8]}"
                user = CustomUser.objects.create(
                    phone_number=phone_number,
                    username=username,
                    is_active=True
                )
                created = True
        else:
            if not user.username or user.username != phone_number:
                username_exists = CustomUser.objects.filter(username=phone_number).exclude(id=user.id).exists()
                if not username_exists:
                    try:
                        user.username = phone_number
                        user.save(update_fields=['username'])
                    except Exception:
                        pass
        
        SmsCode.objects.filter(user=user).delete()
        
        code = str(secrets.randbelow(9000) + 1000)
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
        
        if not user.is_veriifed_my_id:
            return Response(
                {
                    "success": True,
                    "message": "Код подтвержден. Требуется верификация через MyID",
                    "data": {}
                },
                status=status.HTTP_200_OK
            )
        
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
        
        code = str(secrets.randbelow(9000) + 1000)
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


class CreateMyIDSessionView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['MyID'],
        operation_summary="Создание сессии MyID",
        operation_description="""
        Создает сессию для идентификации через MyID.
        
        **Параметры:**
        - phone_number: Номер телефона (опционально)
        - birth_date: Дата рождения в формате YYYY-MM-DD (опционально)
        - pinfl: 14-значный персональный ID (опционально)
        - pass_data: Серия и номер паспорта в формате ABxxxxxxx (опционально)
        
        **Возвращает:**
        - session_id: ID сессии для использования в SDK
        - access_token: Токен доступа для последующих запросов
        """,
        request_body=MyIDSessionSerializer,
        responses={
            200: openapi.Response(
                description="Сессия успешно создана",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "Сессия создана",
                        "data": {
                            "session_id": "140a262b-d99f-4328-bf6b-ac1619cabcbd",
                            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
                        }
                    }
                }
            ),
            400: openapi.Response(
                description="Ошибка валидации данных",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Неверный формат данных",
                        "errors": {}
                    }
                }
            ),
            500: openapi.Response(
                description="Ошибка создания сессии",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Не удалось создать сессию"
                    }
                }
            )
        }
    )
    def post(self, request):
        serializer = MyIDSessionSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Неверный формат данных",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        token_result = get_access_token()
        if not token_result.get("success"):
            error_msg = token_result.get("error", "Unknown error")
            error_detail = token_result.get("error_detail")
            return Response(
                {
                    "success": False,
                    "message": "Не удалось получить access token",
                    "error": error_msg,
                    "error_detail": error_detail
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        access_token = token_result["data"].get("access_token")
        if not access_token:
            return Response(
                {
                    "success": False,
                    "message": "Не удалось получить access token",
                    "error": "Access token не найден в ответе API",
                    "response_data": token_result.get("data")
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        validated_data = serializer.validated_data
        birth_date = validated_data.get("birth_date")
        if birth_date:
            birth_date = birth_date.strftime("%Y-%m-%d")
        
        session_result = create_session(
            access_token=access_token,
            phone_number=validated_data.get("phone_number"),
            birth_date=birth_date,
            pinfl=validated_data.get("pinfl"),
            pass_data=validated_data.get("pass_data")
        )
        
        if not session_result.get("success"):
            return Response(
                {
                    "success": False,
                    "message": "Не удалось создать сессию",
                    "error": session_result.get("error")
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        session_id = session_result["data"].get("session_id")
        
        return Response(
            {
                "success": True,
                "message": "Сессия создана",
                "data": {
                    "session_id": session_id,
                    "access_token": access_token
                }
            },
            status=status.HTTP_200_OK
        )


class VerifyMyIDDataView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['MyID'],
        operation_summary="Получение и верификация данных пользователя через MyID",
        operation_description="""
        Получает данные пользователя из MyID после завершения идентификации в SDK.
        
        **Параметры запроса:**
        - code: Код полученный от SDK после идентификации (query parameter)
        - token: Access token полученный при создании сессии (query parameter)
        - phone_number: Номер телефона пользователя (query parameter, опционально) - используется если My ID не вернул номер
        
        **Процесс:**
        1. Получает данные пользователя из MyID API
        2. Обновляет данные пользователя в базе данных
        3. Отправляет данные в Grist (таблица Counterparties)
        4. Устанавливает is_veriifed_my_id = True
        """,
        manual_parameters=[
            openapi.Parameter(
                'code',
                openapi.IN_QUERY,
                description="Код полученный от SDK",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'token',
                openapi.IN_QUERY,
                description="Access token из сессии",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'phone_number',
                openapi.IN_QUERY,
                description="Номер телефона пользователя (используется если My ID не вернул номер)",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={
            200: openapi.Response(
                description="Данные успешно получены и обновлены",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "Данные успешно обновлены",
                        "data": {
                            "user": {
                                "id": 1,
                                "phone_number": "998901234567",
                                "first_name": "Иван",
                                "last_name": "Иванов"
                            }
                        }
                    }
                }
            ),
            400: openapi.Response(
                description="Ошибка валидации",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Неверные параметры запроса"
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
            ),
            500: openapi.Response(
                description="Ошибка получения данных",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Не удалось получить данные из MyID"
                    }
                }
            )
        }
    )
    def get(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        code = request.query_params.get('code')
        access_token = request.query_params.get('token')
        phone_from_request = request.query_params.get('phone_number')
        
        if not code or not access_token:
            return Response(
                {
                    "success": False,
                    "message": "Неверные параметры запроса. Требуются code и token"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user_data_result = get_user_data(access_token, code)
        
        if not user_data_result.get("success"):
            error = user_data_result.get("error")
            error_detail = user_data_result.get("error_detail", {})
            error_code = error_detail.get("err") if isinstance(error_detail, dict) else None
            error_message = error_detail.get("detail") if isinstance(error_detail, dict) else None
            
            logger.error(f"[VerifyMyIDDataView] Failed to get user data from MyID: {error}")
            logger.error(f"[VerifyMyIDDataView] Error detail: {error_detail}")
            
            if error_code == "AUC001" or (error_message and "Code not found" in str(error_message)):
                user_message = "Код не найден или истек срок действия. Пожалуйста, создайте новую сессию и повторите идентификацию."
            else:
                user_message = "Не удалось получить данные из MyID"
            
            return Response(
                {
                    "success": False,
                    "message": user_message,
                    "error": error,
                    "error_code": error_code,
                    "error_detail": error_message
                },
                status=status.HTTP_400_BAD_REQUEST if error_code == "AUC001" else status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        myid_data = user_data_result.get("data", {})
        profile = myid_data.get("data", {}).get("profile", {})
        common_data = profile.get("common_data", {})
        doc_data = profile.get("doc_data", {})
        contacts = profile.get("contacts", {})
        address_data = profile.get("address", {})
        permanent_registration = address_data.get("permanent_registration", {})
        
        phone = contacts.get("phone", "")
        first_name = common_data.get("first_name", "")
        middle_name = common_data.get("middle_name", "")
        last_name = common_data.get("last_name", "")
        pinfl = common_data.get("pinfl", "")
        birth_date_str = common_data.get("birth_date", "")
        pass_data = doc_data.get("pass_data", "")
        
        address = permanent_registration.get("address", "")
        region = permanent_registration.get("region", "")
        country = permanent_registration.get("country", "")
        district = permanent_registration.get("district", "")
        
        city = None
        street = None
        house = None
        apartment = None
        
        if address:
            address_parts = [part.strip() for part in address.split(',')]
            
            for i, part in enumerate(address_parts):
                if 'дом' in part.lower() or 'дом' in part:
                    house_match = re.search(r'дом\s*(\d+)', part, re.IGNORECASE)
                    if house_match:
                        house = house_match.group(1)
                    
                    apartment_match = re.search(r'квартир[аы]?\s*(\d+)', part, re.IGNORECASE)
                    if apartment_match:
                        apartment = apartment_match.group(1)
                    
                    if i + 1 < len(address_parts):
                        next_part = address_parts[i + 1]
                        apartment_match = re.search(r'квартир[аы]?\s*(\d+)', next_part, re.IGNORECASE)
                        if apartment_match:
                            apartment = apartment_match.group(1)
            
            for i, part in enumerate(address_parts):
                if 'дом' in part.lower() or 'дом' in part:
                    if i > 0:
                        street = address_parts[i - 1]
                    break
            
            if street:
                street_index = address_parts.index(street) if street in address_parts else -1
                if street_index > 0:
                    city = address_parts[street_index - 1]
            
            if not city and district:
                city = district
        
        if phone:
            phone = re.sub(r'[\s\-\+]', '', phone)
        
        if not phone and phone_from_request:
            phone = re.sub(r'[\s\-\+]', '', phone_from_request)
        
        if not phone:
            return Response(
                {
                    "success": False,
                    "message": "Номер телефона не найден в данных MyID и не передан в запросе"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = CustomUser.objects.get(phone_number=phone)
        except CustomUser.DoesNotExist:
            if pinfl:
                try:
                    user = CustomUser.objects.get(pnfl=pinfl)
                    if not user.phone_number or (phone and user.phone_number != phone):
                        user.phone_number = phone
                        user.save()
                except CustomUser.DoesNotExist:
                    return Response(
                        {
                            "success": False,
                            "message": "Пользователь не найден",
                            "debug": {
                                "phone_searched": phone,
                                "pinfl_searched": pinfl
                            }
                        },
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                return Response(
                    {
                        "success": False,
                        "message": "Пользователь не найден. Убедитесь, что вы передали phone_number в запросе или что My ID вернул корректные данные.",
                        "debug": {
                            "phone_searched": phone,
                            "phone_from_request": phone_from_request,
                            "pinfl_available": bool(pinfl),
                            "pass_data_available": bool(pass_data)
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
        
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        if pinfl:
            user.pnfl = pinfl
        if birth_date_str:
            try:
                from datetime import datetime
                birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
                user.date_of_birth = birth_date
            except Exception as e:
                logger.warning(f"[VerifyMyIDDataView] - Failed to parse birth_date '{birth_date_str}': {str(e)}")
        if address:
            user.address = address
        if country:
            user.country = country
        if region:
            user.region = region
        if city:
            user.city = city
        if street:
            user.street = street
        if house:
            user.house = house
        if apartment:
            user.apartment = apartment
        
        user.is_veriifed_my_id = True
        user.save()
        
        phone_for_grist = phone if phone else phone_from_request
        try:
            grist_result = post_to_grist_counterparties(
                first_name=first_name or "",
                last_name=last_name or "",
                middle_name=middle_name or "",
                pinfl=pinfl or "",
                date_of_birth=birth_date_str or "",
                address=address or "",
                phone_number=phone_for_grist or "",
                passport_series=pass_data or ""
            )
            if grist_result:
                logger.info(f"[VerifyMyIDDataView] Data posted to Grist successfully: {grist_result}")
            else:
                logger.warning(f"[VerifyMyIDDataView] Grist post returned None - check API_KEY, DOC_ID, or network")
        except Exception as e:
            logger.error(f"[VerifyMyIDDataView] Error posting to Grist: {str(e)}", exc_info=True)
        
        user_data = UserSerializer(user).data
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        
        return Response(
            {
                "success": True,
                "message": "Данные успешно обновлены",
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


def post_to_grist_counterparties(first_name, last_name, middle_name, pinfl, 
                                  date_of_birth, address, phone_number, passport_series):
    """
    Отправка данных в Grist таблицу Counterparties
    
    Args:
        first_name: Имя
        last_name: Фамилия
        middle_name: Отчество
        pinfl: PINFL
        date_of_birth: Дата рождения
        address: Адрес
        phone_number: Телефон (request body dan keladi)
        passport_series: Серия паспорта
    
    Returns:
        dict: Ответ от Grist API или None при ошибке
    """
    import os
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    API_KEY = os.getenv('ISell_API_KEY')
    DOC_ID = os.getenv('ISell_DOC_ID')
    COUNTERPARTIES_TABLE = os.getenv('ISell_CONTERPARTIES', 'Counterparties')
    
    if not API_KEY or not DOC_ID:
        logger.warning(f"[post_to_grist_counterparties] Missing API_KEY or DOC_ID. API_KEY={bool(API_KEY)}, DOC_ID={bool(DOC_ID)}")
        return None
    
    url = f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{COUNTERPARTIES_TABLE}/records"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    full_name = f"{first_name} {middle_name} {last_name}".strip() if middle_name else f"{first_name} {last_name}".strip()
    
    payload = {
        "records": [
            {
                "fields": {
                    "full_name": full_name,
                    "pinfl": pinfl or "",
                    "address": address or "",
                    "passport_series": passport_series or "",
                    "date_of_birth": date_of_birth or None,
                    "phone1": phone_number or ""
                }
            }
        ]
    }
    
    fields_to_send = {}
    for key, value in payload["records"][0]["fields"].items():
        if value is not None and value != "":
            fields_to_send[key] = value
    
    payload["records"][0]["fields"] = fields_to_send
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"[post_to_grist_counterparties] Successfully posted to Grist: {result}")
        return result
    except requests.exceptions.HTTPError as e:
        error_detail = None
        try:
            error_detail = response.json()
        except:
            error_detail = response.text
        logger.error(f"[post_to_grist_counterparties] HTTP Error: {e}, Status: {response.status_code}, Detail: {error_detail}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"[post_to_grist_counterparties] Request Exception: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"[post_to_grist_counterparties] Unexpected error: {str(e)}", exc_info=True)
        return None


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        tags=['Пользователь'],
        operation_summary="Получение данных пользователя",
        operation_description="""
        Получает данные текущего аутентифицированного пользователя.
        
        **Требуется авторизация:** Bearer Token в заголовке Authorization
        """,
        responses={
            200: openapi.Response(
                description="Данные пользователя",
                examples={
                    "application/json": {
                        "success": True,
                        "data": {
                            "id": 1,
                            "phone_number": "998901234567",
                            "first_name": "Иван",
                            "last_name": "Иванов",
                            "email": "ivan@example.com"
                        }
                    }
                }
            ),
            401: openapi.Response(
                description="Не авторизован",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Не авторизован"
                    }
                }
            )
        }
    )
    def get(self, request):
        """Получить данные текущего пользователя"""
        user = request.user
        serializer = UserSerializer(user)
        return Response(
            {
                "success": True,
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
    
    @swagger_auto_schema(
        tags=['Пользователь'],
        operation_summary="Обновление данных пользователя",
        operation_description="""
        Обновляет данные текущего аутентифицированного пользователя.
        
        **Требуется авторизация:** Bearer Token в заголовке Authorization
        
        **Обновляемые поля:**
        - first_name, last_name, email
        - date_of_birth
        - avatar (изображение)
        - address, city, country, region, street, house, apartment, postal_index
        """,
        request_body=UserUpdateSerializer,
        responses={
            200: openapi.Response(
                description="Данные успешно обновлены",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "Данные успешно обновлены",
                        "data": {
                            "id": 1,
                            "first_name": "Иван",
                            "last_name": "Иванов"
                        }
                    }
                }
            ),
            400: openapi.Response(
                description="Ошибка валидации",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Неверный формат данных",
                        "errors": {}
                    }
                }
            ),
            401: openapi.Response(
                description="Не авторизован"
            )
        }
    )
    def put(self, request):
        """Обновить данные текущего пользователя"""
        user = request.user
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Неверный формат данных",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer.save()
        
        user_serializer = UserSerializer(user)
        return Response(
            {
                "success": True,
                "message": "Данные успешно обновлены",
                "data": user_serializer.data
            },
            status=status.HTTP_200_OK
        )
    
    @swagger_auto_schema(
        tags=['Пользователь'],
        operation_summary="Удаление аккаунта пользователя",
        operation_description="""
        Удаляет аккаунт текущего аутентифицированного пользователя.
        
        **Требуется авторизация:** Bearer Token в заголовке Authorization
        
        **Внимание:** Это действие необратимо!
        """,
        responses={
            200: openapi.Response(
                description="Аккаунт успешно удален",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "Аккаунт успешно удален"
                    }
                }
            ),
            401: openapi.Response(
                description="Не авторизован"
            )
        }
    )
    def delete(self, request):
        """Удалить аккаунт текущего пользователя"""
        user = request.user
        user.delete()
        
        return Response(
            {
                "success": True,
                "message": "Аккаунт успешно удален"
            },
            status=status.HTTP_200_OK
        )
    