from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


from apps.v1.products.models import Categories
from apps.v1.products.serializers import CategoriesSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import AllowAny


class CategoryListView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        tags=['Категории'],
        operation_summary="Список категорий",
        operation_description="Список категорий",
        responses={
            200: openapi.Response(
                description="Список категорий", 
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY, 
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT, 
                        properties={
                            "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID категории"),
                            "name": openapi.Schema(type=openapi.TYPE_STRING, description="Название категории"),
                            "description": openapi.Schema(type=openapi.TYPE_STRING, description="Описание категории"),
                        }
                    )
                )
            )
        }
    )
    def get(self, request):
        categories = Categories.objects.all()
        serializer = CategoriesSerializer(categories, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
