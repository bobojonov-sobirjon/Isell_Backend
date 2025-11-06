from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.v1.products.integrations.product_lists import get_products, import_product_details, import_product_properties, import_product_characteristics, import_product_images
from apps.v1.products.integrations.category_list import get_categories
from apps.v1.order.integrations.advanced_payment_assessment import get_advanced_payment_assessment
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import AllowAny


class ImportCategoriesView(APIView):
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        tags=['Импорт'],
        operation_description="Импорт категорий",
        responses={200: openapi.Response(description="Категории импортированы успешно", schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
            "message": openapi.Schema(type=openapi.TYPE_STRING, description="Сообщение о результате импорта")
        }))}
    )
    def get(self, request):
        categories = get_categories()
        return Response({"message": "Категории импортированы успешно"}, status=status.HTTP_200_OK)


class ImportProductsView(APIView):
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        tags=['Импорт'],
        operation_description="Импорт продуктов и деталей",
        responses={200: openapi.Response(description="Продукты и детали импортированы успешно", schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
            "message": openapi.Schema(type=openapi.TYPE_STRING, description="Сообщение о результате импорта")
        }))}
    )
    def get(self, request):
        products = get_products()
        details = import_product_details()
        
        return Response({
            "message": "Продукты и детали импортированы успешно",
            "products": products,
            "details": details
        }, status=status.HTTP_200_OK)


class ImportCharacteristicsView(APIView):
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        tags=['Импорт'],
        operation_description="Импорт характеристик продуктов",
        responses={200: openapi.Response(description="Характеристики импортированы успешно", schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
            "message": openapi.Schema(type=openapi.TYPE_STRING, description="Сообщение о результате импорта")
        }))}
    )
    def get(self, request):
        # Avval properties import qilamiz
        properties = import_product_properties()
        
        # Keyin characteristics import qilamiz
        characteristics = import_product_characteristics()
        
        return Response({
            "message": "Свойства и характеристики импортированы успешно",
            "properties": properties,
            "characteristics": characteristics
        }, status=status.HTTP_200_OK)


class ImportAdvancedPaymentAssessmentView(APIView):
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        tags=['Импорт'],
        operation_description="Импорт категорий продуктов с advanced payment assessment",
        responses={200: openapi.Response(description="Advanced payment assessment импортирован успешно", schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
            "message": openapi.Schema(type=openapi.TYPE_STRING, description="Сообщение о результате импорта"),
            "created": openapi.Schema(type=openapi.TYPE_INTEGER, description="Количество созданных записей"),
            "updated": openapi.Schema(type=openapi.TYPE_INTEGER, description="Количество обновленных записей"),
            "skipped": openapi.Schema(type=openapi.TYPE_INTEGER, description="Количество пропущенных записей")
        }))}
    )
    def get(self, request):
        result = get_advanced_payment_assessment()
        
        if result.get("success"):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)


class ImportProductImagesView(APIView):
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        tags=['Импорт'],
        operation_description="Импорт изображений продуктов из Grist",
        responses={200: openapi.Response(description="Изображения импортированы успешно", schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
            "message": openapi.Schema(type=openapi.TYPE_STRING, description="Сообщение о результате импорта"),
            "created": openapi.Schema(type=openapi.TYPE_INTEGER, description="Количество созданных изображений"),
            "skipped": openapi.Schema(type=openapi.TYPE_INTEGER, description="Количество пропущенных изображений"),
            "total_downloaded": openapi.Schema(type=openapi.TYPE_INTEGER, description="Общее количество загруженных файлов"),
            "total_products": openapi.Schema(type=openapi.TYPE_INTEGER, description="Количество продуктов с изображениями")
        }))}
    )
    def get(self, request):
        result = import_product_images()
        
        if result.get("success"):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        