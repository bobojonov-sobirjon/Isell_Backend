from django.apps import AppConfig


class OrderConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.v1.order'
    label = 'order'
    verbose_name = 'Заказы'