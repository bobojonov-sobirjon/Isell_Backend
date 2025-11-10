from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from apps.v1.products.models import Banner
from apps.v1.products.serializers import BannerSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


class BannerListView(APIView):
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        tags=['Баннеры'],
        operation_summary="Список баннеров",
        operation_description="Список баннеров",
        responses={
            200: openapi.Response(
                description="Список баннеров",
                    schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID баннера"),
                            "name": openapi.Schema(type=openapi.TYPE_STRING, description="Название баннера"),
                            "description": openapi.Schema(type=openapi.TYPE_STRING, description="Описание баннера"),
                            "link": openapi.Schema(type=openapi.TYPE_STRING, description="Ссылка на баннер"),   
                            "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Активный"),
                            "order": openapi.Schema(type=openapi.TYPE_INTEGER, description="Порядок"),
                        }
                    )
                )
            ),
        }
    )
    def get(self, request):
        try:
            banners = Banner.objects.filter(is_active=True).order_by('order')
            serializer = BannerSerializer(banners, many=True, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)