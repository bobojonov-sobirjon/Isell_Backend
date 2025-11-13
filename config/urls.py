from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve
from django.conf import settings
from django.conf.urls.static import static

from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from drf_yasg import generators

from rest_framework import permissions
from config.libraries.swagger_auth import SwaggerTokenView

from apps.v1.products.views.banner_views import BannerListView
from apps.v1.order.views import CompanyAddressListView


class CustomOpenAPISchemaGenerator(generators.OpenAPISchemaGenerator):
    """Custom schema generator that adds security definitions"""
    
    def get_security_definitions(self):
        """Add Bearer token security definitions"""
        return {
            'Bearer': {
                'type': 'apiKey',
                'name': 'Authorization',
                'in': 'header',
                'description': 'JWT Bearer token. Token olish uchun login endpoint\'dan foydalaning: /api/v1/accounts/login/'
            },
        }


schema_view = get_schema_view(
    openapi.Info(
        title="ISell Ecommerce APIs",
        default_version='v1',
        description="""
        ISell Ecommerce APIs - Система управления для ISell Ecommerce API
        """,
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@snippets.local"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
    authentication_classes=[],
    generator_class=CustomOpenAPISchemaGenerator,
)

urlpatterns = [
    path('admin/', admin.site.urls),
]

urlpatterns += [
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

# Swagger OAuth2 token endpoint
urlpatterns += [
    path('api/v1/swagger/token/', SwaggerTokenView.as_view(), name='swagger-token'),
]

urlpatterns += [
    path('api/v1/products/', include('apps.v1.products.urls')),
    path('api/v1/accounts/', include('apps.v1.accounts.urls')),
    path('api/v1/order/', include('apps.v1.order.urls')),
]

urlpatterns += [
    path('api/v1/info/banners/', BannerListView.as_view(), name='banners'),
    path('api/v1/info/company-addresses/', CompanyAddressListView.as_view(), name='company_addresses'),
    
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT, }, ), ]