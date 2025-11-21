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
    get_application, get_products_in_grist, get_counterparties_in_grist
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

def get_user_counterparty_id(user):
    """
    Get counterparty_id from Grist based on user's pnfl and date_of_birth
    """

    if not user or not user.pnfl or not user.date_of_birth:

        return None
    
    try:

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

                except (ValueError, TypeError):
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
                    
                    # Check if user has any application
                    has_application, counterparty_id = check_user_has_application(user, applications)
                    
                    if has_application:
                        grist_product_map = {}
                        for grist_product in grist_products:
                            grist_id = grist_product.get('id')
                            price_category_id = grist_product.get('fields', {}).get('price_category_id')
                            if grist_id and price_category_id:
                                grist_product_map[grist_id] = price_category_id
                        
                        # Calculate minimum_contribution using the new helper function
                        minimum_contribution = calculate_minimum_contribution_for_products(
                            user, products_data, grist_product_map, applications, counterparty_id
                        )
                    # If user doesn't have application, minimum_contribution stays 0
                except Exception as e:
                    minimum_contribution = 0
                    has_application = False
            
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
            
            # Check if user has application
            has_application = False
            counterparty_id = None
            grist_product_map = {}
            applications = []
            
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
                    
                    # Check if user has any application
                    has_application, counterparty_id = check_user_has_application(user, applications)
                    
                    if has_application:
                        for grist_product in grist_products:
                            grist_id = grist_product.get('id')
                            price_category_id = grist_product.get('fields', {}).get('price_category_id')
                            if grist_id and price_category_id:
                                grist_product_map[grist_id] = price_category_id
                except:
                    pass
            
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
                
                # Calculate minimum_contribution for this product
                # Only calculate if user has application

                if has_application and counterparty_id:
                    try:
                        # Filter applications by counterparty_id and check for Accepted stage
                        approved_applications = []
                        for app in applications:
                            app_counterparty_id = app.get('fields', {}).get('counterparty_id')
                            app_stage = app.get('fields', {}).get('stage', '')
                            # Only accept "Accepted" stage
                            if app_counterparty_id == counterparty_id and app_stage == 'Accepted':
                                approved_applications.append(app)

                        if approved_applications:
                            # Get risk_category_id from approved applications
                            risk_category_id = None
                            product_id_obj = ProductIDs.objects.filter(product=product).first()
                            grist_product_id = product_id_obj.grist_product_id if product_id_obj and product_id_obj.grist_product_id else None
                            
                            # First, try to find matching product in app_products
                            product_found = False
                            if grist_product_id:
                                try:
                                    grist_product_id = int(grist_product_id)
                                except (ValueError, TypeError):
                                    pass
                                
                                if grist_product_id:
                                    for app in approved_applications:
                                        app_products = app.get('fields', {}).get('products', [])
                                        if grist_product_id in app_products:
                                            risk_category_id = app.get('fields', {}).get('risk_category_id')
                                            product_found = True
                                            break
                            
                            # If no product match found but application exists, use its risk_category_id anyway
                            if not product_found and approved_applications:
                                risk_category_id = approved_applications[0].get('fields', {}).get('risk_category_id')

                            if risk_category_id:
                                if grist_product_id and grist_product_id in grist_product_map:
                                    price_category_id = grist_product_map[grist_product_id]
                                    
                                    if price_category_id:
                                        try:

                                            product_risk_category = ProductRiskCategory.objects.get(
                                                grist_risk_category_id=str(risk_category_id),
                                                grist_price_category_id=str(price_category_id)
                                            )
                                            percentage = product_risk_category.percentage or 0
                                            contribution = product_total * percentage
                                            minimum_contribution += contribution

                                        except ProductRiskCategory.DoesNotExist:

                                            pass
                                else:
                                    pass
                    except Exception:
                        pass
                else:
                    pass
            
            monthly_payments = []
            for month_num in sorted(merged_payments.keys()):
                monthly_payments.append({
                    "number": month_num,
                    "date": merged_payments[month_num]['date'],
                    "payment": merged_payments[month_num]['amount']
                })
            
            monthly_payment_amount = merged_payments.get(1, {}).get('amount', 0) if merged_payments else 0
        
        # ability_to_order logic:
        # - If user doesn't have application: minimum_contribution = 0, ability_to_order = True
        # - If user has application: ability_to_order = total_down_payment >= minimum_contribution
        if has_application:
            ability_to_order = float(total_down_payment) >= minimum_contribution
        else:
            ability_to_order = True
        
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
