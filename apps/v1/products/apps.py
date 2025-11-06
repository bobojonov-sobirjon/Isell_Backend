from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.v1.products'
    label = 'products'
    verbose_name = 'Продукты'
