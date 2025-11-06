from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.shortcuts import get_object_or_404
from datetime import datetime, timedelta
from calendar import monthrange
from django.db import transaction

from apps.v1.order.integrations.order_list import get_tariffs
from apps.v1.order.models import Tariffs, Orders, OrderItems, OrderPaymentSchedule, OrderCaluculationMode, CompanyAddress
from apps.v1.order.serializers import TariffsSerializer, OrdersSerializer, CompanyAddressSerializer
from apps.v1.products.models import Products


class ImportTariffsView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Импорт'],
        operation_description="Импорт тарифов",
        responses={
            200: openapi.Response(
                description="Тарифы импортированы успешно",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(type=openapi.TYPE_STRING, description="Сообщение о результате импорта")
                    }
                )
            )
        }
    )
    def get(self, request):
        result = get_tariffs()
        return Response({"message": "Тарифы импортированы успешно"}, status=status.HTTP_200_OK)


class TariffsListView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Тарифы'],
        operation_summary="Получить список тарифов",
        operation_description="Получить список всех активных тарифов с возможностью поиска по названию",
        manual_parameters=[
            openapi.Parameter(
                'name',
                openapi.IN_QUERY,
                description="Поиск по названию тарифа (частичное совпадение)",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={
            200: openapi.Response(
                description="Список тарифов",
                schema=TariffsSerializer(many=True)
            )
        }
    )
    def get(self, request):
        tariffs = Tariffs.objects.filter(is_active=True)
        
        name = request.query_params.get('name', None)
        if name:
            tariffs = tariffs.filter(name__icontains=name)
        
        tariffs = tariffs.order_by('-created_at')
        serializer = TariffsSerializer(tariffs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        tags=['Заказы'],
        operation_summary="Создать заказ",
        operation_description="""
        Создает заказ с товарами и графиком платежей.
        
        **Режимы расчета:**
        - Mode 1: Общий первоначальный взнос и период рассрочки для всех продуктов
        - Mode 2: Индивидуальный первоначальный взнос и период рассрочки для каждого продукта
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['calculation_mode', 'product_list'],
            properties={
                'calculation_mode': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Режим расчета (1 или 2)',
                    enum=[1, 2]
                ),
                'total_down_payment': openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    description='Общий первоначальный взнос (только для mode 1)'
                ),
                'installment_period': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='ID тарифа (только для mode 1)'
                ),
                'product_list': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    description='Список продуктов',
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'product_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'installment_period': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID тарифа (только для mode 2)'),
                            'total_down_payment': openapi.Schema(type=openapi.TYPE_NUMBER, description='Первоначальный взнос (только для mode 2)'),
                        }
                    )
                ),
            }
        ),
        responses={
            201: openapi.Response(
                description="Заказ создан успешно",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'user': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'user_name': openapi.Schema(type=openapi.TYPE_STRING),
                        'order_calculation_mode': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'calculation_mode_name': openapi.Schema(type=openapi.TYPE_STRING),
                        'status': openapi.Schema(type=openapi.TYPE_STRING),
                        'company_address': openapi.Schema(type=openapi.TYPE_INTEGER, nullable=True),
                        'address': openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
                        'latitude': openapi.Schema(type=openapi.TYPE_NUMBER, nullable=True),
                        'longitude': openapi.Schema(type=openapi.TYPE_NUMBER, nullable=True),
                        'items': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'product': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'product_name': openapi.Schema(type=openapi.TYPE_STRING),
                                    'tariff': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'tariff_name': openapi.Schema(type=openapi.TYPE_STRING),
                                    'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'price': openapi.Schema(type=openapi.TYPE_NUMBER),
                                    'down_payment': openapi.Schema(type=openapi.TYPE_NUMBER),
                                }
                            )
                        ),
                        'monthly_payments': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description='Объединенный график платежей по всем товарам',
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'month_number': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'date': openapi.Schema(type=openapi.TYPE_STRING),
                                    'monthly_payment': openapi.Schema(type=openapi.TYPE_NUMBER)
                                }
                            )
                        ),
                        'created_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                        'updated_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                    }
                )
            ),
            400: "Неверные данные запроса",
            404: "Продукт или тариф не найден"
        }
    )
    @transaction.atomic
    def post(self, request):
        calculation_mode = request.data.get('calculation_mode')
        product_list = request.data.get('product_list', [])
        
        if calculation_mode is None:
            return Response(
                {"error": "Поле 'calculation_mode' обязательно"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not product_list:
            return Response(
                {"error": "Поле 'product_list' обязательно и не может быть пустым"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if calculation_mode not in [1, 2]:
            return Response(
                {"error": "calculation_mode должен быть 1 или 2"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order_calculation_mode = get_object_or_404(OrderCaluculationMode, id=calculation_mode)
        
        order = Orders.objects.create(
            user=request.user,
            order_calculation_mode=order_calculation_mode,
            status='pending'
        )
        
        if calculation_mode == 1:
            total_down_payment = request.data.get('total_down_payment')
            installment_period = request.data.get('installment_period')
            
            if total_down_payment is None:
                return Response(
                    {"error": "Поле 'total_down_payment' обязательно для режима 1"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if installment_period is None:
                return Response(
                    {"error": "Поле 'installment_period' обязательно для режима 1"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            tariff = get_object_or_404(Tariffs, id=installment_period)
            
            total_product_sum = 0
            products_data = []
            for item in product_list:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 1)
                
                product = get_object_or_404(Products, id=product_id)
                product_total = float(product.price) * quantity
                total_product_sum += product_total
                products_data.append({
                    'product': product,
                    'quantity': quantity,
                    'product_total': product_total
                })
            
            for prod_data in products_data:
                product = prod_data['product']
                quantity = prod_data['quantity']
                product_total = prod_data['product_total']
                
                product_proportion = product_total / total_product_sum if total_product_sum > 0 else 0
                product_down_payment = float(total_down_payment) * product_proportion
                product_remaining = product_total - product_down_payment
                
                monthly_payment_amount = round(
                    product_remaining * (tariff.coefficient / tariff.payments_count)
                )
                
                order_item = OrderItems.objects.create(
                    order=order,
                    product=product,
                    tariff=tariff,
                    quantity=quantity,
                    price=product.price,
                    down_payment=product_down_payment
                )
                
                current_date = datetime.now()
                
                for month_num in range(1, tariff.payments_count + 1):
                    year = current_date.year
                    month = current_date.month + month_num
                    day = current_date.day
                    
                    while month > 12:
                        month -= 12
                        year += 1
                    
                    max_day = monthrange(year, month)[1]
                    if day > max_day:
                        day = max_day
                    
                    payment_date = datetime(year, month, day)
                    
                    if tariff.offset_days:
                        payment_date = payment_date + timedelta(days=tariff.offset_days)
                    
                    OrderPaymentSchedule.objects.create(
                        order_item=order_item,
                        month_number=month_num,
                        payment_date=payment_date.date(),
                        monthly_payment_amount=monthly_payment_amount
                    )
        
        elif calculation_mode == 2:
            for item in product_list:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 1)
                item_down_payment = item.get('total_down_payment', 0)
                item_installment_period = item.get('installment_period')
                
                if item_installment_period is None:
                    continue
                
                product = get_object_or_404(Products, id=product_id)
                tariff = get_object_or_404(Tariffs, id=item_installment_period)
                
                order_item = OrderItems.objects.create(
                    order=order,
                    product=product,
                    tariff=tariff,
                    quantity=quantity,
                    price=product.price,
                    down_payment=item_down_payment
                )
                
                product_total = float(product.price) * quantity
                product_remaining = product_total - float(item_down_payment)
                
                monthly_payment_amount = round(
                    product_remaining * (tariff.coefficient / tariff.payments_count)
                )
                
                current_date = datetime.now()
                
                for month_num in range(1, tariff.payments_count + 1):
                    year = current_date.year
                    month = current_date.month + month_num
                    day = current_date.day
                    
                    while month > 12:
                        month -= 12
                        year += 1
                    
                    max_day = monthrange(year, month)[1]
                    if day > max_day:
                        day = max_day
                    
                    payment_date = datetime(year, month, day)
                    
                    if tariff.offset_days:
                        payment_date = payment_date + timedelta(days=tariff.offset_days)
                    
                    OrderPaymentSchedule.objects.create(
                        order_item=order_item,
                        month_number=month_num,
                        payment_date=payment_date.date(),
                        monthly_payment_amount=monthly_payment_amount
                    )
        
        order_with_items = Orders.objects.prefetch_related(
            'items__payment_schedule',
            'items__product',
            'items__tariff'
        ).get(id=order.id)
        
        serializer = OrdersSerializer(order_with_items)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CompanyAddressListView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Адреса компании'],
        operation_summary="Получить список адресов компании",
        operation_description="Получить список всех доступных адресов компании",
        responses={
            200: openapi.Response(
                description="Список адресов компании",
                schema=CompanyAddressSerializer(many=True)
            )
        }
    )
    def get(self, request):
        company_addresses = CompanyAddress.objects.all().order_by('-created_at')
        serializer = CompanyAddressSerializer(company_addresses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateOrderAddressView(APIView):
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        tags=['Заказы'],
        operation_summary="Обновить адрес заказа",
        operation_description="""
        Обновить адрес заказа двумя способами:
        1. Выбрать адрес компании (company_id)
        2. Указать пользовательский адрес (address, latitude, longitude)
        
        Примечание: Если указан company_id, пользовательский адрес будет удален.
        Если указан пользовательский адрес, company_address будет удален.
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['order_id'],
            properties={
                'order_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='ID заказа'
                ),
                'company_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='ID адреса компании (используйте только один вариант)'
                ),
                'address': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Пользовательский адрес (используйте только один вариант)'
                ),
                'latitude': openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    description='Широта (обязательно с address)'
                ),
                'longitude': openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    description='Долгота (обязательно с address)'
                ),
            }
        ),
        responses={
            200: openapi.Response(
                description="Адрес заказа обновлен успешно",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'user': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'user_name': openapi.Schema(type=openapi.TYPE_STRING),
                        'order_calculation_mode': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'calculation_mode_name': openapi.Schema(type=openapi.TYPE_STRING),
                        'status': openapi.Schema(type=openapi.TYPE_STRING),
                        'company_address': openapi.Schema(type=openapi.TYPE_INTEGER, nullable=True),
                        'company_address_details': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            nullable=True,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'name': openapi.Schema(type=openapi.TYPE_STRING),
                                'address': openapi.Schema(type=openapi.TYPE_STRING),
                                'latitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'longitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                            }
                        ),
                        'address': openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
                        'latitude': openapi.Schema(type=openapi.TYPE_NUMBER, nullable=True),
                        'longitude': openapi.Schema(type=openapi.TYPE_NUMBER, nullable=True),
                        'items': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'product': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'product_name': openapi.Schema(type=openapi.TYPE_STRING),
                                    'tariff': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'tariff_name': openapi.Schema(type=openapi.TYPE_STRING),
                                    'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'price': openapi.Schema(type=openapi.TYPE_NUMBER),
                                    'down_payment': openapi.Schema(type=openapi.TYPE_NUMBER),
                                }
                            )
                        ),
                        'monthly_payments': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description='Объединенный график платежей по всем товарам',
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'month_number': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'date': openapi.Schema(type=openapi.TYPE_STRING),
                                    'monthly_payment': openapi.Schema(type=openapi.TYPE_NUMBER)
                                }
                            )
                        ),
                        'created_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                        'updated_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                    }
                )
            ),
            400: "Неверные данные запроса",
            404: "Заказ или адрес компании не найден"
        }
    )
    def patch(self, request):
        order_id = request.data.get('order_id')
        company_id = request.data.get('company_id')
        address = request.data.get('address')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        if not order_id:
            return Response(
                {"error": "Поле 'order_id' обязательно"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order = get_object_or_404(Orders, id=order_id, user=request.user)
        
        if company_id:
            company_address = get_object_or_404(CompanyAddress, id=company_id)
            order.company_address = company_address
            order.address = None
            order.latitude = None
            order.longitude = None
            order.save()
        
        elif address or latitude or longitude:
            if not address or latitude is None or longitude is None:
                return Response(
                    {"error": "Для пользовательского адреса необходимо указать address, latitude и longitude"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            order.company_address = None
            order.address = address
            order.latitude = latitude
            order.longitude = longitude
            order.save()
        
        else:
            return Response(
                {"error": "Необходимо указать company_id или пользовательский адрес (address, latitude, longitude)"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order_with_items = Orders.objects.prefetch_related(
            'items__payment_schedule',
            'items__product',
            'items__tariff',
            'company_address'
        ).get(id=order.id)
        
        serializer = OrdersSerializer(order_with_items)
        return Response(serializer.data, status=status.HTTP_200_OK)
