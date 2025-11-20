from django.apps import AppConfig


class ProductConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.v1.product'
    label = 'product'
    verbose_name = 'Продукты v1'
