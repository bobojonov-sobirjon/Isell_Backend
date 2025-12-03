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
        Logic:
        - Variatsiyasiz tovarlar: Products.is_actual = True bo'lsa chiqadi
        - Variatsiyali tovarlar: kamida bitta ProductIDs.is_actual = True bo'lsa chiqadi
        """
        name = request.query_params.get('name', None)
        category = request.query_params.get('category', None)
        
        # Barcha productlarni olamiz
        queryset = Products.objects.select_related(
            'category'
        ).prefetch_related(
            'details__images',
            'ids',
            'characteristics__property'
        ).filter(actual=True)
        
        # Variatsiyasiz tovarlar uchun: Products.is_actual = True bo'lishi kerak
        # Variatsiyali tovarlar uchun: kamida bitta ProductIDs.is_actual = True bo'lishi kerak
        
        from django.db.models import Q, Exists, OuterRef
        
        # Variatsiyasiz tovarlar: is_actual=True va variatsiya yo'q
        products_without_variations = queryset.filter(
            is_actual=True
        ).annotate(
            has_variations=Exists(
                ProductIDs.objects.filter(product=OuterRef('pk'))
            )
        ).filter(has_variations=False)
        
        # Variatsiyali tovarlar: kamida bitta ProductIDs.is_actual = True
        products_with_variations = queryset.filter(
            ids__is_actual=True
        ).distinct()
        
        # Ikkala querysetni birlashtiramiz
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

def get_tariff_coefficient_ratio(tariff):
    """
    Calculate tariff coefficient ratio safely, avoiding division by zero.
    If coefficient or payments_count is 0, use 1 instead.
    """
    coefficient = tariff.coefficient if tariff.coefficient and tariff.coefficient > 0 else 1
    payments_count = tariff.payments_count if tariff.payments_count and tariff.payments_count > 0 else 1
    return coefficient / payments_count

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
        
        product_price = None
        
        # Если передан variation_id, ищем цену в ProductDetails
        if variation_id:
            product_id_obj = ProductIDs.objects.filter(
                product=product,
                variation_id=str(variation_id)
            ).first()
            
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
        
        # Если variation_id не передан или не найден, берем цену из Product.price
        if product_price is None:
            if product.price is not None:
                product_price = float(product.price)
            else:
                # Если в Product.price тоже нет, берем минимальную цену из details
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
            get_tariff_coefficient_ratio(tariff)
        )
        
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

        # Convert user's date_of_birth to timestamp
        # date objects don't have timestamp(), so convert to datetime first
        # Grist stores timestamps in UTC, so we need to create UTC datetime
        if user.date_of_birth:
            # Create datetime at midnight UTC for the date
            # Use timezone-aware datetime to ensure UTC
            from django.utils import timezone
            import pytz
            
            user_dob_datetime = datetime.combine(user.date_of_birth, datetime.min.time())
            # Make it timezone-aware (UTC)
            user_dob_datetime_utc = timezone.make_aware(user_dob_datetime, pytz.UTC)
            user_dob_timestamp = int(user_dob_datetime_utc.timestamp())
        else:
            user_dob_timestamp = None
        
        for idx, counterparty in enumerate(counterparties):
            fields = counterparty.get('fields', {})
            pinfl = fields.get('pinfl', '')
            date_of_birth = fields.get('date_of_birth')
            counterparty_id = counterparty.get('id')

            # Check pnfl match
            pinfl_match = pinfl == user.pnfl

            # Check date_of_birth match
            # Handle different types: None, int, string, or datetime
            dob_match = False
            if date_of_birth is None and user_dob_timestamp is None:
                dob_match = True

            elif date_of_birth is not None and user_dob_timestamp is not None:
                try:
                    # If date_of_birth is a string (like "2000-05-18"), parse it
                    if isinstance(date_of_birth, str):
                        # Try to parse as date string
                        try:
                            from datetime import datetime as dt
                            parsed_date = dt.strptime(date_of_birth, "%Y-%m-%d").date()
                            # Convert to UTC timestamp
                            from django.utils import timezone
                            import pytz
                            
                            parsed_datetime = datetime.combine(parsed_date, datetime.min.time())
                            parsed_datetime_utc = timezone.make_aware(parsed_datetime, pytz.UTC)
                            grist_dob = int(parsed_datetime_utc.timestamp())

                        except ValueError:
                            # If parsing fails, try to convert directly to int
                            grist_dob = int(float(date_of_birth))

                    else:
                        # Convert to int if it's a float or already int
                        grist_dob = int(date_of_birth)
                    
                    # Compare timestamps (allow small difference due to timezone/rounding)
                    # Grist might store timestamps with slight differences, so we check if they're within 24 hours
                    time_diff = abs(grist_dob - user_dob_timestamp)
                    # Allow up to 12 hours difference (43200 seconds) for timezone issues
                    dob_match = time_diff < 43200

                except (ValueError, TypeError) as e:
                    dob_match = False
            else:
                pass
            
            if pinfl_match and dob_match:
                return counterparty_id

        return None
    except Exception as e:
        logger.error(f"Error getting user counterparty ID: {str(e)}", exc_info=True)
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

        # Check if user has any application (any stage)
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
    
    # Sort by id (highest = latest) and return the first one
    matching_apps.sort(key=lambda x: x.get('id', 0), reverse=True)
    return matching_apps[0]

def are_all_today_applications_accepted(applications, counterparty_id):
    """
    Check if all today's applications for a counterparty_id are "Accepted" or "Success"
    Returns True if all are Accepted/Success, False otherwise
    
    Проверяет, все ли заявки на сегодня для counterparty_id имеют статус "Accepted" или "Success"
    Возвращает True, если все Accepted/Success, иначе False
    """
    if not applications or not counterparty_id:
        return False
    
    from datetime import datetime
    from django.utils import timezone
    import pytz
    
    # Get today's date at midnight UTC
    today = datetime.now().date()
    today_datetime = datetime.combine(today, datetime.min.time())
    today_datetime_utc = timezone.make_aware(today_datetime, pytz.UTC)
    today_timestamp = int(today_datetime_utc.timestamp())
    
    # Also check for date range (start and end of day)
    today_start = today_timestamp
    today_end = today_timestamp + 86400  # 24 hours in seconds
    
    today_apps = []
    for app in applications:
        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
        app_date = app.get('fields', {}).get('date')
        
        if app_counterparty_id == counterparty_id and app_date:
            # Handle different date formats from Grist
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
            
            # Check if date matches today (within the day range)
            if app_date_timestamp and today_start <= app_date_timestamp < today_end:
                today_apps.append(app)
    
    if not today_apps:
        return False
    
    # Check if all today's applications are "Accepted" or "Success"
    for app in today_apps:
        stage = app.get('fields', {}).get('stage', '')
        if stage not in ['Accepted', 'Success']:
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
    
    # Get today's date at midnight UTC
    today = datetime.now().date()
    today_datetime = datetime.combine(today, datetime.min.time())
    today_datetime_utc = timezone.make_aware(today_datetime, pytz.UTC)
    today_timestamp = int(today_datetime_utc.timestamp())
    
    # Also check for date range (start and end of day)
    today_start = today_timestamp
    today_end = today_timestamp + 86400  # 24 hours in seconds
    
    matching_apps = []
    for app in applications:
        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
        app_date = app.get('fields', {}).get('date')
        
        if app_counterparty_id == counterparty_id and app_date:
            # Handle different date formats from Grist
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
            
            # Check if date matches today (within the day range)
            if app_date_timestamp and today_start <= app_date_timestamp < today_end:
                matching_apps.append(app)
    
    if not matching_apps:
        return None
    
    # Sort by id (highest = latest) and return the first one
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
            # Filter ProductIDs by product_id and variation_id
            if variation_id:
                product_id_obj = ProductIDs.objects.filter(
                    product_id=product_id,
                    variation_id=str(variation_id)
                ).first()
            else:
                # If no variation_id, get first ProductIDs for this product
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

def compare_application_products_with_request(application, product_list):
    """
    Compare products from application with products from request.
    
    Args:
        application: Application record from Grist (has fields.products which are Price table product_ids)
        product_list: List of products from request (has product_id and variation_id)
    
    Returns:
        True if products match, False otherwise
    """
    if not application or not product_list:
        return False
    
    try:
        # Get products from application (these are Price table product_ids)
        app_products = application.get('fields', {}).get('products', [])
        
        # Handle Grist reference list format: ["L", id1, id2, ...]
        if isinstance(app_products, list) and len(app_products) > 0 and app_products[0] == "L":
            app_products = app_products[1:] if len(app_products) > 1 else []
        
        # Convert to set for comparison (normalize to strings)
        app_products_set = set(str(p) for p in app_products if p)
        
        # Get grist_product_ids from request
        grist_product_ids = get_grist_product_ids_from_request(product_list)
        
        # Convert grist_product_ids to product_ids from Price table
        from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
        request_product_ids = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
        
        # Convert to set for comparison (normalize to strings)
        request_products_set = set(str(p) for p in request_product_ids if p)
        
        # Compare sets
        return app_products_set == request_products_set
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error comparing application products with request: {str(e)}", exc_info=True)
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
    
    # Priority 1: Try to get from latest application with "Accepted" or "Success" status
    latest_app = get_latest_application_by_counterparty(applications, counterparty_id)
    if latest_app:
        latest_stage = latest_app.get('fields', {}).get('stage', '')
        if latest_stage in ['Accepted', 'Success']:
            risk_category_id = latest_app.get('fields', {}).get('risk_category_id')
            if risk_category_id:
                return risk_category_id
    
    # Priority 2: Search in all applications with "Accepted" or "Success" status (sorted by id desc)
    approved_apps = []
    for app in applications:
        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
        app_stage = app.get('fields', {}).get('stage', '')
        if app_counterparty_id == counterparty_id and app_stage in ['Accepted', 'Success']:
            approved_apps.append(app)
    
    # Sort by id (highest = latest) and get first one with risk_category_id
    if approved_apps:
        approved_apps.sort(key=lambda x: x.get('id', 0), reverse=True)
        for app in approved_apps:
            risk_category_id = app.get('fields', {}).get('risk_category_id')
            if risk_category_id:
                return risk_category_id
    
    # Priority 3: Try to get from latest application (any status)
    if latest_app:
        risk_category_id = latest_app.get('fields', {}).get('risk_category_id')
        if risk_category_id:
            return risk_category_id
    
    # Priority 4: Search in all applications for this counterparty (sorted by id desc)
    all_apps = []
    for app in applications:
        app_counterparty_id = app.get('fields', {}).get('counterparty_id')
        if app_counterparty_id == counterparty_id:
            all_apps.append(app)
    
    # Sort by id (highest = latest) and get first one with risk_category_id
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

    if not user or not counterparty_id:

        return 0
    
    try:
        # Filter applications by counterparty_id and check for Accepted stage

        approved_applications = []
        for idx, app in enumerate(applications):
            app_counterparty_id = app.get('fields', {}).get('counterparty_id')
            app_stage = app.get('fields', {}).get('stage', '')
            app_id = app.get('id')

            # Only accept "Accepted" stage
            if app_counterparty_id == counterparty_id and app_stage == 'Accepted':

                approved_applications.append(app)

        if not approved_applications:

            return 0
        
        # Get risk_category_id from approved applications
        # If application is found, use its risk_category_id even if products don't match

        risk_category_id = None
        for app_idx, app in enumerate(approved_applications):
            app_products = app.get('fields', {}).get('products', [])
            app_risk_category_id = app.get('fields', {}).get('risk_category_id')
            app_id = app.get('id')

            # First, try to find matching product in app_products
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
                        else:
                            pass
                    except (ValueError, TypeError):
                        continue
                else:
                    pass
            
            # If no product match found but application exists, use its risk_category_id anyway
            if not product_found and app_risk_category_id:
                risk_category_id = app_risk_category_id

                break
            
            if risk_category_id:
                break
        
        if not risk_category_id:

            return 0

        # Calculate minimum_contribution for all products
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
                            # Try to find ProductRiskCategory

                            # Check what exists in database
                            all_risk_categories = ProductRiskCategory.objects.filter(
                                grist_risk_category_id=str(risk_category_id)
                            )

                            for rc in all_risk_categories:
                                pass
                            
                            product_risk_category = ProductRiskCategory.objects.get(
                                grist_risk_category_id=str(risk_category_id),
                                grist_price_category_id=str(price_category_id)
                            )
                            percentage = product_risk_category.percentage or 0
                            product_total = product_price * quantity
                            contribution = product_total * percentage
                            minimum_contribution += contribution

                        except ProductRiskCategory.DoesNotExist:

                            try:
                                available = ProductRiskCategory.objects.filter(
                                    grist_risk_category_id=str(risk_category_id)
                                )
                                for rc in available:
                                    pass
                            except:
                                pass
                            pass
                        except Exception:

                            pass
                else:
                    pass
        
        return minimum_contribution
    except Exception:
        return 0

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
        
        # Get user from request
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
        
        if calculation_mode not in [1, 2]:
            return Response(
                {"error": "calculation_mode должен быть 1 или 2"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        monthly_payments = []
        has_application = False  # Initialize for both modes
        
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
            
            total_product_sum = 0
            products_data = []
            
            # OPTIMIZATION: Barcha productlarni bir marta olish (bulk fetch)
            product_ids = [item.get('product_id') for item in product_list]
            products = Products.objects.prefetch_related('details', 'ids').filter(id__in=product_ids)
            products_dict = {p.id: p for p in products}
            
            # OPTIMIZATION: Barcha ProductIDs ni bir marta olish
            product_ids_objs = ProductIDs.objects.filter(product_id__in=product_ids).select_related('product')
            product_ids_dict = {}  # product_id -> [ProductIDs objects]
            variation_dict = {}    # (product_id, variation_id) -> ProductIDs object
            
            for pid_obj in product_ids_objs:
                # Asosiy mapping
                if pid_obj.product_id not in product_ids_dict:
                    product_ids_dict[pid_obj.product_id] = []
                product_ids_dict[pid_obj.product_id].append(pid_obj)
                
                # Variation mapping
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
                    # OPTIMIZATION: Dictionary dan olish
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
                
                # OPTIMIZATION: Dictionary dan olish
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
            import logging
            logger = logging.getLogger(__name__)
            
            logger.info(f"[CalculatePaymentScheduleView Mode 1] User: {user}, User ID: {user.id if user else None}")
            
            if user:
                try:
                    # Use ThreadPoolExecutor for concurrent API calls
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        application_future = executor.submit(get_application)
                        grist_products_future = executor.submit(get_products_in_grist)
                        
                        application_data = application_future.result()
                        grist_products_data = grist_products_future.result()
                    
                    applications = application_data.get('records', [])
                    grist_products = grist_products_data.get('records', [])
                    
                    logger.info(f"[CalculatePaymentScheduleView Mode 1] Applications count: {len(applications)}, Grist products count: {len(grist_products)}")
                    
                    # Get counterparty_id
                    counterparty_id = get_user_counterparty_id(user)
                    counterparty_id_for_response = counterparty_id
                    
                    logger.info(f"[CalculatePaymentScheduleView Mode 1] Counterparty ID: {counterparty_id}")
                    
                    if counterparty_id:
                        # Build grist_product_map
                        grist_product_map = {}
                        for grist_product in grist_products:
                            grist_id = grist_product.get('id')
                            price_category_id = grist_product.get('fields', {}).get('price_category_id')
                            if grist_id and price_category_id:
                                grist_product_map[grist_id] = price_category_id
                        
                        # First check for latest application (not just today's)
                        latest_app = get_latest_application_by_counterparty(applications, counterparty_id)
                        
                        logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest app found: {latest_app is not None}")
                        
                        if latest_app:
                            # Use latest application
                            latest_stage = latest_app.get('fields', {}).get('stage', '')
                            application_status = latest_stage
                            
                            logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest app stage: {latest_stage}")
                            
                            # Calculate minimum_contribution based on status
                            if latest_stage in ['Accepted', 'Denied']:
                                # Get risk_category_id from applications
                                risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                if risk_category_id:
                                    # OPTIMIZATION: Barcha kerakli price_category_id larni yig'ish
                                    price_category_ids = set()
                                    grist_product_ids_list = []
                                    
                                    for prod_data in products_data:
                                        product = prod_data['product']
                                        # Dictionary dan olish (yuqorida yaratilgan)
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
                                    
                                    # OPTIMIZATION: Barcha ProductRiskCategory ni bir marta olish
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
                                    
                                    # OPTIMIZATION: Loop ichida dictionary dan olish
                                    for prod_data in products_data:
                                        product = prod_data['product']
                                        quantity = prod_data['quantity']
                                        product_price = prod_data['price']
                                        
                                        # Dictionary dan olish
                                        product_id_obj = product_ids_dict.get(product.id, [None])[0] if product_ids_dict.get(product.id) else None
                                        if product_id_obj and product_id_obj.grist_product_id:
                                            try:
                                                grist_product_id = int(product_id_obj.grist_product_id)
                                                if grist_product_id in grist_product_map:
                                                    price_category_id = str(grist_product_map[grist_product_id])
                                                    
                                                    # Dictionary dan olish
                                                    product_risk_category = risk_category_dict.get(price_category_id)
                                                    if product_risk_category:
                                                        print(f"product_risk_category: {product_risk_category}")
                                                        percentage = product_risk_category.percentage or 0
                                                        product_total = product_price * quantity
                                                        contribution = product_total * percentage
                                                        minimum_contribution += contribution
                                            except (ValueError, TypeError):
                                                pass
                            elif latest_stage in ['Assessment', 'New']:
                                minimum_contribution = 0
                            elif latest_stage == 'Denied by client':
                                minimum_contribution = 0
                            
                            logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest stage: {latest_stage}")
                            
                            # If "New" or "Assessment", return that status (don't create new application)
                            if latest_stage in ['New', 'Assessment']:
                                logger.info(f"[CalculatePaymentScheduleView Mode 1] Status is '{latest_stage}' - NOT creating new application")
                                # application_status is already set above
                            
                            # If "Accepted", check if products match
                            elif latest_stage == 'Accepted':
                                logger.info(f"[CalculatePaymentScheduleView Mode 1] Status is 'Accepted' - checking products")
                                
                                # Compare products from application with request products
                                products_match = compare_application_products_with_request(latest_app, product_list)
                                
                                logger.info(f"[CalculatePaymentScheduleView Mode 1] Products match: {products_match}")
                                
                                if products_match:
                                    # Products match - return "Accepted" status
                                    logger.info(f"[CalculatePaymentScheduleView Mode 1] Products match - NOT creating new application")
                                    # application_status is already set to 'Accepted' above
                                else:
                                    # Products don't match - create new application
                                    logger.info(f"[CalculatePaymentScheduleView Mode 1] Products don't match - creating new application")
                                    
                                    # Get grist_product_ids from request
                                    grist_product_ids = get_grist_product_ids_from_request(product_list)
                                    logger.info(f"[CalculatePaymentScheduleView Mode 1] Grist product IDs: {grist_product_ids}")
                                    
                                    # Convert grist_product_ids to product_ids from Price table
                                    from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                    product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                    logger.info(f"[CalculatePaymentScheduleView Mode 1] Product IDs for application: {product_ids_for_application}")
                                    
                                    # Get risk_category_id from applications (try latest first, then search all)
                                    risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                    logger.info(f"[CalculatePaymentScheduleView Mode 1] Risk category ID: {risk_category_id}")
                                    
                                    # Create application in grist
                                    try:
                                        current_date_str = datetime.now().strftime("%Y-%m-%d")
                                        
                                        logger.info(f"[CalculatePaymentScheduleView Mode 1] Creating application in Grist: counterparty_id={counterparty_id}, date={current_date_str}, stage=New, risk_category_id={risk_category_id}, issue_limit={total_down_payment}, products={product_ids_for_application}")
                                        
                                        result = post_to_grist_application(
                                            counterparty_id=counterparty_id,
                                            date=current_date_str,
                                            stage='New',
                                            risk_category_id=risk_category_id,
                                            issue_limit=float(total_down_payment),
                                            products=product_ids_for_application
                                        )
                                        
                                        logger.info(f"[CalculatePaymentScheduleView Mode 1] Grist application result: {result}")
                                        
                                        if result:
                                            # IMPORTANT: After creating new application, return "New" status
                                            application_status = 'New'
                                            minimum_contribution = 0  # Reset for new application
                                            logger.info(f"[CalculatePaymentScheduleView Mode 1] Application created successfully, status set to: {application_status}")
                                        else:
                                            logger.warning(f"[CalculatePaymentScheduleView Mode 1] Application creation returned False/None")
                                    except Exception as e:
                                        logger.error(f"[CalculatePaymentScheduleView Mode 1] Error creating application: {str(e)}, Type: {type(e).__name__}", exc_info=True)
                            
                            # Only create new application if status is "Success"
                            elif latest_stage == 'Success':
                                logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest stage is 'Success' - creating new application")
                                
                                # Get grist_product_ids from request
                                grist_product_ids = get_grist_product_ids_from_request(product_list)
                                logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest app - Grist product IDs: {grist_product_ids}")
                                
                                # Convert grist_product_ids to product_ids from Price table
                                from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest app - Product IDs for application: {product_ids_for_application}")
                                
                                # Get risk_category_id from applications (try latest first, then search all)
                                risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest app - Risk category ID: {risk_category_id}")
                                
                                # Create application in grist
                                try:
                                    current_date_str = datetime.now().strftime("%Y-%m-%d")
                                    
                                    logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest app - Creating application in Grist: counterparty_id={counterparty_id}, date={current_date_str}, stage=New, risk_category_id={risk_category_id}, issue_limit={total_down_payment}, products={product_ids_for_application}")
                                    
                                    result = post_to_grist_application(
                                        counterparty_id=counterparty_id,
                                        date=current_date_str,
                                        stage='New',
                                        risk_category_id=risk_category_id,
                                        issue_limit=float(total_down_payment),
                                        products=product_ids_for_application
                                    )
                                    
                                    logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest app - Grist application result: {result}")
                                    
                                    if result:
                                        # IMPORTANT: After creating new application, return "New" status
                                        application_status = 'New'
                                        minimum_contribution = 0  # Reset for new application
                                        logger.info(f"[CalculatePaymentScheduleView Mode 1] Latest app - Application created successfully, status set to: {application_status}")
                                    else:
                                        logger.warning(f"[CalculatePaymentScheduleView Mode 1] Latest app - Application creation returned False/None")
                                except Exception as e:
                                    logger.error(f"[CalculatePaymentScheduleView Mode 1] Latest app - Error creating application: {str(e)}, Type: {type(e).__name__}", exc_info=True)
                        else:
                            # No application found at all - create new application
                            logger.info(f"[CalculatePaymentScheduleView Mode 1] No application found at all - creating new application")
                            
                            # Get grist_product_ids from request
                            grist_product_ids = get_grist_product_ids_from_request(product_list)
                            logger.info(f"[CalculatePaymentScheduleView Mode 1] No app - Grist product IDs: {grist_product_ids}")
                            
                            # Convert grist_product_ids to product_ids from Price table
                            from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                            product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                            logger.info(f"[CalculatePaymentScheduleView Mode 1] No app - Product IDs for application: {product_ids_for_application}")
                            
                            # Try to get risk_category_id from any existing applications
                            risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                            logger.info(f"[CalculatePaymentScheduleView Mode 1] No app - Risk category ID: {risk_category_id}")
                            
                            # Create application in grist
                            try:
                                current_date_str = datetime.now().strftime("%Y-%m-%d")
                                
                                logger.info(f"[CalculatePaymentScheduleView Mode 1] No app - Creating application in Grist: counterparty_id={counterparty_id}, date={current_date_str}, stage=New, risk_category_id={risk_category_id}, issue_limit={total_down_payment}, products={product_ids_for_application}")
                                
                                result = post_to_grist_application(
                                    counterparty_id=counterparty_id,
                                    date=current_date_str,
                                    stage='New',
                                    risk_category_id=risk_category_id,  # May be None if no previous applications
                                    issue_limit=float(total_down_payment),
                                    products=product_ids_for_application
                                )
                                
                                logger.info(f"[CalculatePaymentScheduleView Mode 1] No app - Grist application result: {result}")
                                
                                if result:
                                    # IMPORTANT: After creating new application, return "New" status
                                    application_status = 'New'
                                    logger.info(f"[CalculatePaymentScheduleView Mode 1] No app - Application created successfully, status set to: {application_status}")
                                else:
                                    logger.warning(f"[CalculatePaymentScheduleView Mode 1] No app - Application creation returned False/None")
                            except Exception as e:
                                logger.error(f"[CalculatePaymentScheduleView Mode 1] No app - Error creating application: {str(e)}, Type: {type(e).__name__}", exc_info=True)
                            
                            minimum_contribution = 0
                    else:
                        # No counterparty_id, can't create application
                        application_status = None
                        minimum_contribution = 0
                        logger.warning(f"[CalculatePaymentScheduleView Mode 1] No counterparty_id found for user")
                except Exception as e:
                    logger.error(f"[CalculatePaymentScheduleView Mode 1] Exception: {str(e)}, Type: {type(e).__name__}", exc_info=True)
                    minimum_contribution = 0
                    application_status = None
            
            current_date = datetime.now()
            
            if monthly_payment_amount > 0:
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
            
            # Check if user has application
            has_application = False
            counterparty_id = None
            grist_product_map = {}
            applications = []
            application_status = None
            
            if user:
                try:
                    # Use ThreadPoolExecutor for concurrent API calls
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        application_future = executor.submit(get_application)
                        grist_products_future = executor.submit(get_products_in_grist)
                        
                        application_data = application_future.result()
                        grist_products_data = grist_products_future.result()
                    
                    applications = application_data.get('records', [])
                    grist_products = grist_products_data.get('records', [])
                    
                    # Get counterparty_id
                    counterparty_id = get_user_counterparty_id(user)
                    counterparty_id_for_response = counterparty_id
                    
                    # Build grist_product_map
                    for grist_product in grist_products:
                        grist_id = grist_product.get('id')
                        price_category_id = grist_product.get('fields', {}).get('price_category_id')
                        if grist_id and price_category_id:
                            grist_product_map[grist_id] = price_category_id
                    
                    if counterparty_id:
                        # Get latest application for this counterparty_id
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
                except Exception:
                    pass
            
            # OPTIMIZATION: Barcha productlarni bir marta olish (bulk fetch)
            product_ids = [item.get('product_id') for item in product_list if item.get('product_id')]
            products = Products.objects.prefetch_related('details', 'ids').filter(id__in=product_ids)
            products_dict = {p.id: p for p in products}
            
            # OPTIMIZATION: Barcha tarifflarni bir marta olish
            tariff_ids = [item.get('tariff_id') for item in product_list if item.get('tariff_id')]
            tariffs = Tariffs.objects.filter(id__in=tariff_ids)
            tariffs_dict = {t.id: t for t in tariffs}
            
            # OPTIMIZATION: Barcha ProductIDs ni bir marta olish
            product_ids_objs_mode2 = ProductIDs.objects.filter(product_id__in=product_ids).select_related('product')
            product_ids_dict_mode2 = {}  # product_id -> [ProductIDs objects]
            variation_dict_mode2 = {}    # (product_id, variation_id) -> ProductIDs object
            
            for pid_obj in product_ids_objs_mode2:
                # Asosiy mapping
                if pid_obj.product_id not in product_ids_dict_mode2:
                    product_ids_dict_mode2[pid_obj.product_id] = []
                product_ids_dict_mode2[pid_obj.product_id].append(pid_obj)
                
                # Variation mapping
                key = (pid_obj.product_id, str(pid_obj.variation_id) if pid_obj.variation_id else None)
                variation_dict_mode2[key] = pid_obj
            
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
                
                # OPTIMIZATION: Dictionary dan olish
                product = products_dict.get(product_id)
                if not product:
                    continue
                
                # OPTIMIZATION: Dictionary dan olish
                tariff = tariffs_dict.get(item_tariff_id)
                if not tariff:
                    continue
                
                product_price = None
                
                if variation_id:
                    # OPTIMIZATION: Dictionary dan olish
                    key = (product_id, str(variation_id))
                    product_id_obj = variation_dict_mode2.get(key)
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
                    
                    date_key = payment_date.strftime("%d/%m/%y")
                    if month_num not in merged_payments:
                        merged_payments[month_num] = {
                            'date': date_key,
                            'amount': 0
                        }
                    merged_payments[month_num]['amount'] += product_monthly_payment
                    max_months = max(max_months, month_num)
                
                # Calculate minimum_contribution for this product will be done after loop
            
            monthly_payments = []
            for month_num in sorted(merged_payments.keys()):
                monthly_payments.append({
                    "number": month_num,
                    "date": merged_payments[month_num]['date'],
                    "payment": merged_payments[month_num]['amount']
                })
            
            monthly_payment_amount = merged_payments.get(1, {}).get('amount', 0) if merged_payments else 0
            
            # Handle application logic for mode 2
            if user and counterparty_id:
                try:
                    # First check for today's application
                    today_app = get_today_application_by_counterparty(applications, counterparty_id)
                    
                    if today_app:
                        # Use today's application
                        today_stage = today_app.get('fields', {}).get('stage', '')
                        application_status = today_stage
                        
                        # Calculate minimum_contribution based on status
                        if today_stage in ['Accepted', 'Denied']:
                            # Calculate minimum_contribution
                            risk_category_id = today_app.get('fields', {}).get('risk_category_id')
                            if risk_category_id:
                                # Calculate minimum_contribution for all products
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
                                                        
                                                        # Get product price
                                                        product_price = None
                                                        if variation_id:
                                                            product_id_obj_var = ProductIDs.objects.filter(
                                                                product=product, variation_id=str(variation_id)
                                                            ).first()
                                                            if product_id_obj_var:
                                                                # Find price from details
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
                        elif today_stage == 'Denied by client':
                            minimum_contribution = 0
                        elif today_stage in ['Assessment', 'New']:
                            minimum_contribution = 0
                        
                        # Create new application only if today's status is "Accepted" or "Success"
                        # AND all today's applications are "Accepted" or "Success"
                        # If status is "New" or "Assessment", don't create new one
                        # Создавать новую заявку только если статус сегодняшней заявки "Accepted" или "Success"
                        # И все сегодняшние заявки имеют статус "Accepted" или "Success"
                        # Если статус "New" или "Assessment", не создавать новую
                        if today_stage in ['Accepted', 'Success'] and are_all_today_applications_accepted(applications, counterparty_id):
                            # Get grist_product_ids from request
                            grist_product_ids = get_grist_product_ids_from_request(product_list)
                            
                            # Convert grist_product_ids to product_ids from Price table
                            from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                            product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                            
                            # Get risk_category_id from applications (try latest first, then search all)
                            risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                            current_date_str = datetime.now().strftime("%Y-%m-%d")
                            
                            # DEBUG: risk_category_id
                            print(f"\n{'='*80}")
                            print(f"[CalculatePaymentScheduleView Mode 2] DEBUG - risk_category_id:")
                            print(f"  📊 risk_category_id: {risk_category_id}")
                            print(f"  📊 risk_category_id type: {type(risk_category_id)}")
                            print(f"  📊 risk_category_id is None: {risk_category_id is None}")
                            if risk_category_id is not None:
                                print(f"  ✅ risk_category_id mavjud: {risk_category_id}")
                            else:
                                print(f"  ⚠️  risk_category_id None - Grist'ga yuborilmaydi")
                            print(f"  📋 counterparty_id: {counterparty_id}")
                            print(f"  📋 applications soni: {len(applications) if applications else 0}")
                            print(f"{'='*80}\n")
                            
                            # Calculate total_advance_payment for mode 2
                            total_advance_payment_mode2 = sum(item.get('advance_payment', 0) for item in product_list)
                            
                            try:
                                print(f"[CalculatePaymentScheduleView Mode 2] post_to_grist_application chaqirilmoqda:")
                                print(f"  📤 counterparty_id: {counterparty_id}")
                                print(f"  📤 date: {current_date_str}")
                                print(f"  📤 stage: New")
                                print(f"  📤 risk_category_id: {risk_category_id} (type: {type(risk_category_id)})")
                                print(f"  📤 issue_limit: {float(total_advance_payment_mode2)}")
                                print(f"  📤 products: {product_ids_for_application}")
                                
                                result = post_to_grist_application(
                                    counterparty_id=counterparty_id,
                                    date=current_date_str,
                                    stage='New',
                                    risk_category_id=risk_category_id,
                                    issue_limit=float(total_advance_payment_mode2),
                                    products=product_ids_for_application
                                )
                                
                                print(f"[CalculatePaymentScheduleView Mode 2] post_to_grist_application natijasi:")
                                print(f"  📥 result: {result}")
                                print(f"  📥 result type: {type(result)}")
                                
                                if result:
                                    # IMPORTANT: After creating new application, return "New" status
                                    application_status = 'New'
                            except Exception as e:
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.error(f"Error creating application (mode 2): {str(e)}")
                    else:
                        # No application for today, check latest application to get risk_category_id
                        latest_app = get_latest_application_by_counterparty(applications, counterparty_id)
                        
                        if latest_app:
                            latest_stage = latest_app.get('fields', {}).get('stage', '')
                            application_status = latest_stage
                            
                            # Only create new application if latest stage is "Accepted" or "Success"
                            should_create_application = latest_stage in ['Accepted', 'Success']
                            
                            # Calculate minimum_contribution based on status
                            if latest_stage in ['Accepted', 'Denied']:
                                # Get risk_category_id from applications
                                risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                            
                            if risk_category_id:
                                # OPTIMIZATION: Barcha kerakli price_category_id larni yig'ish
                                price_category_ids = set()
                                product_data_list = []
                                
                                for item in product_list:
                                    product_id = item.get('product_id')
                                    quantity = item.get('quantity', 1)
                                    variation_id = item.get('variation_id')
                                    
                                    # Dictionary dan olish (yuqorida yaratilgan)
                                    product = products_dict.get(product_id)
                                    if not product:
                                        continue
                                    
                                    # Dictionary dan olish
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
                                
                                # OPTIMIZATION: Barcha ProductRiskCategory ni bir marta olish
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
                                
                                # OPTIMIZATION: Loop ichida dictionary dan olish
                                for prod_data in product_data_list:
                                    product = prod_data['product']
                                    quantity = prod_data['quantity']
                                    variation_id = prod_data['variation_id']
                                    price_category_id = prod_data['price_category_id']
                                    
                                    # Dictionary dan olish
                                    product_risk_category = risk_category_dict_mode2.get(str(price_category_id))
                                    if product_risk_category:
                                        percentage = product_risk_category.percentage or 0
                                        
                                        # Get product price (yuqorida hisoblangan)
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
                            elif latest_stage == 'Denied by client':
                                minimum_contribution = 0
                            elif latest_stage in ['Assessment', 'New']:
                                minimum_contribution = 0
                            
                            # Create new application only if latest stage is Accepted or Success
                            if should_create_application:
                                try:
                                    # Get grist_product_ids from request (these are Price table record ids)
                                    grist_product_ids = get_grist_product_ids_from_request(product_list)
                                    
                                    # Convert grist_product_ids to product_ids from Price table
                                    from apps.v1.order.integrations.advanced_payment_assessment import get_product_ids_from_price_table_by_grist_ids
                                    product_ids_for_application = get_product_ids_from_price_table_by_grist_ids(grist_product_ids)
                                    
                                    # Get risk_category_id from applications (try latest first, then search all)
                                    risk_category_id = get_risk_category_id_from_applications(applications, counterparty_id)
                                    current_date_str = datetime.now().strftime("%Y-%m-%d")
                                    
                                    # DEBUG: risk_category_id
                                    print(f"\n{'='*80}")
                                    print(f"[CalculatePaymentScheduleView Mode 2 - Latest App] DEBUG - risk_category_id:")
                                    print(f"  📊 risk_category_id: {risk_category_id}")
                                    print(f"  📊 risk_category_id type: {type(risk_category_id)}")
                                    print(f"  📊 risk_category_id is None: {risk_category_id is None}")
                                    if risk_category_id is not None:
                                        print(f"  ✅ risk_category_id mavjud: {risk_category_id}")
                                    else:
                                        print(f"  ⚠️  risk_category_id None - Grist'ga yuborilmaydi")
                                    print(f"  📋 counterparty_id: {counterparty_id}")
                                    print(f"  📋 applications soni: {len(applications) if applications else 0}")
                                    print(f"{'='*80}\n")
                                    
                                    # Calculate total_advance_payment for mode 2
                                    total_advance_payment_mode2 = sum(item.get('advance_payment', 0) for item in product_list)
                                    
                                    print(f"[CalculatePaymentScheduleView Mode 2 - Latest App] post_to_grist_application chaqirilmoqda:")
                                    print(f"  📤 counterparty_id: {counterparty_id}")
                                    print(f"  📤 date: {current_date_str}")
                                    print(f"  📤 stage: New")
                                    print(f"  📤 risk_category_id: {risk_category_id} (type: {type(risk_category_id)})")
                                    print(f"  📤 issue_limit: {float(total_advance_payment_mode2)}")
                                    print(f"  📤 products: {product_ids_for_application}")
                                    
                                    result = post_to_grist_application(
                                        counterparty_id=counterparty_id,
                                        date=current_date_str,
                                        stage='New',
                                        risk_category_id=risk_category_id,
                                        issue_limit=float(total_advance_payment_mode2),
                                        products=product_ids_for_application
                                    )
                                    
                                    print(f"[CalculatePaymentScheduleView Mode 2 - Latest App] post_to_grist_application natijasi:")
                                    print(f"  📥 result: {result}")
                                    print(f"  📥 result type: {type(result)}")
                                    
                                    if result:
                                        # IMPORTANT: After creating new application, return "New" status
                                        application_status = 'New'
                                except Exception as e:
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.error(f"Error creating application (mode 2): {str(e)}")
                        else:
                            # No application found, don't create (only create if latest is Accepted or Success)
                            application_status = None
                            minimum_contribution = 0
                except Exception:
                    application_status = None
                    minimum_contribution = 0
        
        # ability_to_order logic: Only True if status is "Accepted"
        if application_status == 'Accepted':
            # Check if total_down_payment meets minimum_contribution requirement
            if calculation_mode == 1:
                ability_to_order = float(total_down_payment) >= minimum_contribution if minimum_contribution > 0 else True
            elif calculation_mode == 2:
                ability_to_order = float(total_down_payment) >= minimum_contribution if minimum_contribution > 0 else True
            else:
                ability_to_order = True
        else:
            # For all other statuses (New, Assessment, Denied, Denied by client, None, etc.), ability_to_order is False
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
            "status": application_status,
            "counterparty_id": counterparty_id_for_response,
            "monthly_payments": monthly_payments,
            "product_list": response_product_list
        }
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[CalculatePaymentScheduleView] Final response - status: {application_status}, counterparty_id: {counterparty_id_for_response}, ability_to_order: {ability_to_order}, calculation_mode: {calculation_mode}")
        
        return Response(response_data, status=status.HTTP_200_OK)
