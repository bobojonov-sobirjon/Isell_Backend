from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404
from datetime import datetime, timedelta
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from apps.v1.product.models import (
    Categories, Products, ProductDetails, ProductIDs,
    ProductImages, ProductCharacteristics, ProductProperties
)
from apps.v1.product.serializers import (
    CategoriesSerializer, ProductListSerializer
)
from apps.v1.order.models import Tariffs, Orders
from apps.v1.product.models import ProductRiskCategory
from apps.v1.order.integrations.advanced_payment_assessment import (
    get_application, get_products_in_grist, get_counterparties_in_grist, post_to_grist_application
)
from apps.v1.product.constants import (
    TariffConstants, ApplicationStages, TimeConstants, CalculationModes
)
from apps.v1.product.utils.payment_utils import (
    get_tariff_coefficient_ratio,
    calculate_monthly_payment_amount,
    generate_monthly_payments
)
from apps.v1.product.utils.detail_matching import match_product_detail, find_matching_detail_price
from apps.v1.product.services.product_price_service import ProductPriceService
from apps.v1.product.services.application_service import ApplicationService
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

logger = logging.getLogger(__name__)

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
        Logic:
        - Variatsiyasiz tovarlar: Products.is_actual = True bo'lsa chiqadi
        - Variatsiyali tovarlar: kamida bitta ProductIDs.is_actual = True bo'lsa chiqadi
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
        
        
        from django.db.models import Q, Exists, OuterRef
        
        products_without_variations = queryset.filter(
            is_actual=True
        ).annotate(
            has_variations=Exists(
                ProductIDs.objects.filter(product=OuterRef('pk'))
            )
        ).filter(has_variations=False)
        
        products_with_variations = queryset.filter(
            ids__is_actual=True
        ).distinct()
        
        queryset = queryset.filter(
            Q(id__in=products_without_variations.values_list('id', flat=True)) |
            Q(id__in=products_with_variations.values_list('id', flat=True))
        ).distinct()
        
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

# get_tariff_coefficient_ratio moved to apps.v1.product.utils.payment_utils

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
        
        **Логика определения цены:**
        - Если передан variation_id: цена берется из ProductDetails (вариация продукта)
        - Если variation_id не передан: цена берется из Product.price
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
            openapi.Parameter(
                'variation_id',
                openapi.IN_QUERY,
                description="ID вариации продукта (опционально). Если указан, цена берется из ProductDetails",
                type=openapi.TYPE_INTEGER,
                required=False
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
        variation_id = request.query_params.get('variation_id')
        
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
            Products.objects.prefetch_related('details', 'ids'),
            id=product_id
        )
        tariff = get_object_or_404(Tariffs, id=installment_period)
        
        is_no_installment = tariff.name and TariffConstants.NO_INSTALLMENT_KEYWORD in tariff.name
        
        # Get product price using service
        product_price = None
        if variation_id:
            product_id_obj = ProductIDs.objects.filter(
                product=product,
                variation_id=str(variation_id)
            ).first()
            
            if product_id_obj and product_id_obj.variation_name:
                product_price = find_matching_detail_price(product, product_id_obj.variation_name)
        
        # Fallback to product price or minimum detail price
        if product_price is None:
            product_price = ProductPriceService.get_product_price(product)
        
        if product_price is None:
            return Response(
                {"error": "Цена продукта не найдена"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate monthly payment
        if is_no_installment:
            monthly_payment = 0
        else:
            remaining_amount = max(0, product_price - float(total_down_payment))
            monthly_payment = calculate_monthly_payment_amount(remaining_amount, tariff)
        
        response_data = [
            {
                "product_price": product_price,
                "monthly_payment": monthly_payment
            }
        ]
        
        return Response(response_data, status=status.HTTP_200_OK)

def get_user_counterparty_id(user):
    """
    Get counterparty_id from Grist based on user's pnfl and date_of_birth
    """
    import logging
    logger = logging.getLogger(__name__)

    if not user or not user.pnfl or not user.date_of_birth:
        return None
    
    try:
        from apps.v1.order.integrations.advanced_payment_assessment import get_counterparties_in_grist
        import os
        
        table_name = os.getenv('ISell_CONTERPARTIES', 'Counterparties')
        
        counterparties_data = get_counterparties_in_grist()
        counterparties = counterparties_data.get('records', [])

        if user.date_of_birth:
            from django.utils import timezone
            import pytz
            
            user_dob_datetime = datetime.combine(user.date_of_birth, datetime.min.time())
            user_dob_datetime_utc = timezone.make_aware(user_dob_datetime, pytz.UTC)
            user_dob_timestamp = int(user_dob_datetime_utc.timestamp())
        else:
            user_dob_timestamp = None
        
        for idx, counterparty in enumerate(counterparties):
            fields = counterparty.get('fields', {})
            pinfl = fields.get('pinfl', '')
            date_of_birth = fields.get('date_of_birth')
            counterparty_id = counterparty.get('id')

            pinfl_match = pinfl == user.pnfl

            dob_match = False
            if date_of_birth is None and user_dob_timestamp is None:
                dob_match = True

            elif date_of_birth is not None and user_dob_timestamp is not None:
                try:
                    if isinstance(date_of_birth, str):
                        try:
                            from datetime import datetime as dt
                            parsed_date = dt.strptime(date_of_birth, "%Y-%m-%d").date()
                            from django.utils import timezone
                            import pytz
                            
                            parsed_datetime = datetime.combine(parsed_date, datetime.min.time())
                            parsed_datetime_utc = timezone.make_aware(parsed_datetime, pytz.UTC)
                            grist_dob = int(parsed_datetime_utc.timestamp())

                        except ValueError:
                            grist_dob = int(float(date_of_birth))

                    else:
                        grist_dob = int(date_of_birth)
                    
                    time_diff = abs(grist_dob - user_dob_timestamp)
                    dob_match = time_diff < 43200

                except (ValueError, TypeError) as e:
                    dob_match = False
            else:
                pass
            
            if pinfl_match and dob_match:
                return counterparty_id

        return None
    except Exception as e:
        return None

def check_user_has_application(user, applications):
    """
    Check if user has any application in get_application()
    Returns (has_application, counterparty_id)
    """

    if not user:

        return (False, None)
    
    try:
        counterparty_id = get_user_counterparty_id(user)

        if not counterparty_id:

            return (False, None)

        for idx, app in enumerate(applications):
            app_counterparty_id = app.get('fields', {}).get('counterparty_id')
            app_stage = app.get('fields', {}).get('stage', '')
            app_id = app.get('id')

            if app_counterparty_id == counterparty_id:

                return (True, counterparty_id)

        return (False, None)
    except Exception as e:

        return (False, None)

def get_latest_application_by_counterparty(applications, counterparty_id):
    """
    Get the latest application for a counterparty_id
    Returns the application with the highest id (latest) or None
    """
    if not applications or not counterparty_id:
        return None
    
    matching_apps = []
    for app in applications:
        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
        if app_counterparty_id == counterparty_id:
            matching_apps.append(app)
    
    if not matching_apps:
        return None
    
    matching_apps.sort(key=lambda x: x.get('id', 0), reverse=True)
    return matching_apps[0]

def are_all_today_applications_accepted(applications, counterparty_id):
    """
    Check if all today's applications for a counterparty_id are "Accepted", "Success", or "Denied by client"
    Returns True if all are Accepted/Success/Denied by client, False otherwise
    
    Проверяет, все ли заявки на сегодня для counterparty_id имеют статус "Accepted", "Success" или "Denied by client"
    Возвращает True, если все Accepted/Success/Denied by client, иначе False
    """
    if not applications or not counterparty_id:
        return False
    
    from datetime import datetime
    from django.utils import timezone
    import pytz
    
    today = datetime.now().date()
    today_datetime = datetime.combine(today, datetime.min.time())
    today_datetime_utc = timezone.make_aware(today_datetime, pytz.UTC)
    today_timestamp = int(today_datetime_utc.timestamp())
    
    today_start = today_timestamp
    today_end = today_timestamp + 86400
    
    today_apps = []
    for app in applications:
        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
        app_date = app.get('fields', {}).get('date')
        
        if app_counterparty_id == counterparty_id and app_date:
            app_date_timestamp = None
            if isinstance(app_date, (int, float)):
                app_date_timestamp = int(app_date)
            elif isinstance(app_date, str):
                try:
                    from datetime import datetime as dt
                    parsed_date = dt.strptime(app_date, "%Y-%m-%d").date()
                    parsed_datetime = dt.combine(parsed_date, dt.min.time())
                    parsed_datetime_utc = timezone.make_aware(parsed_datetime, pytz.UTC)
                    app_date_timestamp = int(parsed_datetime_utc.timestamp())
                except:
                    pass
            
            if app_date_timestamp and today_start <= app_date_timestamp < today_end:
                today_apps.append(app)
    
    if not today_apps:
        return False
    
    for app in today_apps:
        stage = app.get('fields', {}).get('stage', '')
        if stage not in [ApplicationStages.ACCEPTED, ApplicationStages.SUCCESS, ApplicationStages.DENIED_BY_CLIENT]:
            return False
    
    return True

def get_today_application_by_counterparty(applications, counterparty_id):
    """
    Get today's application for a counterparty_id
    Returns the application for today's date or None
    """
    if not applications or not counterparty_id:
        return None
    
    from datetime import datetime
    from django.utils import timezone
    import pytz
    
    today = datetime.now().date()
    today_datetime = datetime.combine(today, datetime.min.time())
    today_datetime_utc = timezone.make_aware(today_datetime, pytz.UTC)
    today_timestamp = int(today_datetime_utc.timestamp())
    
    today_start = today_timestamp
    today_end = today_timestamp + 86400
    
    matching_apps = []
    for app in applications:
        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
        app_date = app.get('fields', {}).get('date')
        
        if app_counterparty_id == counterparty_id and app_date:
            app_date_timestamp = None
            if isinstance(app_date, (int, float)):
                app_date_timestamp = int(app_date)
            elif isinstance(app_date, str):
                try:
                    from datetime import datetime as dt
                    parsed_date = dt.strptime(app_date, "%Y-%m-%d").date()
                    parsed_datetime = dt.combine(parsed_date, dt.min.time())
                    parsed_datetime_utc = timezone.make_aware(parsed_datetime, pytz.UTC)
                    app_date_timestamp = int(parsed_datetime_utc.timestamp())
                except:
                    pass
            
            if app_date_timestamp and today_start <= app_date_timestamp < today_end:
                matching_apps.append(app)
    
    if not matching_apps:
        return None
    
    matching_apps.sort(key=lambda x: x.get('id', 0), reverse=True)
    return matching_apps[0]

def get_grist_product_ids_from_request(product_list):
    """
    Get grist_product_ids from ProductIDs model using product_id and variation_id from request
    Returns list of grist_product_ids
    """
    grist_product_ids = []
    
    for item in product_list:
        product_id = item.get('product_id')
        variation_id = item.get('variation_id')
        
        if not product_id:
            continue
        
        try:
            if variation_id:
                product_id_obj = ProductIDs.objects.filter(
                    product_id=product_id,
                    variation_id=str(variation_id)
                ).first()
            else:
                product_id_obj = ProductIDs.objects.filter(
                    product_id=product_id
                ).first()
            
            if product_id_obj and product_id_obj.grist_product_id:
                try:
                    grist_id = int(product_id_obj.grist_product_id)
                    grist_product_ids.append(grist_id)
                except (ValueError, TypeError):
                    continue
        except Exception:
            continue
    
    return grist_product_ids

def get_grist_product_ids_from_price_product_ids(price_product_ids):
    """
    Get grist_product_ids (Price table record ids) from Price table product_ids.
    Reverse of get_product_ids_from_price_table_by_grist_ids.
    
    Args:
        price_product_ids: List of product_ids from Price table fields.product_id
    
    Returns:
        List of grist_product_ids (Price table record ids)
    """
    if not price_product_ids:
        return []
    
    try:
        from apps.v1.order.integrations.advanced_payment_assessment import ISell_PRODUCT_PRICE, get_url
        import aiohttp
        import asyncio
        
        if not ISell_PRODUCT_PRICE:
            return []
        
        url = get_url(ISell_PRODUCT_PRICE)
        
        async def fetch_price_data_async(session, url):
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
            except Exception:
                return None
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_price_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        records = data.get("records", [])
        
        grist_product_ids = []
        price_product_ids_set = set(str(p) for p in price_product_ids if p)
        
        for record in records:
            record_id = record.get("id")
            fields = record.get("fields", {})
            product_id = fields.get("product_id")
            
            if product_id and str(product_id) in price_product_ids_set:
                if record_id:
                    grist_product_ids.append(record_id)
        
        return grist_product_ids
        
    except Exception as e:
        return []

def get_base_product_ids_from_price_product_ids(price_product_ids):
    """
    Get base product_ids from Price table record IDs.
    Price table product_ids in applications are actually Price table record IDs.
    We need to get base product_id directly from ProductIDs model using grist_product_id.
    
    Args:
        price_product_ids: List of Price table record IDs (from application fields.products)
        These are actually grist_product_ids stored in ProductIDs model
    
    Returns:
        List of base product_ids (Products.id)
    """
    if not price_product_ids:
        return []
    
    base_product_ids = []
    
    for price_product_id in price_product_ids:
        if not price_product_id:
            continue
        
        try:
            product_id_obj = ProductIDs.objects.filter(grist_product_id=str(price_product_id)).first()
            
            if product_id_obj and product_id_obj.product:
                base_product_id = product_id_obj.product.id
                base_product_ids.append(base_product_id)
        except Exception:
            continue
    
    return base_product_ids

def get_variation_ids_from_price_table_record_ids(price_record_ids):
    """
    Get variation_ids from Price table record IDs.
    Price table dan barcha ma'lumotlarni oladi, keyin ProductIDs modeldan variation_id bilan check qiladi.
    
    Args:
        price_record_ids: List of Price table record IDs (from application fields.products)
    
    Returns:
        List of variation_ids from ProductIDs model (bizning bazadan)
    """
    if not price_record_ids:
        return []
    
    try:
        from apps.v1.order.integrations.advanced_payment_assessment import ISell_PRODUCT_PRICE, get_url
        import aiohttp
        import asyncio
        
        if not ISell_PRODUCT_PRICE:
            return []
        
        url = get_url(ISell_PRODUCT_PRICE)
        
        async def fetch_price_data_async(session, url):
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return None
            except Exception:
                return None
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_price_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        records = data.get("records", [])
        
        price_record_ids_set = set(str(p) for p in price_record_ids if p)
        
        variation_ids_from_price = []
        for record in records:
            record_id = str(record.get("id"))
            if record_id in price_record_ids_set:
                fields = record.get("fields", {})
                variation_id = fields.get("variation_id")
                
                if variation_id:
                    variation_ids_from_price.append(str(variation_id))
        
        variation_ids_from_db = []
        for variation_id_str in variation_ids_from_price:
            product_id_obj = ProductIDs.objects.filter(variation_id=str(variation_id_str)).first()
            
            if product_id_obj:
                variation_ids_from_db.append(str(variation_id_str))
        
        return variation_ids_from_db
        
    except Exception:
        return []

def get_product_names_and_variation_ids_from_price_table_record_ids(price_record_ids):
    """
    Get product names and variation_ids from Price table record IDs.
    1. Price table dan product_id ni oladi
    2. ISell_PRODUCTS (Grist) dan product name ni oladi
    3. ProductIDs modeldan product__name va variation_id bilan check qiladi
    
    Args:
        price_record_ids: List of Price table record IDs (from application fields.products)
    
    Returns:
        List of tuples: [(product_name, variation_id), ...]
    """
    if not price_record_ids:
        return []
    
    try:
        from apps.v1.order.integrations.advanced_payment_assessment import ISell_PRODUCT_PRICE, ISell_PRODUCTS, get_url
        from apps.v1.order.integrations.advanced_payment_assessment import headers as grist_headers
        import aiohttp
        import asyncio
        
        if not ISell_PRODUCT_PRICE:
            return []
        
        if not ISell_PRODUCTS:
            return []
        
        price_url = get_url(ISell_PRODUCT_PRICE)
        
        price_record_ids_int = [int(p) for p in price_record_ids if p and str(p).isdigit()]
        
        if not price_record_ids_int:
            return []
        
        async def fetch_price_data_async(session, url, headers):
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return None
            except Exception:
                return None
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_price_data_async(session, price_url, grist_headers)
                return data
        
        price_data = asyncio.run(fetch())
        
        if not price_data:
            return []
        
        price_records = price_data.get("records", [])
        
        price_record_ids_set = set(price_record_ids_int)
        
        price_table_ids = []
        variation_ids_from_price = {}
        for record in price_records:
            record_id = record.get("id")
            fields = record.get("fields", {})
            product_id = fields.get("product_id")
            variation_id = fields.get("variation_id") or ""
            
            if product_id in price_record_ids_set:
                price_table_ids.append(record_id)
                variation_ids_from_price[record_id] = variation_id
        
        if not price_table_ids:
            return []
        
        result = []
        for price_table_id in price_table_ids:
            variation_id_from_price = variation_ids_from_price.get(price_table_id, "")
            
            product_id_obj = ProductIDs.objects.filter(
                grist_product_id=str(price_table_id),
                variation_id=str(variation_id_from_price) if variation_id_from_price else ""
            ).first()
            
            if product_id_obj:
                product_name = product_id_obj.product.name if product_id_obj.product else ""
                variation_id = product_id_obj.variation_id or ""
                result.append((product_name, variation_id))
        
        return result
        
    except Exception:
        return []

def compare_application_products_with_request(application, product_list):
    """
    Compare products from application with products from request.
    Avval product name bilan, keyin variation_id bilan solishtiradi.
    
    Args:
        application: Application record from Grist (has fields.products which are Price table record IDs)
        product_list: List of products from request (has product_id and variation_id)
    
    Returns:
        True if products match (product name va variation_id), False otherwise
    """
    if not application or not product_list:
        return False
    
    try:
        app_products_raw = application.get('fields', {}).get('products', [])
        
        app_products = app_products_raw
        
        if isinstance(app_products, list) and len(app_products) > 0 and app_products[0] == "L":
            app_products = app_products[1:] if len(app_products) > 1 else []
        
        if not app_products:
            return False
        
        app_product_data = get_product_names_and_variation_ids_from_price_table_record_ids(app_products)
        
        request_product_data = []
        for item in product_list:
            product_id = item.get('product_id')
            variation_id = item.get('variation_id', '')
            
            if not product_id:
                continue
            
            try:
                product = Products.objects.filter(id=product_id).first()
                if product:
                    product_name = product.name or ""
                    request_product_data.append((product_name, str(variation_id) if variation_id else ""))
            except Exception:
                pass
        
        request_product_set = set(request_product_data)
        app_product_set = set(app_product_data)
        
        if request_product_set.issubset(app_product_set) and len(request_product_set) > 0:
            return True
        
        return False
        
    except Exception:
        return False

def get_risk_category_id_from_applications(applications, counterparty_id):
    """
    Get risk_category_id from applications for a counterparty.
    Priority:
    1. First try to get from latest application with "Accepted" or "Success" status
    2. Then try to get from any application with "Accepted" or "Success" status
    3. Then try to get from latest application (any status)
    4. Finally search in all applications for this counterparty
    
    Returns:
        risk_category_id or None
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not applications or not counterparty_id:
        return None
    
    latest_app = get_latest_application_by_counterparty(applications, counterparty_id)
    if latest_app:
        latest_stage = latest_app.get('fields', {}).get('stage', '')
        if latest_stage in [ApplicationStages.ACCEPTED, ApplicationStages.SUCCESS]:
            risk_category_id = latest_app.get('fields', {}).get('risk_category_id')
            if risk_category_id:
                return risk_category_id
    
    approved_apps = []
    for app in applications:
        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
        app_stage = app.get('fields', {}).get('stage', '')
        if app_counterparty_id == counterparty_id and app_stage in [ApplicationStages.ACCEPTED, ApplicationStages.SUCCESS]:
            approved_apps.append(app)
    
    if approved_apps:
        approved_apps.sort(key=lambda x: x.get('id', 0), reverse=True)
        for app in approved_apps:
            risk_category_id = app.get('fields', {}).get('risk_category_id')
            if risk_category_id:
                return risk_category_id
    
    if latest_app:
        risk_category_id = latest_app.get('fields', {}).get('risk_category_id')
        if risk_category_id:
            return risk_category_id
    
    all_apps = []
    for app in applications:
        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
        if app_counterparty_id == counterparty_id:
            all_apps.append(app)
    
    if all_apps:
        all_apps.sort(key=lambda x: x.get('id', 0), reverse=True)
        for app in all_apps:
            risk_category_id = app.get('fields', {}).get('risk_category_id')
            if risk_category_id:
                return risk_category_id
    
    return None

def calculate_minimum_contribution_for_products(user, products_data, grist_product_map, applications, counterparty_id):
    """
    Calculate minimum_contribution for products based on user's approved applications
    """
    import logging
    logger = logging.getLogger(__name__)

    if not user or not counterparty_id:
        return 0
    
    try:
        approved_applications = []
        for idx, app in enumerate(applications):
            app_counterparty_id = app.get('fields', {}).get('counterparty_id')
            app_stage = app.get('fields', {}).get('stage', '')
            app_id = app.get('id')

            if app_counterparty_id == counterparty_id and app_stage == ApplicationStages.ACCEPTED:
                approved_applications.append(app)

        if not approved_applications:
            return 0

        risk_category_id = None
        for app_idx, app in enumerate(approved_applications):
            app_products = app.get('fields', {}).get('products', [])
            app_risk_category_id = app.get('fields', {}).get('risk_category_id')
            app_id = app.get('id')

            product_found = False
            for prod_idx, prod_data in enumerate(products_data):
                product = prod_data['product']
                product_id_obj = ProductIDs.objects.filter(product=product).first()
                grist_product_id = product_id_obj.grist_product_id if product_id_obj and product_id_obj.grist_product_id else None

                if grist_product_id:
                    try:
                        grist_product_id = int(grist_product_id)

                        if grist_product_id in app_products:
                            risk_category_id = app_risk_category_id
                            product_found = True
                            break
                    except (ValueError, TypeError):
                        continue
            
            if not product_found and app_risk_category_id:
                risk_category_id = app_risk_category_id
                break
            
            if risk_category_id:
                break
        
        if not risk_category_id:
            return 0
        
        # Risk category ma'lumotlarini olish
        try:
            risk_category_obj = ProductRiskCategory.objects.filter(grist_risk_category_id=str(risk_category_id)).first()
        except Exception:
            pass

        minimum_contribution = 0

        for prod_idx, prod_data in enumerate(products_data):
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
                
                if grist_product_id in grist_product_map:
                    price_category_id = grist_product_map[grist_product_id]
                    
                    if risk_category_id and price_category_id:
                        try:
                            product_risk_category = ProductRiskCategory.objects.get(
                                grist_risk_category_id=str(risk_category_id),
                                grist_price_category_id=str(price_category_id)
                            )
                            
                            percentage = product_risk_category.percentage or 0
                            product_total = product_price * quantity
                            contribution = product_total * percentage
                            
                            minimum_contribution += contribution

                        except ProductRiskCategory.DoesNotExist:
                            pass
                        except Exception:
                            pass
        
        return minimum_contribution
    except Exception as e:
        logger.error(f"Error calculating minimum contribution: {e}", exc_info=True)
        return 0

def has_active_orders(user):
    """
    User uchun FINISHED bo'lmagan orderlar bor-yo'qligini tekshiradi.
    Agar PREPARING, READY yoki DELIVERING statusli order bo'lsa, True qaytaradi.
    """
    if not user:
        return False
    
    active_orders = Orders.objects.filter(
        user=user,
        status__in=[Orders.Status.PREPARING, Orders.Status.READY, Orders.Status.DELIVERING]
    ).exists()
    
    return active_orders

def has_denied_by_client_for_products(applications, counterparty_id, product_list):
    """
    Berilgan mahsulotlar uchun 'Denied by client' stage bor-yo'qligini tekshiradi.
    Faqat o'sha mahsulotlar uchun tekshiradi, boshqalari uchun emas.
    """
    if not applications or not counterparty_id or not product_list:
        return False
    
    try:
        from apps.v1.product.models import Products
        from apps.v1.order.models import OrderItems
        
        # Request'dagi mahsulotlarni olish
        request_product_ids = [item.get('product_id') for item in product_list if item.get('product_id')]
        request_variation_ids = [str(item.get('variation_id')) for item in product_list if item.get('variation_id')]
        
        # Applications'lardan 'Denied by client' stage bilan mahsulotlarni topish
        for app in applications:
            app_counterparty_id = app.get('fields', {}).get('counterparty_id')
            app_stage = app.get('fields', {}).get('stage', '')
            
            if app_counterparty_id == counterparty_id and app_stage == 'Denied by client':
                # Application'dagi mahsulotlarni olish
                app_products_match = compare_application_products_with_request(app, product_list)
                if app_products_match:
                    return True
        
        return False
    except Exception:
        return False

def has_accepted_but_not_in_orders(user, applications, counterparty_id, product_list):
    """
    Berilgan mahsulotlar uchun 'Accepted' stage bor, lekin Order tablega qo'shilmaganligini tekshiradi.
    """
    if not user or not applications or not counterparty_id or not product_list:
        return False
    
    try:
        from apps.v1.order.models import OrderItems
        
        # Applications'lardan 'Accepted' stage bilan mahsulotlarni topish
        for app in applications:
            app_counterparty_id = app.get('fields', {}).get('counterparty_id')
            app_stage = app.get('fields', {}).get('stage', '')
            
            if app_counterparty_id == counterparty_id and app_stage == ApplicationStages.ACCEPTED:
                # Application'dagi mahsulotlar request'dagi mahsulotlar bilan mos keladimi?
                app_products_match = compare_application_products_with_request(app, product_list)
                if app_products_match:
                    # Bu mahsulotlar Order tablega qo'shilganmi?
                    # Request'dagi barcha mahsulotlar uchun tekshirish
                    for item in product_list:
                        product_id = item.get('product_id')
                        variation_id = item.get('variation_id')
                        
                        if not product_id:
                            continue
                        
                        # Variation_id bilan tekshirish
                        if variation_id:
                            order_item_exists = OrderItems.objects.filter(
                                order__user=user,
                                product_id=product_id,
                                variation__variation_id=str(variation_id)
                            ).exists()
                            if not order_item_exists:
                                return True
                else:
                            # Variation_id bo'lmasa, faqat product_id bilan tekshirish
                            order_item_exists = OrderItems.objects.filter(
                                order__user=user,
                                product_id=product_id,
                                variation__isnull=True
                            ).exists()
                            if not order_item_exists:
                                return True
        
        return False
    except Exception:
        return False

def has_denied_within_30_days(applications, counterparty_id, product_list=None):
    """
    'Denied' stage bor va 30 kundan kam o'tganligini tekshiradi.
    Faqat request'dagi productlar bilan mos keladigan "Denied" application'larni tekshiradi.
    """
    if not applications or not counterparty_id:
        return False
    
    try:
        from datetime import datetime
        
        for app in applications:
            app_counterparty_id = app.get('fields', {}).get('counterparty_id')
            app_stage = app.get('fields', {}).get('stage', '')
            
            if app_counterparty_id == counterparty_id and app_stage == 'Denied':
                # Agar product_list berilgan bo'lsa, faqat o'sha productlar bilan mos keladigan application'larni tekshirish
                if product_list:
                    app_products_match = compare_application_products_with_request(app, product_list)
                    if not app_products_match:
                        continue  # Bu application boshqa productlar uchun, o'tkazib yuborish
                
                denied_date = app.get('fields', {}).get('date', 0)
                
                if denied_date:
                    if isinstance(denied_date, (int, float)):
                        denied_datetime = datetime.fromtimestamp(denied_date)
                        current_datetime = datetime.now()
                        days_passed = (current_datetime - denied_datetime).days
                        
                        if days_passed < 30:
                            return True
        
        return False
    except Exception:
        return False

class CalculatePaymentScheduleView(APIView):
    """
    View for calculating payment schedule based on calculation mode.
    """
    permission_classes = [IsAuthenticated]
    
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
                        "ability_to_order": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Возможность оформить заказ"),
                        "status": openapi.Schema(type=openapi.TYPE_STRING, description="Статус заявки (New, Assessment, Accepted, Denied, Denied by client, Success)", x_nullable=True),
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
        
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        
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
        
        if calculation_mode not in CalculationModes.VALID_MODES:
            return Response(
                {"error": f"calculation_mode должен быть {CalculationModes.MODE_1} или {CalculationModes.MODE_2}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        monthly_payments = []
        has_application = False
        
        if calculation_mode == CalculationModes.MODE_1:
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
            
            is_no_installment = tariff.name and TariffConstants.NO_INSTALLMENT_KEYWORD in tariff.name
            
            total_product_sum = 0
            products_data = []
            
            product_ids = [item.get('product_id') for item in product_list]
            products = Products.objects.prefetch_related('details', 'ids').filter(id__in=product_ids)
            products_dict = {p.id: p for p in products}
            
            product_ids_objs = ProductIDs.objects.filter(product_id__in=product_ids).select_related('product')
            product_ids_dict = {}
            variation_dict = {}
            
            for pid_obj in product_ids_objs:
                if pid_obj.product_id not in product_ids_dict:
                    product_ids_dict[pid_obj.product_id] = []
                product_ids_dict[pid_obj.product_id].append(pid_obj)
                
                key = (pid_obj.product_id, str(pid_obj.variation_id) if pid_obj.variation_id else None)
                variation_dict[key] = pid_obj
            
            for item in product_list:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 1)
                variation_id = item.get('variation_id')
                
                product = products_dict.get(product_id)
                if not product:
                    continue
                
                product_price = None
                
                if variation_id:
                    key = (product_id, str(variation_id))
                    product_id_obj = variation_dict.get(key)
                    
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
                            # Agar variation_name'da SIM ma'lumoti bo'lmasa, SIM matching shart emas
                            variation_has_sim_info = "SIM" in variation_name or "DUAL" in variation_name or "ESIM" in variation_name
                            
                            if sim:
                                sim_normalized = sim.replace("+", "").replace(" ", "").upper()
                                variation_name_normalized = variation_name.replace(" ", "").replace("+", "")
                                
                                if sim.upper() in variation_name:
                                    sim_match = True
                                elif sim_normalized and sim_normalized in variation_name_normalized:
                                    sim_match = True
                                elif "SIM" in sim_normalized and "SIM" in variation_name:
                                    sim_match = True
                                elif "DUAL" in sim_normalized and "DUAL" in variation_name:
                                    sim_match = True
                                elif "ESIM" in sim_normalized and "ESIM" in variation_name:
                                    sim_match = True
                            
                            # Agar variation_name'da SIM ma'lumoti bo'lmasa, SIM matching shart emas
                            sim_required = bool(sim) and variation_has_sim_info
                            
                            if color_match and storage_match and (sim_match if sim_required else True):
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
                
                # Response uchun variation_id: agar request'da variation_id bo'lsa, uni ishlatish, aks holda birinchi topilganini
                response_variation_id = None
                if variation_id:
                    # Request'dan kelgan variation_id ni ishlatish
                    response_variation_id = variation_id
                else:
                    # Agar variation_id bo'lmasa, birinchi topilganini ishlatish
                    product_id_obj = product_ids_dict.get(product_id, [None])[0] if product_ids_dict.get(product_id) else None
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
                    total_product_sum * get_tariff_coefficient_ratio(tariff)
                )
            else:
                monthly_payment_amount = 0
            
            minimum_contribution = 0
            application_status = None
            counterparty_id_for_response = None
            
            if is_no_installment:
                pass
            elif user:
                try:
                    with ThreadPoolExecutor(max_workers=3) as executor:
                        application_future = executor.submit(get_application)
                        grist_products_future = executor.submit(get_products_in_grist)
                        counterparty_future = executor.submit(get_user_counterparty_id, user)
                        
                        application_data = application_future.result()
                        grist_products_data = grist_products_future.result()
                        counterparty_id = counterparty_future.result()
                    
                    applications = application_data.get('records', [])
                    grist_products = grist_products_data.get('records', [])
                    counterparty_id_for_response = counterparty_id
                    
                    if counterparty_id:
                        grist_product_map = {}
                        for grist_product in grist_products:
                            grist_id = grist_product.get('id')
                            price_category_id = grist_product.get('fields', {}).get('price_category_id')
                            if grist_id and price_category_id:
                                grist_product_map[grist_id] = price_category_id
                        
                        latest_app = get_latest_application_by_counterparty(applications, counterparty_id)
                        
                        if latest_app:
                            latest_stage = latest_app.get('fields', {}).get('stage', '')
                            # "Denied by client" holatida ham yangi application yaratishga ruxsat beriladi (Success kabi)
                            # Shuning uchun "Denied by client" holatida application_status ni o'rnatmaslik
                            # "Denied" holatida ham cooldown period o'tgan bo'lsa, application_status ni o'rnatmaslik
                            if latest_stage != ApplicationStages.DENIED_BY_CLIENT:
                                # "Denied" holatida cooldown period tekshiruvi keyinroq qilinadi
                                if latest_stage != ApplicationStages.DENIED:
                                    application_status = latest_stage
                            
                            if latest_stage in [ApplicationStages.ACCEPTED, ApplicationStages.DENIED]:
                                risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                
                                if risk_category_id:
                                    # Risk category ma'lumotlarini olish
                                    try:
                                        risk_category_obj = ProductRiskCategory.objects.filter(grist_risk_category_id=str(risk_category_id)).first()
                                    except Exception:
                                        pass
                                    
                                    price_category_ids = set()
                                    grist_product_ids_list = []
                                    
                                    for prod_data in products_data:
                                        product = prod_data['product']
                                        product_id_obj = product_ids_dict.get(product.id, [None])[0] if product_ids_dict.get(product.id) else None
                                        if product_id_obj and product_id_obj.grist_product_id:
                                            try:
                                                grist_product_id = int(product_id_obj.grist_product_id)
                                                if grist_product_id in grist_product_map:
                                                    price_category_id = grist_product_map[grist_product_id]
                                                    price_category_ids.add(str(price_category_id))
                                                    grist_product_ids_list.append((product.id, grist_product_id, price_category_id))
                                            except (ValueError, TypeError):
                                                pass
                                    
                                    risk_category_dict = {}
                                    if price_category_ids:
                                        risk_categories = ProductRiskCategory.objects.filter(
                                            grist_risk_category_id=str(risk_category_id),
                                            grist_price_category_id__in=price_category_ids
                                        )
                                        
                                        risk_category_dict = {
                                            rc.grist_price_category_id: rc 
                                            for rc in risk_categories
                                        }
                                    
                                    for prod_idx, prod_data in enumerate(products_data):
                                        product = prod_data['product']
                                        quantity = prod_data['quantity']
                                        product_price = prod_data['price']
                                        
                                        product_id_obj = product_ids_dict.get(product.id, [None])[0] if product_ids_dict.get(product.id) else None
                                        if product_id_obj and product_id_obj.grist_product_id:
                                            try:
                                                grist_product_id = int(product_id_obj.grist_product_id)
                                                if grist_product_id in grist_product_map:
                                                    price_category_id = str(grist_product_map[grist_product_id])
                                                    
                                                    product_risk_category = risk_category_dict.get(price_category_id)
                                                    if product_risk_category:
                                                        percentage = product_risk_category.percentage or 0
                                                        product_total = product_price * quantity
                                                        contribution = product_total * percentage
                                                        
                                                        minimum_contribution += contribution
                                            except (ValueError, TypeError):
                                                pass
                                    
                                    # Issue limit bilan solishtirish
                                    issue_limit = latest_app.get('fields', {}).get('issue_limit')
                                    if issue_limit is not None:
                                        try:
                                            issue_limit = float(issue_limit)
                                            
                                            # Product sum dan issue_limit ni ayirish
                                            product_sum_minus_issue_limit = original_total_product_sum - issue_limit
                                            
                                            # Minimum contribution bilan solishtirish va eng kattasini olish
                                            minimum_contribution = max(minimum_contribution, product_sum_minus_issue_limit)
                                        except (ValueError, TypeError):
                                            pass
                            elif latest_stage in [ApplicationStages.ASSESSMENT, ApplicationStages.NEW]:
                                minimum_contribution = 0
                            elif latest_stage == ApplicationStages.DENIED_BY_CLIENT:
                                minimum_contribution = 0
                            
                            if latest_stage in [ApplicationStages.NEW, ApplicationStages.ASSESSMENT]:
                                pass
                            elif latest_stage == ApplicationStages.DENIED_BY_CLIENT:
                                # "Denied by client" holatida ham yangi application yaratishga ruxsat beriladi (Success kabi)
                                # Shuning uchun application_status ni o'rnatmaslik, post qilish kodini ishlatish uchun
                                ability_to_order = False
                            elif latest_stage == ApplicationStages.DENIED:
                                # Faqat request'dagi productlar bilan mos keladigan "Denied" application'larni tekshirish
                                app_products_match = compare_application_products_with_request(latest_app, product_list)
                                
                                if app_products_match:
                                    # Agar bu application request'dagi productlar bilan mos kelsa, Denied holatini tekshirish
                                    denied_app = latest_app
                                    denied_date = denied_app.get('fields', {}).get('date', 0)
                                    
                                    if denied_date:
                                        denied_datetime = datetime.fromtimestamp(denied_date)
                                        current_datetime = datetime.now()
                                        days_passed = (current_datetime - denied_datetime).days
                                        
                                        if days_passed < TimeConstants.DENIED_COOLDOWN_DAYS:
                                            # Hali cooldown period ichida, Denied holatini o'rnatish
                                            application_status = ApplicationStages.DENIED
                                            ability_to_order = False
                                        # Agar days_passed >= DENIED_COOLDOWN_DAYS bo'lsa, application_status ni o'rnatmaslik
                                        # va post qilish kodini ishlatish uchun (cooldown period o'tgan)
                                        # Bu holatda application_status None bo'lib qoladi va keyinroq post qilish kodini ishlatish mumkin
                                    else:
                                        # Date bo'lmasa, Denied holatini o'rnatish
                                        application_status = ApplicationStages.DENIED
                                        ability_to_order = False
                                # Agar bu application boshqa productlar uchun bo'lsa, application_status ni o'rnatmaslik
                                # va post qilish kodini ishlatish uchun
                            elif latest_stage == ApplicationStages.ACCEPTED:
                                from django.utils import timezone
                                import pytz
                                
                                today = datetime.now().date()
                                today_datetime = datetime.combine(today, datetime.min.time())
                                today_datetime_utc = timezone.make_aware(today_datetime, pytz.UTC)
                                today_timestamp = int(today_datetime_utc.timestamp())
                                today_start = today_timestamp
                                today_end = today_timestamp + 86400
                                
                                today_accepted_apps = []
                                for app in applications:
                                    app_counterparty_id = app.get('fields', {}).get('counterparty_id')
                                    app_stage = app.get('fields', {}).get('stage', '')
                                    app_date = app.get('fields', {}).get('date')
                                    
                                    if app_counterparty_id == counterparty_id and app_stage == ApplicationStages.ACCEPTED and app_date:
                                        app_date_timestamp = None
                                        if isinstance(app_date, (int, float)):
                                            app_date_timestamp = int(app_date)
                                        elif isinstance(app_date, str):
                                            try:
                                                parsed_date = datetime.strptime(app_date, "%Y-%m-%d").date()
                                                parsed_datetime = datetime.combine(parsed_date, datetime.min.time())
                                                parsed_datetime_utc = timezone.make_aware(parsed_datetime, pytz.UTC)
                                                app_date_timestamp = int(parsed_datetime_utc.timestamp())
                                            except:
                                                pass
                                        
                                        if app_date_timestamp and today_start <= app_date_timestamp < today_end:
                                            today_accepted_apps.append(app)
                                
                                found_today_accepted = False
                                for today_app in today_accepted_apps:
                                    products_match = compare_application_products_with_request(today_app, product_list)
                                    
                                    if products_match:
                                        found_today_accepted = True
                                        application_status = 'Accepted'
                                        break
                                
                                if not found_today_accepted:
                                    # Check if should post using ApplicationService
                                    should_post, reason = ApplicationService.should_post_to_grist(
                                        user=user,
                                        applications=applications,
                                        counterparty_id=counterparty_id,
                                        product_list=product_list
                                    )
                                    
                                    if not should_post:
                                        logger.info(f"Application posting blocked: {reason}", extra={
                                            'user_id': user.id if user else None,
                                            'counterparty_id': counterparty_id
                                        })
                                    
                                    if should_post:
                                        grist_product_ids = get_grist_product_ids_from_request(product_list)
                                        
                                        from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                        product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                        
                                        risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                        
                                        try:
                                            current_date_str = datetime.now().strftime("%Y-%m-%d")
                                            
                                            result = post_to_grist_application(
                                                counterparty_id=counterparty_id,
                                                date=current_date_str,
                                                stage=ApplicationStages.NEW,
                                                risk_category_id=risk_category_id,
                                                issue_limit=float(total_down_payment),
                                                products=product_ids_for_application
                                            )
                                            
                                            if result:
                                                application_status = ApplicationStages.NEW
                                                minimum_contribution = 0
                                        except ValueError as e:
                                            logger.warning(f"Invalid value in post_to_grist_application: {e}", extra={
                                                'user_id': user.id if user else None,
                                                'counterparty_id': counterparty_id
                                            })
                                        except KeyError as e:
                                            logger.warning(f"Missing key in post_to_grist_application: {e}")
                                        except Exception as e:
                                            logger.error(f"Unexpected error in post_to_grist_application: {e}", exc_info=True, extra={
                                                'user_id': user.id if user else None,
                                                'counterparty_id': counterparty_id
                                            })
                            
                            if application_status not in [ApplicationStages.ACCEPTED, ApplicationStages.DENIED, ApplicationStages.DENIED_BY_CLIENT]:
                                # Success, Denied by client yoki Denied (cooldown period o'tgan) stage kelganda post qilish mumkin
                                # Denied holatida ham cooldown period o'tgan bo'lsa (application_status None bo'lsa), post qilish mumkin
                                if (latest_stage == ApplicationStages.SUCCESS or 
                                    latest_stage == ApplicationStages.DENIED_BY_CLIENT or
                                    latest_stage == ApplicationStages.DENIED):
                                    # Denied holatida ham cooldown period o'tgan bo'lsa (application_status None), post qilish mumkin
                                    should_post, reason = ApplicationService.should_post_to_grist(
                                        user=user,
                                        applications=applications,
                                        counterparty_id=counterparty_id,
                                        product_list=product_list
                                    )
                                    
                                    if not should_post:
                                        logger.info(f"Application posting blocked ({latest_stage} stage): {reason}", extra={
                                            'user_id': user.id if user else None,
                                            'counterparty_id': counterparty_id
                                        })
                                    
                                    if should_post:
                                        grist_product_ids = get_grist_product_ids_from_request(product_list)
                                        
                                        from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                        product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                        
                                        risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                        
                                        try:
                                            current_date_str = datetime.now().strftime("%Y-%m-%d")
                                            
                                            result = post_to_grist_application(
                                                counterparty_id=counterparty_id,
                                                date=current_date_str,
                                                stage=ApplicationStages.NEW,
                                                risk_category_id=risk_category_id,
                                                issue_limit=float(total_down_payment),
                                                products=product_ids_for_application
                                            )
                                            
                                            if result:
                                                application_status = ApplicationStages.NEW
                                                minimum_contribution = 0
                                        except ValueError as e:
                                            logger.warning(f"Invalid value in post_to_grist_application: {e}", extra={
                                                'user_id': user.id if user else None,
                                                'counterparty_id': counterparty_id
                                            })
                                        except KeyError as e:
                                            logger.warning(f"Missing key in post_to_grist_application: {e}")
                                        except Exception as e:
                                            logger.error(f"Unexpected error in post_to_grist_application: {e}", exc_info=True, extra={
                                                'user_id': user.id if user else None,
                                                'counterparty_id': counterparty_id
                                            })
                            
                            # "Denied by client" holatida post qilishdan keyin yoki post qilish bo'lmasa, application_status ni o'rnatish
                            if latest_stage == ApplicationStages.DENIED_BY_CLIENT and application_status not in [ApplicationStages.ACCEPTED, ApplicationStages.NEW]:
                                application_status = ApplicationStages.DENIED_BY_CLIENT
                                
                                if application_status not in [ApplicationStages.ACCEPTED, ApplicationStages.NEW]:
                                    # Check if should post using ApplicationService
                                    should_post, reason = ApplicationService.should_post_to_grist(
                                        user=user,
                                        applications=applications,
                                        counterparty_id=counterparty_id,
                                        product_list=product_list
                                    )
                                    
                                    if not should_post:
                                        logger.info(f"Application posting blocked: {reason}", extra={
                                            'user_id': user.id if user else None,
                                            'counterparty_id': counterparty_id
                                        })
                                    
                                    if should_post:
                                        grist_product_ids = get_grist_product_ids_from_request(product_list)
                                        
                                        from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                        product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                        
                                        risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                        
                                        try:
                                            current_date_str = datetime.now().strftime("%Y-%m-%d")
                                            
                                            result = post_to_grist_application(
                                                counterparty_id=counterparty_id,
                                                date=current_date_str,
                                                stage=ApplicationStages.NEW,
                                                risk_category_id=risk_category_id,
                                                issue_limit=float(total_down_payment),
                                                products=product_ids_for_application
                                            )
                                            
                                            if result:
                                                application_status = ApplicationStages.NEW
                                        except Exception:
                                            pass
                            
                            if application_status != ApplicationStages.ACCEPTED:
                                minimum_contribution = 0
                        else:
                            grist_product_ids = get_grist_product_ids_from_request(product_list)
                            
                            from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                            product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                            
                            risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                            
                            # Tekshiruvlar: post qilishni to'xtatadigan holatlar
                            should_post = True
                            
                            # 1. Faol orderlar tekshiruvi
                            if has_active_orders(user):
                                should_post = False
                            
                            # 2. Denied by client tekshiruvi olib tashlandi - endi "Denied by client" holatida ham post qilish mumkin
                            
                            # 3. Accepted lekin Order tablega qo'shilmagan tekshiruvi
                            if has_accepted_but_not_in_orders(user, applications, counterparty_id, product_list):
                                should_post = False
                            
                            # 4. Denied 30 kundan kam o'tgan tekshiruvi (faqat request'dagi productlar uchun)
                            if has_denied_within_30_days(applications, counterparty_id, product_list):
                                should_post = False
                            
                            if should_post:
                                try:
                                    current_date_str = datetime.now().strftime("%Y-%m-%d")
                                    
                                    result = post_to_grist_application(
                                        counterparty_id=counterparty_id,
                                        date=current_date_str,
                                        stage=ApplicationStages.NEW,
                                        risk_category_id=risk_category_id,
                                        issue_limit=float(total_down_payment),
                                        products=product_ids_for_application
                                    )
                                    
                                    if result:
                                        application_status = ApplicationStages.NEW
                                except Exception:
                                    pass
                            
                            minimum_contribution = 0
                except Exception as e:
                    minimum_contribution = 0
                    application_status = None
            
            # Generate monthly payments using utility
            if not is_no_installment and monthly_payment_amount > 0:
                monthly_payments = generate_monthly_payments(
                    tariff=tariff,
                    total_amount=monthly_payment_amount,
                    start_date=datetime.now()
                )
        
        elif calculation_mode == CalculationModes.MODE_2:
            original_total_product_sum = 0
            total_product_sum = 0
            total_down_payment = 0
            minimum_contribution = 0
            all_payments = []  # Barcha to'lovlarni saqlash uchun list
            max_months = 0
            total_remaining_after_advance = 0
            
            has_application = False
            counterparty_id = None
            grist_product_map = {}
            applications = []
            application_status = None
            
            if user:
                try:
                    with ThreadPoolExecutor(max_workers=3) as executor:
                        application_future = executor.submit(get_application)
                        grist_products_future = executor.submit(get_products_in_grist)
                        counterparty_future = executor.submit(get_user_counterparty_id, user)
                        
                        application_data = application_future.result()
                        grist_products_data = grist_products_future.result()
                        counterparty_id = counterparty_future.result()
                    
                    applications = application_data.get('records', [])
                    grist_products = grist_products_data.get('records', [])
                    counterparty_id_for_response = counterparty_id
                    
                    for grist_product in grist_products:
                        grist_id = grist_product.get('id')
                        price_category_id = grist_product.get('fields', {}).get('price_category_id')
                        if grist_id and price_category_id:
                            grist_product_map[grist_id] = price_category_id
                    
                    if counterparty_id:
                        latest_app = get_latest_application_by_counterparty(applications, counterparty_id)
                        
                        if latest_app:
                            has_application = True
                            application_status = latest_app.get('fields', {}).get('stage', '')
                        else:
                            has_application = False
                            application_status = None
                    else:
                        has_application = False
                        application_status = None
                except ValueError as e:
                    logger.warning(f"Invalid value in CalculatePaymentScheduleView mode 2: {e}", extra={
                        'user_id': user.id if user else None
                    })
                except KeyError as e:
                    logger.warning(f"Missing key in CalculatePaymentScheduleView mode 2: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error in CalculatePaymentScheduleView mode 2: {e}", exc_info=True, extra={
                        'user_id': user.id if user else None
                    })
            
            product_ids = [item.get('product_id') for item in product_list if item.get('product_id')]
            products = Products.objects.prefetch_related('details', 'ids').filter(id__in=product_ids)
            products_dict = {p.id: p for p in products}
            
            tariff_ids = [item.get('tariff_id') for item in product_list if item.get('tariff_id')]
            tariffs = Tariffs.objects.filter(id__in=tariff_ids)
            tariffs_dict = {t.id: t for t in tariffs}
            
            # Build variation dict using service
            product_ids_objs_mode2 = ProductIDs.objects.filter(product_id__in=product_ids).select_related('product')
            variation_dict_mode2, product_ids_dict_mode2 = ProductPriceService.build_variation_dict(product_ids_objs_mode2)
            
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
                
                product = products_dict.get(product_id)
                if not product:
                    continue
                
                tariff = tariffs_dict.get(item_tariff_id)
                if not tariff:
                    continue
                
                is_no_installment = tariff.name and TariffConstants.NO_INSTALLMENT_KEYWORD in tariff.name
                
                # Get product price using service
                product_price = ProductPriceService.get_product_price(
                    product=product,
                    variation_id=variation_id,
                    variation_dict=variation_dict_mode2,
                    product_ids_dict=product_ids_dict_mode2
                )
                
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
                
                if not is_no_installment:
                    if product_remaining > 0:
                        product_monthly_payment = round(
                            product_remaining * get_tariff_coefficient_ratio(tariff)
                        )
                    else:
                        product_monthly_payment = 0
                    
                    current_date = datetime.now()
                    
                    safe_payments_count = tariff.payments_count if tariff.payments_count and tariff.payments_count > 0 else 1
                    for month_num in range(1, safe_payments_count + 1):
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
                        
                        # Har bir to'lovni alohida saqlash (date va payment bilan)
                        all_payments.append({
                            'date': payment_date,
                            'payment': product_monthly_payment
                        })
                        max_months = max(max_months, month_num)
            
            # Barcha to'lovlarni date bo'yicha birlashtirish
            merged_payments_by_date = {}
            for payment in all_payments:
                date_key = payment['date'].strftime("%d/%m/%y")
                if date_key not in merged_payments_by_date:
                    merged_payments_by_date[date_key] = {
                        'date': payment['date'],
                        'amount': 0
                    }
                merged_payments_by_date[date_key]['amount'] += payment['payment']
            
            # Date bo'yicha sortirovka qilish
            sorted_payments = sorted(merged_payments_by_date.items(), key=lambda x: x[1]['date'])
            
            # Qaytadan numeratsiya qilish
            monthly_payments = []
            for idx, (date_key, payment_data) in enumerate(sorted_payments, start=1):
                monthly_payments.append({
                    "number": idx,
                    "date": date_key,
                    "payment": payment_data['amount']
                })
            
            # Birinchi oylik to'lov miqdorini olish
            monthly_payment_amount = monthly_payments[0]['payment'] if monthly_payments else 0
            
            if user and counterparty_id:
                try:
                    today_app = get_today_application_by_counterparty(applications, counterparty_id)
                    
                    if today_app:
                        today_stage = today_app.get('fields', {}).get('stage', '')
                        application_status = today_stage
                        
                        if today_stage in ['Accepted', 'Denied']:
                            risk_category_id = today_app.get('fields', {}).get('risk_category_id')
                            if risk_category_id:
                                for item in product_list:
                                    product_id = item.get('product_id')
                                    quantity = item.get('quantity', 1)
                                    variation_id = item.get('variation_id')
                                    
                                    try:
                                        product = Products.objects.get(id=product_id)
                                        product_id_obj = ProductIDs.objects.filter(
                                            product=product,
                                            variation_id=str(variation_id) if variation_id else None
                                        ).first()
                                        
                                        if not product_id_obj and variation_id is None:
                                            product_id_obj = ProductIDs.objects.filter(product=product).first()
                                        
                                        grist_product_id = product_id_obj.grist_product_id if product_id_obj else None
                                        
                                        if grist_product_id:
                                            try:
                                                grist_product_id = int(grist_product_id)
                                                if grist_product_id in grist_product_map:
                                                    price_category_id = grist_product_map[grist_product_id]
                                                    
                                                    try:
                                                        product_risk_category = ProductRiskCategory.objects.get(
                                                            grist_risk_category_id=str(risk_category_id),
                                                            grist_price_category_id=str(price_category_id)
                                                        )
                                                        percentage = product_risk_category.percentage or 0
                                                        
                                                        product_price = None
                                                        if variation_id:
                                                            product_id_obj_var = ProductIDs.objects.filter(
                                                                product=product, variation_id=str(variation_id)
                                                            ).first()
                                                            if product_id_obj_var:
                                                                details = product.details.all()
                                                                for detail in details:
                                                                    if detail.price:
                                                                        product_price = float(detail.price)
                                                                        break
                                                        
                                                        if product_price is None:
                                                            product_price = float(product.price) if product.price else 0
                                                        
                                                        product_total = product_price * quantity
                                                        contribution = product_total * percentage
                                                        minimum_contribution += contribution
                                                    except (ProductRiskCategory.DoesNotExist, Exception):
                                                        pass
                                            except (ValueError, TypeError):
                                                pass
                                    except Products.DoesNotExist:
                                        pass
                                
                                # Issue limit bilan solishtirish
                                # Barcha productlarning pricelarini qo'shib, keyin issue_limit ni ayirish
                                issue_limit = today_app.get('fields', {}).get('issue_limit')
                                if issue_limit is not None:
                                    try:
                                        issue_limit = float(issue_limit)
                                        
                                        # Barcha productlarning pricelarini qo'shib, keyin issue_limit ni ayirish
                                        # original_total_product_sum allaqachon barcha productlarning pricelarini o'z ichiga oladi
                                        product_sum_minus_issue_limit = original_total_product_sum - issue_limit
                                        
                                        # Minimum contribution bilan solishtirish va eng kattasini olish
                                        minimum_contribution = max(minimum_contribution, product_sum_minus_issue_limit)
                                    except (ValueError, TypeError):
                                        pass
                        elif today_stage == 'Denied by client':
                            minimum_contribution = 0
                        elif today_stage in ['Assessment', 'New']:
                            minimum_contribution = 0
                        
                        if today_stage in ['Accepted', 'Success', 'Denied by client'] and are_all_today_applications_accepted(applications, counterparty_id):
                            if today_stage == 'Accepted':
                                products_match = compare_application_products_with_request(today_app, product_list)
                                
                                if products_match:
                                    application_status = 'Accepted'
                                else:
                                    grist_product_ids = get_grist_product_ids_from_request(product_list)
                                    
                                    from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                    product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                    
                                    risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                    current_date_str = datetime.now().strftime("%Y-%m-%d")
                                    
                                    total_advance_payment_mode2 = sum(item.get('advance_payment', 0) for item in product_list)
                                    
                                    # Check if should post using ApplicationService
                                    should_post, reason = ApplicationService.should_post_to_grist(
                                        user=user,
                                        applications=applications,
                                        counterparty_id=counterparty_id,
                                        product_list=product_list
                                    )
                                    
                                    if not should_post:
                                        logger.info(f"Application posting blocked (Mode 2 - Accepted): {reason}", extra={
                                            'user_id': user.id if user else None,
                                            'counterparty_id': counterparty_id
                                        })
                                    
                                    if should_post:
                                        try:
                                            result = post_to_grist_application(
                                                counterparty_id=counterparty_id,
                                                date=current_date_str,
                                                stage=ApplicationStages.NEW,
                                                risk_category_id=risk_category_id,
                                                issue_limit=float(total_advance_payment_mode2),
                                                products=product_ids_for_application
                                            )
                                            
                                            if result:
                                                application_status = ApplicationStages.NEW
                                        except Exception as e:
                                            pass
                            elif today_stage == 'Success' or today_stage == 'Denied by client':
                                grist_product_ids = get_grist_product_ids_from_request(product_list)
                                
                                from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                
                                risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                current_date_str = datetime.now().strftime("%Y-%m-%d")
                                
                                total_advance_payment_mode2 = sum(item.get('advance_payment', 0) for item in product_list)
                                
                                # Check if should post using ApplicationService
                                should_post, reason = ApplicationService.should_post_to_grist(
                                    user=user,
                                    applications=applications,
                                    counterparty_id=counterparty_id,
                                    product_list=product_list
                                )
                                
                                if not should_post:
                                    logger.info(f"Application posting blocked (Mode 2 - {today_stage}): {reason}", extra={
                                        'user_id': user.id if user else None,
                                        'counterparty_id': counterparty_id
                                    })
                                
                                if should_post:
                                    try:
                                        result = post_to_grist_application(
                                            counterparty_id=counterparty_id,
                                            date=current_date_str,
                                            stage=ApplicationStages.NEW,
                                            risk_category_id=risk_category_id,
                                            issue_limit=float(total_advance_payment_mode2),
                                            products=product_ids_for_application
                                        )
                                        
                                        if result:
                                            application_status = ApplicationStages.NEW
                                    except Exception as e:
                                        pass
                                    
                                    # "Denied by client" holatida post qilishdan keyin yoki post qilish bo'lmasa, application_status ni o'rnatish
                                    if today_stage == 'Denied by client' and application_status not in ['Accepted', 'New']:
                                        application_status = 'Denied by client'
                    else:
                        latest_app = get_latest_application_by_counterparty(applications, counterparty_id)
                        
                        if latest_app:
                            latest_stage = latest_app.get('fields', {}).get('stage', '')
                            # "Denied by client" holatida ham yangi application yaratishga ruxsat beriladi (Success kabi)
                            # Shuning uchun "Denied by client" holatida application_status ni o'rnatmaslik
                            if latest_stage != 'Denied by client':
                                application_status = latest_stage
                            else:
                                application_status = None  # Post qilish kodini ishlatish uchun
                            
                            should_create_application = latest_stage in ['Accepted', 'Success', 'Denied by client']
                            
                            if latest_stage in [ApplicationStages.ACCEPTED, ApplicationStages.DENIED]:
                                risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                            
                            if risk_category_id:
                                price_category_ids = set()
                                product_data_list = []
                                
                                for item in product_list:
                                    product_id = item.get('product_id')
                                    quantity = item.get('quantity', 1)
                                    variation_id = item.get('variation_id')
                                    
                                    product = products_dict.get(product_id)
                                    if not product:
                                        continue
                                    
                                    key = (product_id, str(variation_id) if variation_id else None)
                                    product_id_obj = variation_dict_mode2.get(key)
                                    if not product_id_obj and variation_id is None:
                                        product_id_obj = product_ids_dict_mode2.get(product_id, [None])[0] if product_ids_dict_mode2.get(product_id) else None
                                    
                                    if product_id_obj and product_id_obj.grist_product_id:
                                        try:
                                            grist_product_id = int(product_id_obj.grist_product_id)
                                            if grist_product_id in grist_product_map:
                                                price_category_id = grist_product_map[grist_product_id]
                                                price_category_ids.add(str(price_category_id))
                                                product_data_list.append({
                                                    'product': product,
                                                    'quantity': quantity,
                                                    'variation_id': variation_id,
                                                    'grist_product_id': grist_product_id,
                                                    'price_category_id': price_category_id
                                                })
                                        except (ValueError, TypeError):
                                            pass
                                
                                risk_category_dict_mode2 = {}
                                if price_category_ids:
                                    risk_categories = ProductRiskCategory.objects.filter(
                                        grist_risk_category_id=str(risk_category_id),
                                        grist_price_category_id__in=price_category_ids
                                    )
                                    risk_category_dict_mode2 = {
                                        rc.grist_price_category_id: rc 
                                        for rc in risk_categories
                                    }
                                
                                for prod_data in product_data_list:
                                    product = prod_data['product']
                                    quantity = prod_data['quantity']
                                    variation_id = prod_data['variation_id']
                                    price_category_id = prod_data['price_category_id']
                                    
                                    product_risk_category = risk_category_dict_mode2.get(str(price_category_id))
                                    if product_risk_category:
                                        percentage = product_risk_category.percentage or 0
                                        
                                        product_price = None
                                        if variation_id:
                                            key = (product.id, str(variation_id))
                                            product_id_obj_var = variation_dict_mode2.get(key)
                                            if product_id_obj_var:
                                                details = product.details.all()
                                                for detail in details:
                                                    if detail.price:
                                                        product_price = float(detail.price)
                                                        break
                                        
                                        if product_price is None:
                                            product_price = float(product.price) if product.price else 0
                                        
                                        product_total = product_price * quantity
                                        contribution = product_total * percentage
                                        minimum_contribution += contribution
                                
                                # Issue limit bilan solishtirish
                                # Barcha productlarning pricelarini qo'shib, keyin issue_limit ni ayirish
                                issue_limit = latest_app.get('fields', {}).get('issue_limit')
                                if issue_limit is not None:
                                    try:
                                        issue_limit = float(issue_limit)
                                        
                                        # Barcha productlarning pricelarini qo'shib, keyin issue_limit ni ayirish
                                        # original_total_product_sum allaqachon barcha productlarning pricelarini o'z ichiga oladi
                                        product_sum_minus_issue_limit = original_total_product_sum - issue_limit
                                        
                                        # Minimum contribution bilan solishtirish va eng kattasini olish
                                        minimum_contribution = max(minimum_contribution, product_sum_minus_issue_limit)
                                    except (ValueError, TypeError):
                                        pass
                            elif latest_stage == 'Denied by client':
                                minimum_contribution = 0
                            elif latest_stage in ['Assessment', 'New']:
                                minimum_contribution = 0
                            
                            if latest_stage == 'Denied by client':
                                # "Denied by client" holatida ham yangi application yaratishga ruxsat beriladi (Success kabi)
                                # Shuning uchun application_status ni o'rnatmaslik, post qilish kodini ishlatish uchun
                                ability_to_order = False
                                should_create_application = False
                            elif latest_stage == 'Denied':
                                denied_app = latest_app
                                denied_date = denied_app.get('fields', {}).get('date', 0)
                                
                                if denied_date:
                                    denied_datetime = datetime.fromtimestamp(denied_date)
                                    current_datetime = datetime.now()
                                    days_passed = (current_datetime - denied_datetime).days
                                    
                                    if days_passed < 30:
                                        application_status = 'Denied'
                                        ability_to_order = False
                                        should_create_application = False
                                else:
                                    application_status = 'Denied'
                                    ability_to_order = False
                                    should_create_application = False
                            
                            if should_create_application:
                                if latest_stage == 'Accepted':
                                    from django.utils import timezone
                                    import pytz
                                    
                                    today = datetime.now().date()
                                    today_datetime = datetime.combine(today, datetime.min.time())
                                    today_datetime_utc = timezone.make_aware(today_datetime, pytz.UTC)
                                    today_timestamp = int(today_datetime_utc.timestamp())
                                    today_start = today_timestamp
                                    today_end = today_timestamp + 86400
                                    
                                    today_accepted_apps = []
                                    for app in applications:
                                        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
                                        app_stage = app.get('fields', {}).get('stage', '')
                                        app_date = app.get('fields', {}).get('date')
                                        
                                        if app_counterparty_id == counterparty_id and app_stage == ApplicationStages.ACCEPTED and app_date:
                                            app_date_timestamp = None
                                            if isinstance(app_date, (int, float)):
                                                app_date_timestamp = int(app_date)
                                            elif isinstance(app_date, str):
                                                try:
                                                    parsed_date = datetime.strptime(app_date, "%Y-%m-%d").date()
                                                    parsed_datetime = datetime.combine(parsed_date, datetime.min.time())
                                                    parsed_datetime_utc = timezone.make_aware(parsed_datetime, pytz.UTC)
                                                    app_date_timestamp = int(parsed_datetime_utc.timestamp())
                                                except:
                                                    pass
                                            
                                            if app_date_timestamp and today_start <= app_date_timestamp < today_end:
                                                today_accepted_apps.append(app)
                                    
                                    found_today_accepted = False
                                    for today_app in today_accepted_apps:
                                        products_match = compare_application_products_with_request(today_app, product_list)
                                        
                                        if products_match:
                                            found_today_accepted = True
                                            application_status = 'Accepted'
                                            break
                                    
                                    if not found_today_accepted:
                                        # Check if should post using ApplicationService
                                        should_post, reason = ApplicationService.should_post_to_grist(
                                            user=user,
                                            applications=applications,
                                            counterparty_id=counterparty_id,
                                            product_list=product_list
                                        )
                                        
                                        if not should_post:
                                            logger.info(f"Application posting blocked (Mode 2 - No today accepted): {reason}", extra={
                                                'user_id': user.id if user else None,
                                                'counterparty_id': counterparty_id
                                            })
                                        
                                        if should_post:
                                            try:
                                                grist_product_ids = get_grist_product_ids_from_request(product_list)
                                                
                                                from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                                product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                                
                                                risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                                current_date_str = datetime.now().strftime("%Y-%m-%d")
                                                
                                                total_advance_payment_mode2 = sum(item.get('advance_payment', 0) for item in product_list)
                                                
                                                result = post_to_grist_application(
                                                    counterparty_id=counterparty_id,
                                                    date=current_date_str,
                                                    stage=ApplicationStages.NEW,
                                                    risk_category_id=risk_category_id,
                                                    issue_limit=float(total_advance_payment_mode2),
                                                    products=product_ids_for_application
                                                )
                                                
                                                if result:
                                                    application_status = ApplicationStages.NEW
                                            except Exception:
                                                pass
                                    
                                if application_status != 'Accepted' and application_status != 'Denied':
                                    if latest_stage == 'Success' or latest_stage == 'Denied by client':
                                        # Check if should post using ApplicationService
                                        should_post, reason = ApplicationService.should_post_to_grist(
                                            user=user,
                                            applications=applications,
                                            counterparty_id=counterparty_id,
                                            product_list=product_list
                                        )
                                        
                                        if not should_post:
                                            logger.info(f"Application posting blocked (Mode 2 - {latest_stage} stage): {reason}", extra={
                                                'user_id': user.id if user else None,
                                                'counterparty_id': counterparty_id
                                            })
                                        
                                        if should_post:
                                            try:
                                                grist_product_ids = get_grist_product_ids_from_request(product_list)
                                                
                                                from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                                product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                                
                                                risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                                current_date_str = datetime.now().strftime("%Y-%m-%d")
                                                
                                                total_advance_payment_mode2 = sum(item.get('advance_payment', 0) for item in product_list)
                                                
                                                result = post_to_grist_application(
                                                    counterparty_id=counterparty_id,
                                                    date=current_date_str,
                                                    stage=ApplicationStages.NEW,
                                                    risk_category_id=risk_category_id,
                                                    issue_limit=float(total_advance_payment_mode2),
                                                    products=product_ids_for_application
                                                )
                                                
                                                if result:
                                                    application_status = ApplicationStages.NEW
                                            except Exception as e:
                                                pass
                                        
                                        # "Denied by client" holatida post qilishdan keyin yoki post qilish bo'lmasa, application_status ni o'rnatish
                                        if latest_stage == 'Denied by client' and application_status not in ['Accepted', 'New']:
                                            application_status = 'Denied by client'
                        else:
                            if application_status != 'Accepted' and application_status != 'Denied':
                                grist_product_ids = get_grist_product_ids_from_request(product_list)
                                
                                from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                
                                risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                
                                # Check if should post using ApplicationService
                                should_post, reason = ApplicationService.should_post_to_grist(
                                    user=user,
                                    applications=applications,
                                    counterparty_id=counterparty_id,
                                    product_list=product_list
                                )
                                
                                if not should_post:
                                    logger.info(f"Application posting blocked (Mode 2 - No application): {reason}", extra={
                                        'user_id': user.id if user else None,
                                        'counterparty_id': counterparty_id
                                    })
                                
                                if should_post:
                                    try:
                                        current_date_str = datetime.now().strftime("%Y-%m-%d")
                                        
                                        total_advance_payment_mode2 = sum(item.get('advance_payment', 0) for item in product_list)
                                        
                                        result = post_to_grist_application(
                                            counterparty_id=counterparty_id,
                                            date=current_date_str,
                                            stage=ApplicationStages.NEW,
                                            risk_category_id=risk_category_id,
                                            issue_limit=float(total_advance_payment_mode2),
                                            products=product_ids_for_application
                                        )
                                        
                                        if result:
                                            application_status = ApplicationStages.NEW
                                    except Exception as e:
                                        pass
                            
                            minimum_contribution = 0
                except Exception:
                    application_status = None
                    minimum_contribution = 0
        
        ability_to_order = False
        
        if application_status == 'Accepted':
            if calculation_mode == 1:
                meets_minimum = float(total_down_payment) >= minimum_contribution if minimum_contribution > 0 else True
            elif calculation_mode == CalculationModes.MODE_2:
                meets_minimum = float(total_down_payment) >= minimum_contribution if minimum_contribution > 0 else True
            else:
                meets_minimum = True
            
            if meets_minimum:
                if user:
                    try:
                        latest_order = Orders.objects.filter(user=user).order_by('-created_at').first()
                        
                        if latest_order is None:
                            ability_to_order = True
                        elif latest_order.status == Orders.Status.FINISHED:
                            ability_to_order = True
                        elif latest_order.status in [Orders.Status.PREPARING, Orders.Status.READY, Orders.Status.DELIVERING]:
                            ability_to_order = False
                        else:
                            ability_to_order = False
                    except Exception as e:
                        ability_to_order = False
                else:
                    ability_to_order = False
            else:
                ability_to_order = False
        else:
            ability_to_order = False
        
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
        elif calculation_mode == CalculationModes.MODE_2:
            for item in product_list:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 1)
                item_advance_payment = item.get('advance_payment', 0)
                item_tariff_id = item.get('tariff_id')
                request_variation_id = item.get('variation_id')  # Request'dan kelgan variation_id
                
                try:
                    product = Products.objects.get(id=product_id)
                    
                    # Response uchun variation_id: agar request'da variation_id bo'lsa, uni ishlatish, aks holda birinchi topilganini
                    response_variation_id = None
                    if request_variation_id:
                        # Request'dan kelgan variation_id ni ishlatish
                        response_variation_id = request_variation_id
                    else:
                        # Agar variation_id bo'lmasa, birinchi topilganini ishlatish
                        product_id_obj = ProductIDs.objects.filter(product=product).first()
                        response_variation_id = product_id_obj.variation_id if product_id_obj and product_id_obj.variation_id else None
                    
                    response_product_list.append({
                        "product_id": product.id,
                        "quantity": quantity,
                        "variation_id": int(response_variation_id) if response_variation_id else None,
                        "tariff_id": int(item_tariff_id) if item_tariff_id else None,
                        "advance_payment": float(item_advance_payment)
                    })
                except Products.DoesNotExist:
                    continue
        
        if calculation_mode == 1:
            total_products_price = original_total_product_sum
        elif calculation_mode == CalculationModes.MODE_2:
            total_products_price = original_total_product_sum
            
            # Mode 2 da total_down_payment va minimum_contribution ni faqat tekshiruv uchun
            # Response'da asl total_down_payment qiymatini qaytarish kerak
        else:
            total_products_price = original_total_product_sum
        
        response_data = {
            "total_products_price": round(total_products_price, 2),
            "total_advance_payment": float(total_down_payment),
            "total_every_month_payment": monthly_payment_amount,
            "minimum_contribution": round(minimum_contribution, 2),
            "ability_to_order": ability_to_order,
            "status": application_status,
            "counterparty_id": counterparty_id_for_response,
            "monthly_payments": monthly_payments,
            "product_list": response_product_list
        }
        
        return Response(response_data, status=status.HTTP_200_OK)


class CalculatePaymentScheduleSimpleView(APIView):
    """
    Simplified view for calculating payment schedule - only returns monthly_payments and product_list.
    Does NOT post to ISell_APPLICATION or request ISell_COUNTERPARTIES.
    """
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Продукты'],
        operation_summary="Расчет графика платежей (упрощенный)",
        operation_description=""" 
        Рассчитывает график платежей на основе режима расчета.
        Возвращает только monthly_payments и product_list.
        Не создает заявки в Grist и не запрашивает данные о контрагентах.
        
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
                description="График платежей (упрощенный)",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
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
        
        if calculation_mode not in CalculationModes.VALID_MODES:
            return Response(
                {"error": f"calculation_mode должен быть {CalculationModes.MODE_1} или {CalculationModes.MODE_2}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        monthly_payments = []
        
        if calculation_mode == CalculationModes.MODE_1:
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
            
            is_no_installment = tariff.name and TariffConstants.NO_INSTALLMENT_KEYWORD in tariff.name
            
            # Get products and build dictionaries using service
            product_ids = [item.get('product_id') for item in product_list]
            products = Products.objects.prefetch_related('details', 'ids').filter(id__in=product_ids)
            products_dict = {p.id: p for p in products}
            
            product_ids_objs = ProductIDs.objects.filter(product_id__in=product_ids).select_related('product')
            variation_dict, product_ids_dict = ProductPriceService.build_variation_dict(product_ids_objs)
            
            # Process product list using service
            products_data, total_product_sum = ProductPriceService.process_product_list(
                product_list=product_list,
                products_dict=products_dict,
                variation_dict=variation_dict,
                product_ids_dict=product_ids_dict
            )
            
            # Calculate remaining amount after down payment
            original_total_product_sum = total_product_sum
            total_product_sum = max(0, total_product_sum - float(total_down_payment))
            
            # Calculate monthly payment amount using utility
            monthly_payment_amount = calculate_monthly_payment_amount(total_product_sum, tariff)
            
            # Generate monthly payments using utility
            if not is_no_installment and monthly_payment_amount > 0:
                monthly_payments = generate_monthly_payments(
                    tariff=tariff,
                    total_amount=monthly_payment_amount,
                    start_date=datetime.now()
                )
            
            response_product_list = []
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
        
        elif calculation_mode == CalculationModes.MODE_2:
            merged_payments = {}
            max_months = 0
            
            product_ids = [item.get('product_id') for item in product_list]
            products = Products.objects.prefetch_related('details', 'ids').filter(id__in=product_ids)
            products_dict = {p.id: p for p in products}
            
            tariff_ids = [item.get('tariff_id') for item in product_list if item.get('tariff_id')]
            tariffs = Tariffs.objects.filter(id__in=tariff_ids)
            tariffs_dict = {t.id: t for t in tariffs}
            
            # Build variation dict using service
            product_ids_objs_mode2 = ProductIDs.objects.filter(product_id__in=product_ids).select_related('product')
            variation_dict_mode2, product_ids_dict_mode2 = ProductPriceService.build_variation_dict(product_ids_objs_mode2)
            
            for item in product_list:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 1)
                variation_id = item.get('variation_id')
                item_tariff_id = item.get('tariff_id')
                item_advance_payment = item.get('advance_payment', 0)
                
                if not item_tariff_id:
                    continue
                
                tariff = tariffs_dict.get(item_tariff_id)
                if not tariff:
                    continue
                
                is_no_installment = tariff.name and TariffConstants.NO_INSTALLMENT_KEYWORD in tariff.name
                
                product = products_dict.get(product_id)
                if not product:
                    continue
                
                # Get product price using service
                product_price = ProductPriceService.get_product_price(
                    product=product,
                    variation_id=variation_id,
                    variation_dict=variation_dict_mode2,
                    product_ids_dict=product_ids_dict_mode2
                )
                
                if product_price is None:
                    continue
                
                total_product_price = product_price * quantity
                total_after_advance = max(0, total_product_price - float(item_advance_payment))
                
                if not is_no_installment:
                    # Calculate monthly payment using utility
                    monthly_payment = calculate_monthly_payment_amount(total_after_advance, tariff)
                    
                    safe_payments_count = tariff.payments_count if tariff.payments_count and tariff.payments_count > 0 else 1
                    
                    if safe_payments_count > max_months:
                        max_months = safe_payments_count
                    
                    if monthly_payment > 0:
                        # Generate monthly payments using utility
                        item_monthly_payments = generate_monthly_payments(
                            tariff=tariff,
                            total_amount=monthly_payment,
                            start_date=datetime.now()
                        )
                        
                        # Merge payments by date
                        for payment in item_monthly_payments:
                            date_key = payment['date']
                            if date_key not in merged_payments:
                                merged_payments[date_key] = {
                                    "number": payment['number'],
                                    "date": date_key,
                                    "payment": 0
                                }
                            merged_payments[date_key]["payment"] += payment['payment']
            
            monthly_payments = sorted(merged_payments.values(), key=lambda x: x["number"])
            
            response_product_list = []
            for item in product_list:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 1)
                item_advance_payment = item.get('advance_payment', 0)
                item_tariff_id = item.get('tariff_id')
                
                try:
                    product = products_dict.get(product_id)
                    if not product:
                        continue
                    
                    product_id_obj = product_ids_dict_mode2.get(product_id, [None])[0] if product_ids_dict_mode2.get(product_id) else None
                    variation_id = product_id_obj.variation_id if product_id_obj and product_id_obj.variation_id else None
                    
                    response_product_list.append({
                        "product_id": product.id,
                        "quantity": quantity,
                        "variation_id": int(variation_id) if variation_id else None,
                        "tariff_id": int(item_tariff_id) if item_tariff_id else None,
                        "advance_payment": float(item_advance_payment)
                    })
                except Exception:
                    continue
        
        response_data = {
            "monthly_payments": monthly_payments,
            "product_list": response_product_list
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
