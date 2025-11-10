from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from django.shortcuts import get_object_or_404
from datetime import datetime, timedelta
from calendar import monthrange

from apps.v1.products.models import Products, ProductDetails, ProductCategory
from apps.v1.order.models import Tariffs, OrderCaluculationMode
from apps.v1.products.serializers import ProductsSerializer, ProductDetailFilterSerializer, ProductImagesSerializer, CategoriesSerializer
from apps.v1.order.integrations.advanced_payment_assessment import get_application, get_products_in_grist
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import AllowAny




class ProductPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProductListView(APIView):
    permission_classes = [AllowAny]
    pagination_class = ProductPagination
    
    @swagger_auto_schema(
        tags=['Продукты'],
        operation_summary="Список продуктов",
        operation_description="Список продуктов с фильтрацией и пагинацией",
        manual_parameters=[
            openapi.Parameter(
                'name',
                openapi.IN_QUERY,
                description="Фильтр по названию продукта (частичный поиск)",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'category',
                openapi.IN_QUERY,
                description="Фильтр по ID категории",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'page',
                openapi.IN_QUERY,
                description="Номер страницы",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'page_size',
                openapi.IN_QUERY,
                description="Количество элементов на странице (по умолчанию 10, максимум 100)",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description="Список продуктов", 
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "count": openapi.Schema(type=openapi.TYPE_INTEGER, description="Общее количество продуктов"),
						"total_pages": openapi.Schema(type=openapi.TYPE_INTEGER, description="Общее количество страниц"),
                        "next": openapi.Schema(type=openapi.TYPE_STRING, description="Ссылка на следующую страницу"),
                        "previous": openapi.Schema(type=openapi.TYPE_STRING, description="Ссылка на предыдущую страницу"),
                        "results": openapi.Schema(
                            type=openapi.TYPE_ARRAY, 
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT, 
                                properties={
                                    "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID продукта"),
                                    "name": openapi.Schema(type=openapi.TYPE_STRING, description="Название продукта"),
                                    "category": openapi.Schema(type=openapi.TYPE_OBJECT, description="Категория"),
                                    "price": openapi.Schema(type=openapi.TYPE_NUMBER, description="Цена"),
                                    "battery_capacity": openapi.Schema(type=openapi.TYPE_STRING, description="Емкость аккумулятора"),
                                    "processor": openapi.Schema(type=openapi.TYPE_STRING, description="Процессор"),
                                    "screen_name": openapi.Schema(type=openapi.TYPE_STRING, description="Название экрана"),
                                    "details": openapi.Schema(
                                        type=openapi.TYPE_ARRAY, 
                                        description="Детали продукта",
                                        items=openapi.Schema(type=openapi.TYPE_OBJECT)
                                    ),
                                    "images": openapi.Schema(
                                        type=openapi.TYPE_ARRAY, 
                                        description="Изображения продукта",
                                        items=openapi.Schema(type=openapi.TYPE_OBJECT)
                                    ),
                                }
                            )
                        )
                    }
                )
            )
        }
    )
    def get(self, request):
        name = request.query_params.get('name', None)
        category = request.query_params.get('category', None)
        
        queryset = Products.objects.select_related('category').prefetch_related('details', 'images', 'characteristics__property').all()
        
        if name:
            queryset = queryset.filter(name__icontains=name)
        
        if category:
            queryset = queryset.filter(category_id=category)
        
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        
        serializer = ProductsSerializer(paginated_queryset, many=True, context={'request': request})
        
        response = paginator.get_paginated_response(serializer.data)
        response.data['total_pages'] = paginator.page.paginator.num_pages
        return response
        

class ProductDetailView(APIView):
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        tags=['Продукты'],
        operation_summary="Детальная информация о продукте",
        operation_description="Детальная информация о продукте",
        responses={
            200: openapi.Response(
                description="Детальная информация о продукте", 
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT, 
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID продукта"),
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Название продукта"),
                        "category": openapi.Schema(type=openapi.TYPE_OBJECT, description="Категория"),
                        "price": openapi.Schema(type=openapi.TYPE_NUMBER, description="Цена"),
                        "battery_capacity": openapi.Schema(type=openapi.TYPE_STRING, description="Емкость аккумулятора"),
                        "processor": openapi.Schema(type=openapi.TYPE_STRING, description="Процессор"),
                        "screen_name": openapi.Schema(type=openapi.TYPE_STRING, description="Название экрана"),
                        "details": openapi.Schema(
                            type=openapi.TYPE_ARRAY, 
                            description="Детали продукта",
                            items=openapi.Schema(type=openapi.TYPE_OBJECT)
                        ),
                        "images": openapi.Schema(
                            type=openapi.TYPE_ARRAY, 
                            description="Изображения продукта",
                            items=openapi.Schema(type=openapi.TYPE_OBJECT)
                        ),
                    }
                )
            )
        }
    )
    def get(self, request, product_id):
        product = Products.objects.select_related('category').prefetch_related('details', 'images', 'characteristics__property').get(id=product_id)
        serializer = ProductsSerializer(product, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProductDetailFilterView(APIView):
    """
    Cascading filter view for product details.
    Returns color_list, storage_list, and sim_card_list based on selected filters.
    """
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Продукты'],
        operation_summary="Фильтрованные детали продукта (Cascading Filter)",
        operation_description="""
        Cascading filter для выбора color, storage и sim_card.
        
        **Логика работы:**
        1. Без фильтров: возвращает ВСЕ доступные colors, storages и sim_cards (все distinct, все is_active=false)
        2. С color_name: возвращает все colors (выбранный is_active=true), доступные storage для этого color, и доступные sim_cards для этого color
        3. С color_name и storage_name: возвращает все colors, доступные storage для color (выбранный is_active=true), и доступные sim_cards для этой комбинации
        4. С color_name, storage_name и sim_card_name: возвращает все с соответствующими is_active=true
        
        **Параметры:**
        - color_name: фильтр по цвету (опционально)
        - storage_name: фильтр по памяти (опционально, требует color_name)
        - sim_card_name: фильтр по типу SIM-карты (опционально, требует color_name и storage_name)
        """,
        manual_parameters=[
            openapi.Parameter(
                'color_name',
                openapi.IN_QUERY,
                description="Фильтр по цвету (например: White, Black)",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'storage_name',
                openapi.IN_QUERY,
                description="Фильтр по памяти (например: 256GB, 512GB)",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'sim_card_name',
                openapi.IN_QUERY,
                description="Фильтр по SIM-карте (например: Dual SIM, SIM + eSIM)",
                type=openapi.TYPE_STRING,
                required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description="Фильтрованные детали продукта",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID продукта"),
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Название продукта"),
                        "category": openapi.Schema(type=openapi.TYPE_OBJECT, description="Категория"),
                        "price": openapi.Schema(type=openapi.TYPE_NUMBER, description="Цена"),
                        "battery_capacity": openapi.Schema(type=openapi.TYPE_STRING, description="Емкость аккумулятора"),
                        "processor": openapi.Schema(type=openapi.TYPE_STRING, description="Процессор"),
                        "screen_name": openapi.Schema(type=openapi.TYPE_STRING, description="Название экрана"),
                        "images": openapi.Schema(
                            type=openapi.TYPE_ARRAY, 
                            description="Изображения продукта",
                            items=openapi.Schema(type=openapi.TYPE_OBJECT)
                        ),
                        "color_list": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description="Список доступных цветов",
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                    "color_name": openapi.Schema(type=openapi.TYPE_STRING)
                                }
                            )
                        ),
                        "storage_list": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description="Список доступных вариантов памяти",
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                    "storage_name": openapi.Schema(type=openapi.TYPE_STRING)
                                }
                            )
                        ),
                        "sim_card_list": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description="Список доступных типов SIM-карт",
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                    "sim_card_name": openapi.Schema(type=openapi.TYPE_STRING)
                                }
                            )
                        ),
                        "characteristics": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description="Характеристики продукта, сгруппированные по свойствам",
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "name_property": openapi.Schema(type=openapi.TYPE_STRING, description="Название свойства"),
                                    "details": openapi.Schema(
                                        type=openapi.TYPE_ARRAY,
                                        description="Детали свойства",
                                        items=openapi.Schema(
                                            type=openapi.TYPE_OBJECT,
                                            properties={
                                                "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID характеристики"),
                                                "value": openapi.Schema(type=openapi.TYPE_STRING, description="Значение характеристики")
                                            }
                                        )
                                    )
                                }
                            )
                        ),
                    }
                )
            ),
            404: "Продукт не найден"
        }
    )
    def get(self, request, product_id):
        try:
            product = Products.objects.select_related('category').prefetch_related('images', 'details', 'characteristics__property').get(id=product_id)
        except Products.DoesNotExist:
            return Response(
                {"error": "Продукт не найден"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        color_name = request.query_params.get('color_name', None)
        storage_name = request.query_params.get('storage_name', None)
        sim_card_name = request.query_params.get('sim_card_name', None)
        
        all_details = product.details.all()
        
        all_colors = all_details.values_list('color', flat=True).distinct()
        color_list = [
            {
                "is_active": color == color_name if color_name else False,
                "color_name": color
            }
            for color in all_colors if color
        ]
        
        storage_list = []
        sim_card_list = []
        
        if color_name:
            color_details = all_details.filter(color=color_name)
            
            storages = color_details.values_list('storage', flat=True).distinct()
            storage_list = [
                {
                    "is_active": storage == storage_name if storage_name else False,
                    "storage_name": storage
                }
                for storage in storages if storage
            ]
            
            sim_cards = color_details.values_list('sim_card', flat=True).distinct()
            sim_card_list = [
                {
                    "is_active": False,
                    "sim_card_name": sim_card
                }
                for sim_card in sim_cards if sim_card
            ]
            
            if storage_name:
                color_storage_details = color_details.filter(storage=storage_name)
                
                sim_cards = color_storage_details.values_list('sim_card', flat=True).distinct()
                sim_card_list = [
                    {
                        "is_active": sim_card == sim_card_name if sim_card_name else False,
                        "sim_card_name": sim_card
                    }
                    for sim_card in sim_cards if sim_card
                ]
        else:
            all_storages = all_details.values_list('storage', flat=True).distinct()
            storage_list = [
                {
                    "is_active": False,
                    "storage_name": storage
                }
                for storage in all_storages if storage
            ]
            
            all_sim_cards = all_details.values_list('sim_card', flat=True).distinct()
            sim_card_list = [
                {
                    "is_active": False,
                    "sim_card_name": sim_card
                }
                for sim_card in all_sim_cards if sim_card
            ]
        
        characteristics_data = []
        characteristics_qs = product.characteristics.select_related('property').all()
        
        property_groups = {}
        for char in characteristics_qs:
            property_name = char.property.name
            if property_name not in property_groups:
                property_groups[property_name] = []
            property_groups[property_name].append({
                "id": char.id,
                "value": char.value
            })
        
        for property_name, details in property_groups.items():
            characteristics_data.append({
                "name_property": property_name,
                "details": details
            })
        
        response_data = {
            "id": product.id,
            "name": product.name,
            "category": CategoriesSerializer(product.category).data,
            "price": product.price,
            "battery_capacity": product.battery_capacity,
            "processor": product.processor,
            "screen_name": product.screen_name,
            "images": ProductImagesSerializer(product.images.all(), many=True , context={'request': request}).data,
            "color_list": color_list,
            "storage_list": storage_list,
            "sim_card_list": sim_card_list,
            "characteristics": characteristics_data,
        }
        
        return Response(response_data, status=status.HTTP_200_OK)


class CalculateMonthlyPaymentView(APIView):
    """
    View for calculating monthly payment based on product price, down payment, and tariff.
    """
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Продукты'],
        operation_summary="Расчет ежемесячного платежа",
        operation_description="""
        Рассчитывает ежемесячный платеж на основе цены продукта, первоначального взноса и выбранного тарифа.
        
        **Формула:**
        monthly_payment = round((product.price - total_down_payment) * (tariff.coefficient / tariff.payments_count))
        """,
        manual_parameters=[
            openapi.Parameter(
                'total_down_payment',
                openapi.IN_QUERY,
                description="Сумма первоначального взноса",
                type=openapi.TYPE_NUMBER,
                required=True
            ),
            openapi.Parameter(
                'installment_period',
                openapi.IN_QUERY,
                description="ID тарифа (срок рассрочки)",
                type=openapi.TYPE_INTEGER,
                required=True
            ),
        ],
        responses={
            200: openapi.Response(
                description="Рассчитанный ежемесячный платеж",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "product_price": openapi.Schema(type=openapi.TYPE_NUMBER, description="Цена продукта"),
                            "monthly_payment": openapi.Schema(type=openapi.TYPE_NUMBER, description="Ежемесячный платеж")
                        }
                    )
                )
            ),
            400: "Неверные данные запроса",
            404: "Продукт или тариф не найден"
        }
    )
    def get(self, request, product_id):
        total_down_payment = request.query_params.get('total_down_payment')
        installment_period = request.query_params.get('installment_period')
        
        if total_down_payment is None:
            return Response(
                {"error": "Поле 'total_down_payment' обязательно"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if installment_period is None:
            return Response(
                {"error": "Поле 'installment_period' обязательно"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        product = get_object_or_404(Products, id=product_id)
        tariff = get_object_or_404(Tariffs, id=installment_period)
        
        monthly_payment = round(
            (float(product.price) - float(total_down_payment)) * 
            (tariff.coefficient / tariff.payments_count)
        )
        
        response_data = [
            {
                "product_price": product.price,
                "monthly_payment": monthly_payment
            }
        ]
        
        return Response(response_data, status=status.HTTP_200_OK)


class CalculatePaymentScheduleView(APIView):
    """
    View for calculating payment schedule based on calculation mode.
    """
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Продукты'],
        operation_summary="Расчет графика платежей",
        operation_description="""
        Рассчитывает график платежей на основе режима расчета.
        
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
            200: openapi.Response(
                description="График платежей",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "total_price": openapi.Schema(type=openapi.TYPE_NUMBER, description="Общая цена после вычета первоначального взноса"),
                        "total_down_payment": openapi.Schema(type=openapi.TYPE_NUMBER, description="Первоначальный взнос"),
                        "total_every_month_payment": openapi.Schema(type=openapi.TYPE_NUMBER, description="Ежемесячный платеж"),
                        "minimum_contribution": openapi.Schema(type=openapi.TYPE_NUMBER, description="Минимальный взнос"),
                        "ability_to_order": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Возможность оформить заказ (true если minimum_contribution <= total_down_payment)"),
                        "monthly_payments": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "month_number": openapi.Schema(type=openapi.TYPE_INTEGER),
                                    "date": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                                    "monthly_payment": openapi.Schema(type=openapi.TYPE_NUMBER)
                                }
                            )
                        )
                    }
                )
            ),
            400: "Неверные данные запроса",
            404: "Режим расчета, продукт или тариф не найден"
        }
    )
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
        
        monthly_payments = []
        
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
                total_product_sum += float(product.price) * quantity
                products_data.append({
                    'product': product,
                    'quantity': quantity
                })
            
            original_total_product_sum = total_product_sum
            total_product_sum = total_product_sum - float(total_down_payment)
            
            monthly_payment_amount = round(
                total_product_sum * (tariff.coefficient / tariff.payments_count)
            )
            
            minimum_contribution = 0
            try:
                application_data = get_application()
                applications = application_data.get('records', [])
                
                grist_products_data = get_products_in_grist()
                grist_products = grist_products_data.get('records', [])
                
                grist_product_map = {}
                for grist_product in grist_products:
                    grist_id = grist_product.get('id')
                    price_category_id = grist_product.get('fields', {}).get('price_category_id')
                    if grist_id and price_category_id:
                        grist_product_map[grist_id] = price_category_id
                
                risk_category_id = None
                for app in applications:
                    app_products = app.get('fields', {}).get('products', [])
                    for prod_data in products_data:
                        grist_product_id = prod_data['product'].grist_product_id
                        if grist_product_id:
                            try:
                                grist_product_id = int(grist_product_id)
                            except (ValueError, TypeError):
                                continue
                        if grist_product_id and grist_product_id in app_products:
                            risk_category_id = app.get('fields', {}).get('risk_category_id')
                            break
                    if risk_category_id:
                        break
                
                for prod_data in products_data:
                    product = prod_data['product']
                    quantity = prod_data['quantity']
                    grist_product_id = product.grist_product_id
                    
                    if grist_product_id:
                        try:
                            grist_product_id = int(grist_product_id)
                        except (ValueError, TypeError):
                            continue
                    
                    if grist_product_id and grist_product_id in grist_product_map:
                        price_category_id = grist_product_map[grist_product_id]
                        
                        if risk_category_id and price_category_id:
                            try:
                                product_category = ProductCategory.objects.get(
                                    grist_risk_category_id=str(risk_category_id),
                                    grist_price_category_id=str(price_category_id)
                                )
                                percentage = product_category.percentage or 0
                                product_price = float(product.price) * quantity
                                minimum_contribution += product_price * percentage
                            except ProductCategory.DoesNotExist:
                                pass
            except Exception as e:
                minimum_contribution = 0
            
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
                
                monthly_payments.append({
                    "month_number": month_num,
                    "date": payment_date.strftime("%d/%m/%y"),
                    "monthly_payment": monthly_payment_amount
                })
        
        elif calculation_mode == 2:
            original_total_product_sum = 0
            total_product_sum = 0
            total_down_payment = 0
            minimum_contribution = 0
            merged_payments = {}
            max_months = 0
            
            try:
                application_data = get_application()
                applications = application_data.get('records', [])
                grist_products_data = get_products_in_grist()
                grist_products = grist_products_data.get('records', [])
                
                grist_product_map = {}
                for grist_product in grist_products:
                    grist_id = grist_product.get('id')
                    price_category_id = grist_product.get('fields', {}).get('price_category_id')
                    if grist_id and price_category_id:
                        grist_product_map[grist_id] = price_category_id
            except:
                grist_product_map = {}
                applications = []
            
            for item in product_list:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 1)
                item_down_payment = item.get('total_down_payment', 0)
                item_installment_period = item.get('installment_period')
                
                if item_installment_period is None:
                    continue
                
                try:
                    product = get_object_or_404(Products, id=product_id)
                except:
                    continue
                
                try:
                    tariff = get_object_or_404(Tariffs, id=item_installment_period)
                except:
                    continue
                
                product_total = float(product.price) * quantity
                original_total_product_sum += product_total
                total_down_payment += float(item_down_payment)
                
                product_remaining = product_total - float(item_down_payment)
                total_product_sum += product_remaining
                
                product_monthly_payment = round(
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
                    
                    date_key = payment_date.strftime("%d/%m/%y")
                    if month_num not in merged_payments:
                        merged_payments[month_num] = {
                            'date': date_key,
                            'amount': 0
                        }
                    merged_payments[month_num]['amount'] += product_monthly_payment
                    max_months = max(max_months, month_num)
                
                try:
                    grist_product_id = product.grist_product_id
                    if grist_product_id:
                        try:
                            grist_product_id = int(grist_product_id)
                        except (ValueError, TypeError):
                            continue
                        
                        risk_category_id = None
                        for app in applications:
                            app_products = app.get('fields', {}).get('products', [])
                            if grist_product_id in app_products:
                                risk_category_id = app.get('fields', {}).get('risk_category_id')
                                break
                        
                        if grist_product_id in grist_product_map:
                            price_category_id = grist_product_map[grist_product_id]
                            
                            if risk_category_id and price_category_id:
                                try:
                                    product_category = ProductCategory.objects.get(
                                        grist_risk_category_id=str(risk_category_id),
                                        grist_price_category_id=str(price_category_id)
                                    )
                                    percentage = product_category.percentage or 0
                                    minimum_contribution += product_total * percentage
                                except ProductCategory.DoesNotExist:
                                    pass
                except:
                    pass
            
            monthly_payments = []
            for month_num in sorted(merged_payments.keys()):
                monthly_payments.append({
                    "month_number": month_num,
                    "date": merged_payments[month_num]['date'],
                    "monthly_payment": merged_payments[month_num]['amount']
                })
            
            monthly_payment_amount = merged_payments.get(1, {}).get('amount', 0) if merged_payments else 0
        
        ability_to_order = minimum_contribution <= float(total_down_payment)
        
        response_data = {
            "total_price": round(total_product_sum, 2),
            "total_down_payment": float(total_down_payment),
            "total_every_month_payment": monthly_payment_amount,
            "minimum_contribution": round(minimum_contribution, 2),
            "ability_to_order": ability_to_order,
            "monthly_payments": monthly_payments
        }
        
        return Response(response_data, status=status.HTTP_200_OK)