from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta
import random
import re
from django.shortcuts import render

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from apps.v1.accounts.models import CustomUser, SmsCode
from apps.v1.accounts.serializers import (
    PhoneLoginSerializer, 
    VerifySMSCodeSerializer,
    UserSerializer,
    MyIDSessionSerializer
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
        
        # Check if user is verified with MyID
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
        
        # Получаем access token
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
        
        # Создаем сессию
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
        
        logger.debug(f"[VerifyMyIDDataView] ========================================")
        logger.debug(f"[VerifyMyIDDataView] ===== REQUEST START =====")
        logger.debug(f"[VerifyMyIDDataView] ========================================")
        
        code = request.query_params.get('code')
        access_token = request.query_params.get('token')
        
        logger.debug(f"[VerifyMyIDDataView] Received parameters:")
        logger.debug(f"[VerifyMyIDDataView] - code: {code}")
        logger.debug(f"[VerifyMyIDDataView] - token: {access_token[:50] if access_token else None}...")
        
        if not code or not access_token:
            logger.warning(f"[VerifyMyIDDataView] Missing parameters: code={code}, token={'present' if access_token else 'missing'}")
            return Response(
                {
                    "success": False,
                    "message": "Неверные параметры запроса. Требуются code и token"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Получаем данные пользователя из MyID
        logger.debug(f"[VerifyMyIDDataView] Calling get_user_data with code={code}")
        user_data_result = get_user_data(access_token, code)
        
        logger.debug(f"[VerifyMyIDDataView] get_user_data result:")
        logger.debug(f"[VerifyMyIDDataView] - success: {user_data_result.get('success')}")
        logger.debug(f"[VerifyMyIDDataView] - status_code: {user_data_result.get('status_code')}")
        logger.debug(f"[VerifyMyIDDataView] - error: {user_data_result.get('error')}")
        
        if not user_data_result.get("success"):
            error = user_data_result.get("error")
            error_detail = user_data_result.get("error_detail", {})
            error_code = error_detail.get("err") if isinstance(error_detail, dict) else None
            error_message = error_detail.get("detail") if isinstance(error_detail, dict) else None
            
            logger.error(f"[VerifyMyIDDataView] Failed to get user data from MyID: {error}")
            logger.error(f"[VerifyMyIDDataView] Error detail: {error_detail}")
            
            # Более понятное сообщение об ошибке
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
        logger.debug(f"[VerifyMyIDDataView] MyID data keys: {list(myid_data.keys())}")
        
        profile = myid_data.get("data", {}).get("profile", {})
        logger.debug(f"[VerifyMyIDDataView] Profile keys: {list(profile.keys())}")
        
        common_data = profile.get("common_data", {})
        doc_data = profile.get("doc_data", {})
        contacts = profile.get("contacts", {})
        address_data = profile.get("address", {})
        permanent_registration = address_data.get("permanent_registration", {})
        
        logger.debug(f"[VerifyMyIDDataView] Extracted data:")
        logger.debug(f"[VerifyMyIDDataView] - contacts: {contacts}")
        logger.debug(f"[VerifyMyIDDataView] - common_data: {common_data}")
        logger.debug(f"[VerifyMyIDDataView] - doc_data: {doc_data}")
        
        # Извлекаем данные
        phone = contacts.get("phone", "")
        first_name = common_data.get("first_name", "")
        middle_name = common_data.get("middle_name", "")
        last_name = common_data.get("last_name", "")
        pinfl = common_data.get("pinfl", "")
        birth_date_str = common_data.get("birth_date", "")
        pass_data = doc_data.get("pass_data", "")
        
        logger.debug(f"[VerifyMyIDDataView] Extracted values:")
        logger.debug(f"[VerifyMyIDDataView] - phone (raw): {phone}")
        logger.debug(f"[VerifyMyIDDataView] - first_name: {first_name}")
        logger.debug(f"[VerifyMyIDDataView] - last_name: {last_name}")
        logger.debug(f"[VerifyMyIDDataView] - pinfl: {pinfl}")
        logger.debug(f"[VerifyMyIDDataView] - birth_date: {birth_date_str}")
        logger.debug(f"[VerifyMyIDDataView] - pass_data: {pass_data}")
        
        # Адрес
        address = permanent_registration.get("address", "")
        region = permanent_registration.get("region", "")
        country = permanent_registration.get("country", "")
        
        # Нормализуем номер телефона (удаляем пробелы, дефисы, плюсы)
        phone_original = phone
        if phone:
            phone = re.sub(r'[\s\-\+]', '', phone)
            logger.debug(f"[VerifyMyIDDataView] Phone normalized: '{phone_original}' -> '{phone}'")
        
        if not phone:
            logger.warning(f"[VerifyMyIDDataView] Phone number is empty after extraction")
            return Response(
                {
                    "success": False,
                    "message": "Номер телефона не найден в данных MyID"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Ищем пользователя по номеру телефона
        logger.debug(f"[VerifyMyIDDataView] Searching for user with phone_number='{phone}'")
        try:
            user = CustomUser.objects.get(phone_number=phone)
            logger.debug(f"[VerifyMyIDDataView] User found by phone_number: user_id={user.id}, username={user.username}")
        except CustomUser.DoesNotExist:
            logger.warning(f"[VerifyMyIDDataView] User not found by phone_number='{phone}'")
            # Пробуем найти пользователя по PINFL, если номер телефона не найден
            if pinfl:
                logger.debug(f"[VerifyMyIDDataView] Trying to find user by PINFL='{pinfl}'")
                try:
                    user = CustomUser.objects.get(pnfl=pinfl)
                    logger.debug(f"[VerifyMyIDDataView] User found by PINFL: user_id={user.id}, username={user.username}, phone_number={user.phone_number}")
                    # Обновляем номер телефона, если он был пустым
                    if not user.phone_number:
                        logger.debug(f"[VerifyMyIDDataView] Updating user phone_number from None to '{phone}'")
                        user.phone_number = phone
                        user.save()
                except CustomUser.DoesNotExist:
                    logger.error(f"[VerifyMyIDDataView] User not found by PINFL='{pinfl}' either")
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
                logger.error(f"[VerifyMyIDDataView] PINFL not available, cannot search by PINFL")
                return Response(
                    {
                        "success": False,
                        "message": "Пользователь не найден",
                        "debug": {
                            "phone_searched": phone
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Обновляем данные пользователя
        logger.debug(f"[VerifyMyIDDataView] Updating user data...")
        if first_name:
            user.first_name = first_name
            logger.debug(f"[VerifyMyIDDataView] - Updated first_name: {first_name}")
        if last_name:
            user.last_name = last_name
            logger.debug(f"[VerifyMyIDDataView] - Updated last_name: {last_name}")
        if pinfl:
            user.pnfl = pinfl
            logger.debug(f"[VerifyMyIDDataView] - Updated pnfl: {pinfl}")
        if birth_date_str:
            try:
                from datetime import datetime
                birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
                user.date_of_birth = birth_date
                logger.debug(f"[VerifyMyIDDataView] - Updated date_of_birth: {birth_date}")
            except Exception as e:
                logger.warning(f"[VerifyMyIDDataView] - Failed to parse birth_date '{birth_date_str}': {str(e)}")
        if address:
            user.address = address
            logger.debug(f"[VerifyMyIDDataView] - Updated address: {address}")
        if country:
            user.country = country
            logger.debug(f"[VerifyMyIDDataView] - Updated country: {country}")
        if region:
            user.region = region
            logger.debug(f"[VerifyMyIDDataView] - Updated region: {region}")
        
        # Устанавливаем флаг верификации
        user.is_veriifed_my_id = True
        logger.debug(f"[VerifyMyIDDataView] - Setting is_veriifed_my_id = True")
        user.save()
        logger.debug(f"[VerifyMyIDDataView] User saved successfully")
        
        # Отправляем данные в Grist
        logger.debug(f"[VerifyMyIDDataView] Posting data to Grist...")
        try:
            post_to_grist_counterparties(
                first_name=first_name or "",
                last_name=last_name or "",
                middle_name=middle_name or "",
                pinfl=pinfl or "",
                date_of_birth=birth_date_str or "",
                address=address or "",
                phone=phone or "",
                passport_series=pass_data or ""
            )
            logger.debug(f"[VerifyMyIDDataView] Data posted to Grist successfully")
        except Exception as e:
            logger.error(f"[VerifyMyIDDataView] Error posting to Grist: {str(e)}")
        
        user_data = UserSerializer(user).data
        
        logger.debug(f"[VerifyMyIDDataView] ===== REQUEST SUCCESS =====")
        logger.debug(f"[VerifyMyIDDataView] Returning user data for user_id={user.id}")
        logger.debug(f"[VerifyMyIDDataView] ========================================")
        
        return Response(
            {
                "success": True,
                "message": "Данные успешно обновлены",
                "data": {
                    "user": user_data
                }
            },
            status=status.HTTP_200_OK
        )


def post_to_grist_counterparties(first_name, last_name, middle_name, pinfl, 
                                  date_of_birth, address, phone, passport_series):
    """
    Отправка данных в Grist таблицу Counterparties
    
    Args:
        first_name: Имя
        last_name: Фамилия
        middle_name: Отчество
        pinfl: PINFL
        date_of_birth: Дата рождения
        address: Адрес
        phone: Телефон
        passport_series: Серия паспорта
    """
    import os
    import requests
    
    API_KEY = os.getenv('ISell_API_KEY')
    DOC_ID = os.getenv('ISell_DOC_ID')
    COUNTERPARTIES_TABLE = os.getenv('ISell_CONTERPARTIES', 'Counterparties')
    
    if not API_KEY or not DOC_ID:
        return None
    
    url = f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{COUNTERPARTIES_TABLE}/records"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Формируем полное имя
    full_name = f"{first_name} {middle_name} {last_name}".strip() if middle_name else f"{first_name} {last_name}".strip()
    
    payload = {
        "records": [
            {
                "fields": {
                    "name": full_name,
                    "pinfl": pinfl,
                    "address": address,
                    "passport_series": passport_series,
                    "date_of_birth": date_of_birth,
                    "phone": phone
                }
            }
        ]
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return None
    