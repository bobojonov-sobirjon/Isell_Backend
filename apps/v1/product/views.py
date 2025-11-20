from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404
from datetime import datetime, timedelta
from calendar import monthrange

from apps.v1.product.models import (
    Categories, Products, ProductDetails, ProductIDs,
    ProductImages, ProductCharacteristics, ProductProperties
)
from apps.v1.product.serializers import (
    CategoriesSerializer, ProductListSerializer
)
from apps.v1.order.models import Tariffs, Orders
from apps.v1.product.models import ProductRiskCategory
from apps.v1.order.integrations.advanced_payment_assessment import get_application, get_products_in_grist
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


class ProductPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class CategoriesListView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Категории'],
        operation_summary="Список категорий",
        operation_description="Список категорий, у которых есть продукты",
        responses={
            200: openapi.Response(
                description="Список категорий",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "count": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "results": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                                    "name": openapi.Schema(type=openapi.TYPE_STRING),
                                }
                            )
                        )
                    }
                )
            )
        }
    )
    def get(self, request):
        """
        Get all categories that have at least one product
        """
        categories = Categories.objects.filter(
            products__isnull=False
        ).distinct().order_by('id')
        
        serializer = CategoriesSerializer(categories, many=True)
        
        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        }, status=status.HTTP_200_OK)


class ProductListView(APIView):
    permission_classes = [AllowAny]
    pagination_class = ProductPagination
    
    @swagger_auto_schema(
        tags=['Продукты'],
        operation_summary="Список всех продуктов",
        operation_description="Список всех продуктов с фильтрацией и пагинацией",
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
                        "count": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "next": openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
                        "previous": openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
                        "results": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_OBJECT)
                        )
                    }
                )
            )
        }
    )
    def get(self, request):
        """
        Get all products with filters and pagination
        """
        name = request.query_params.get('name', None)
        category = request.query_params.get('category', None)
        
        queryset = Products.objects.select_related(
            'category'
        ).prefetch_related(
            'details__images',
            'ids',
            'characteristics__property'
        ).filter(actual=True)
        
        if name:
            queryset = queryset.filter(name__icontains=name)
        
        if category:
            queryset = queryset.filter(category_id=category)
        
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        
        serializer = ProductListSerializer(
            paginated_queryset, 
            many=True, 
            context={'request': request}
        )
        
        response = paginator.get_paginated_response(serializer.data)
        return response


class ProductDetailView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Продукты'],
        operation_summary="Детальная информация о продукте",
        operation_description="""
        Детальная информация о продукте по ID с возможностью фильтрации по color, storage и sim_card.
        
        **Логика работы фильтров:**
        - color_name: фильтрует variations по цвету
        - storage_name: фильтрует variations по памяти (работает вместе с color_name)
        - sim_card_name: фильтрует variations по типу SIM-карты (работает вместе с color_name и storage_name)
        
        **Response включает:**
        - color_list: список всех доступных цветов с is_active флагом
        - storage_list: список доступных вариантов памяти с is_active флагом (зависит от color_name)
        - sim_card_list: список доступных типов SIM-карт с is_active флагом (зависит от color_name и storage_name)
        """,
        manual_parameters=[
            openapi.Parameter(
                'product_id',
                openapi.IN_PATH,
                description="ID продукта",
                type=openapi.TYPE_INTEGER,
                required=True
            ),
            openapi.Parameter(
                'color',
                openapi.IN_QUERY,
                description="Фильтр по цвету (например: White, Black, Desert)",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'storage',
                openapi.IN_QUERY,
                description="Фильтр по памяти (например: 256GB, 512GB, 1TB)",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'sim',
                openapi.IN_QUERY,
                description="Фильтр по SIM-карте (например: Dual SIM, SIM + eSIM)",
                type=openapi.TYPE_STRING,
                required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description="Детальная информация о продукте",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT)
            ),
            404: openapi.Response(description="Продукт не найден")
        }
    )
    def get(self, request, product_id):
        """
        Get detailed information about a product with optional filters
        """
        product = get_object_or_404(
            Products.objects.select_related('category').prefetch_related(
                'details__images',
                'ids',
                'characteristics__property'
            ),
            id=product_id,
            actual=True
        )
        
        color_name = request.query_params.get('color', None)
        storage_name = request.query_params.get('storage', None)
        sim_card_name = request.query_params.get('sim', None)
        
        serializer = ProductListSerializer(
            product, 
            context={
                'request': request,
                'color_name': color_name,
                'storage_name': storage_name,
                'sim_card_name': sim_card_name
            }
        )
        
        return Response(serializer.data, status=status.HTTP_200_OK)


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
                'advance_payment',
                openapi.IN_QUERY,
                description="Сумма первоначального взноса",
                type=openapi.TYPE_NUMBER,
                required=True
            ),
            openapi.Parameter(
                'tariff',
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
        total_down_payment = request.query_params.get('advance_payment')
        installment_period = request.query_params.get('tariff')
        
        if total_down_payment is None:
            return Response(
                {"error": "Поле 'advance_payment' обязательно"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if installment_period is None:
            return Response(
                {"error": "Поле 'tariff' обязательно"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        product = get_object_or_404(
            Products.objects.prefetch_related('details'),
            id=product_id
        )
        tariff = get_object_or_404(Tariffs, id=installment_period)
        
        product_price = None
        
        if product.price is not None:
            product_price = float(product.price)
        else:
            details = product.details.all()
            if details.exists():
                prices = [float(detail.price) for detail in details if detail.price is not None]
                if prices:
                    product_price = min(prices)
        
        if product_price is None:
            return Response(
                {"error": "Цена продукта не найдена"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        monthly_payment = round(
            (product_price - float(total_down_payment)) * 
            (tariff.coefficient / tariff.payments_count)
        )
        
        response_data = [
            {
                "product_price": product_price,
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
                'total_advance_payment': openapi.Schema(
                    type=openapi.TYPE_NUMBER,
                    description='Общий первоначальный взнос (только для mode 1)'
                ),
                'tariff_id': openapi.Schema(
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
                            'variation_id': openapi.Schema(type=openapi.TYPE_INTEGER, x_nullable=True, description='ID вариации продукта'),
                            'tariff_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID тарифа (только для mode 2)'),
                            'advance_payment': openapi.Schema(type=openapi.TYPE_NUMBER, description='Первоначальный взнос (только для mode 2)'),
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
                        "total_products_price": openapi.Schema(type=openapi.TYPE_NUMBER, description="Общая цена после вычета первоначального взноса"),
                        "total_advance_payment": openapi.Schema(type=openapi.TYPE_NUMBER, description="Первоначальный взнос"),
                        "total_every_month_payment": openapi.Schema(type=openapi.TYPE_NUMBER, description="Ежемесячный платеж"),
                        "minimum_contribution": openapi.Schema(type=openapi.TYPE_NUMBER, description="Минимальный взнос"),
                        "ability_to_order": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Возможность оформить заказ (true если minimum_contribution <= total_advance_payment)"),
                        "monthly_payments": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "number": openapi.Schema(type=openapi.TYPE_INTEGER),
                                    "date": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                                    "payment": openapi.Schema(type=openapi.TYPE_NUMBER)
                                }
                            )
                        ),
                        "product_list": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            description="Список продуктов с информацией о расчете",
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "product_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                                    "quantity": openapi.Schema(type=openapi.TYPE_INTEGER),
                                    "variation_id": openapi.Schema(type=openapi.TYPE_INTEGER, x_nullable=True),
                                    "tariff_id": openapi.Schema(type=openapi.TYPE_INTEGER, x_nullable=True),
                                    "advance_payment": openapi.Schema(type=openapi.TYPE_NUMBER)
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
            total_down_payment = request.data.get('total_advance_payment')
            tariff_id = request.data.get('tariff_id')
            
            if total_down_payment is None:
                return Response(
                    {"error": "Поле 'total_advance_payment' обязательно для режима 1"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if tariff_id is None:
                return Response(
                    {"error": "Поле 'tariff_id' обязательно для режима 1"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            for item in product_list:
                if 'product_id' not in item:
                    return Response(
                        {"error": "Каждый элемент product_list должен содержать 'product_id'"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            tariff = get_object_or_404(Tariffs, id=tariff_id)
            
            user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
            
            has_previous_orders = False
            if user:
                has_previous_orders = Orders.objects.filter(user=user).exists()
            
            total_product_sum = 0
            products_data = []
            for item in product_list:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 1)
                variation_id = item.get('variation_id')
                
                try:
                    product = Products.objects.prefetch_related('details', 'ids').get(id=product_id)
                except Products.DoesNotExist:
                    continue
                
                product_price = None
                
                if variation_id:
                    product_id_obj = ProductIDs.objects.filter(product=product, variation_id=str(variation_id)).first()
                    if product_id_obj and product_id_obj.variation_name:
                        variation_name = product_id_obj.variation_name.upper()
                        details = product.details.all()
                        
                        for detail in details:
                            color = detail.color or ""
                            storage = detail.storage or ""
                            sim = detail.sim or ""
                            
                            color_match = color.upper() in variation_name if color else False
                            storage_match = storage.upper() in variation_name if storage else False
                            
                            sim_match = False
                            if sim:
                                sim_normalized = sim.replace("+", "").replace(" ", "").upper()
                                if sim.upper() in variation_name:
                                    sim_match = True
                                elif sim_normalized and sim_normalized in variation_name.replace(" ", "").replace("+", ""):
                                    sim_match = True
                                elif "SIM" in sim_normalized and "SIM" in variation_name:
                                    sim_match = True
                                elif "DUAL" in sim_normalized and "DUAL" in variation_name:
                                    sim_match = True
                                elif "ESIM" in sim_normalized and "ESIM" in variation_name:
                                    sim_match = True
                            
                            if color_match and storage_match and (sim_match if sim else True):
                                if detail.price is not None:
                                    product_price = float(detail.price)
                                    break
                
                if product_price is None:
                    if product.price is not None:
                        product_price = float(product.price)
                    else:
                        details = product.details.all()
                        if details.exists():
                            prices = [float(detail.price) for detail in details if detail.price is not None]
                            if prices:
                                product_price = min(prices)
                
                if product_price is None:
                    continue
                
                total_product_sum += product_price * quantity
                
                product_id_obj = ProductIDs.objects.filter(product=product).first()
                response_variation_id = product_id_obj.variation_id if product_id_obj and product_id_obj.variation_id else None
                
                products_data.append({
                    'product': product,
                    'quantity': quantity,
                    'price': product_price,
                    'variation_id': response_variation_id
                })
            
            original_total_product_sum = total_product_sum
            total_product_sum = max(0, total_product_sum - float(total_down_payment))
            
            if total_product_sum > 0:
                monthly_payment_amount = round(
                    total_product_sum * (tariff.coefficient / tariff.payments_count)
                )
            else:
                monthly_payment_amount = 0
            
            minimum_contribution = 0
            if has_previous_orders:
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
                            product = prod_data['product']
                            product_id_obj = ProductIDs.objects.filter(product=product).first()
                            grist_product_id = product_id_obj.grist_product_id if product_id_obj and product_id_obj.grist_product_id else None
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
                        product_price = prod_data['price']
                        product_id_obj = ProductIDs.objects.filter(product=product).first()
                        grist_product_id = product_id_obj.grist_product_id if product_id_obj and product_id_obj.grist_product_id else None
                        
                        if grist_product_id:
                            try:
                                grist_product_id = int(grist_product_id)
                            except (ValueError, TypeError):
                                continue
                        
                        if grist_product_id and grist_product_id in grist_product_map:
                            price_category_id = grist_product_map[grist_product_id]
                            
                            if risk_category_id and price_category_id:
                                try:
                                    product_risk_category = ProductRiskCategory.objects.get(
                                        grist_risk_category_id=str(risk_category_id),
                                        grist_price_category_id=str(price_category_id)
                                    )
                                    percentage = product_category.percentage or 0
                                    product_total = product_price * quantity
                                    minimum_contribution += product_total * percentage
                                except ProductRiskCategory.DoesNotExist:
                                    pass
                except Exception as e:
                    minimum_contribution = 0
            
            current_date = datetime.now()
            
            if monthly_payment_amount > 0:
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
                        "number": month_num,
                        "date": payment_date.strftime("%d/%m/%y"),
                        "payment": monthly_payment_amount
                    })
        
        elif calculation_mode == 2:
            original_total_product_sum = 0
            total_product_sum = 0
            total_down_payment = 0
            minimum_contribution = 0
            merged_payments = {}
            max_months = 0
            total_remaining_after_advance = 0
            
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
                variation_id = item.get('variation_id')
                item_down_payment = item.get('advance_payment', 0)
                item_tariff_id = item.get('tariff_id')
                
                if 'product_id' not in item:
                    continue
                
                if item_tariff_id is None:
                    continue
                
                try:
                    product = Products.objects.prefetch_related('details', 'ids').get(id=product_id)
                except Products.DoesNotExist:
                    continue
                
                try:
                    tariff = Tariffs.objects.get(id=item_tariff_id)
                except Tariffs.DoesNotExist:
                    continue
                
                product_price = None
                
                if variation_id:
                    product_id_obj = ProductIDs.objects.filter(product=product, variation_id=str(variation_id)).first()
                    if product_id_obj and product_id_obj.variation_name:
                        variation_name = product_id_obj.variation_name.upper()
                        details = product.details.all()
                        
                        best_match_detail = None
                        best_match_score = 0
                        
                        for detail in details:
                            color = detail.color or ""
                            storage = detail.storage or ""
                            sim = detail.sim or ""
                            
                            color_match = color.upper() in variation_name if color else False
                            storage_match = storage.upper() in variation_name if storage else False
                            
                            sim_match = False
                            if sim:
                                sim_normalized = sim.replace("+", "").replace(" ", "").upper()
                                if sim.upper() in variation_name:
                                    sim_match = True
                                elif sim_normalized and sim_normalized in variation_name.replace(" ", "").replace("+", ""):
                                    sim_match = True
                                elif "SIM" in sim_normalized and "SIM" in variation_name:
                                    sim_match = True
                                elif "DUAL" in sim_normalized and "DUAL" in variation_name:
                                    sim_match = True
                                elif "ESIM" in sim_normalized and "ESIM" in variation_name:
                                    sim_match = True
                            
                            if color_match and storage_match and (sim_match if sim else True):
                                if detail.price is not None:
                                    product_price = float(detail.price)
                                    break
                            
                            match_score = 0
                            if color_match:
                                match_score += 1
                            if storage_match:
                                match_score += 1
                            if sim_match or not sim:
                                match_score += 1
                            
                            if match_score > best_match_score and detail.price is not None:
                                best_match_detail = detail
                                best_match_score = match_score
                        
                        if product_price is None and best_match_detail and best_match_detail.price is not None:
                            product_price = float(best_match_detail.price)
                
                if product_price is None:
                    if product.price is not None:
                        product_price = float(product.price)
                    else:
                        details = product.details.all()
                        if details.exists():
                            prices = [float(detail.price) for detail in details if detail.price is not None]
                            if prices:
                                product_price = min(prices)
                
                if product_price is None:
                    continue
                
                product_total = product_price * quantity
                original_total_product_sum += product_total
                total_down_payment += float(item_down_payment)
                
                product_remaining = product_total - float(item_down_payment)
                if product_remaining < 0:
                    product_remaining = 0
                
                total_product_sum += product_remaining
                total_remaining_after_advance += product_remaining
                
                if product_remaining > 0:
                    product_monthly_payment = round(
                        product_remaining * (tariff.coefficient / tariff.payments_count)
                    )
                else:
                    product_monthly_payment = 0
                
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
                    product_id_obj = ProductIDs.objects.filter(product=product).first()
                    grist_product_id = product_id_obj.grist_product_id if product_id_obj and product_id_obj.grist_product_id else None
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
                    "number": month_num,
                    "date": merged_payments[month_num]['date'],
                    "payment": merged_payments[month_num]['amount']
                })
            
            monthly_payment_amount = merged_payments.get(1, {}).get('amount', 0) if merged_payments else 0
        
        if calculation_mode == 1:
            if not has_previous_orders:
                ability_to_order = True
            else:
                ability_to_order = minimum_contribution <= float(total_down_payment)
        else:
            ability_to_order = minimum_contribution <= float(total_down_payment)
        
        response_product_list = []
        
        if calculation_mode == 1:
            for prod_data in products_data:
                product = prod_data['product']
                quantity = prod_data['quantity']
                variation_id = prod_data.get('variation_id')
                
                response_product_list.append({
                    "product_id": product.id,
                    "quantity": quantity,
                    "variation_id": int(variation_id) if variation_id else None,
                    "tariff_id": int(tariff_id) if tariff_id else None,
                    "advance_payment": round(float(total_down_payment) / len(products_data), 2) if products_data else 0
                })
        elif calculation_mode == 2:
            for item in product_list:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 1)
                item_advance_payment = item.get('advance_payment', 0)
                item_tariff_id = item.get('tariff_id')
                
                try:
                    product = Products.objects.get(id=product_id)
                    product_id_obj = ProductIDs.objects.filter(product=product).first()
                    variation_id = product_id_obj.variation_id if product_id_obj and product_id_obj.variation_id else None
                    
                    response_product_list.append({
                        "product_id": product.id,
                        "quantity": quantity,
                        "variation_id": int(variation_id) if variation_id else None,
                        "tariff_id": int(item_tariff_id) if item_tariff_id else None,
                        "advance_payment": float(item_advance_payment)
                    })
                except Products.DoesNotExist:
                    continue
        
        if calculation_mode == 1:
            total_products_price = original_total_product_sum
        elif calculation_mode == 2:
            total_products_price = original_total_product_sum
        else:
            total_products_price = original_total_product_sum
        
        response_data = {
            "total_products_price": round(total_products_price, 2),
            "total_advance_payment": float(total_down_payment),
            "total_every_month_payment": monthly_payment_amount,
            "minimum_contribution": round(minimum_contribution, 2),
            "ability_to_order": ability_to_order,
            "monthly_payments": monthly_payments,
            "product_list": response_product_list
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
