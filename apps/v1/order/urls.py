from django.urls import path
from apps.v1.order.views import (
    ImportTariffsView, 
    TariffsListView, 
    CreateOrderView, 
    CompanyAddressListView,
    UpdateOrderAddressView,
    MyOrdersView
)


urlpatterns = [
    path('import-tariffs/', ImportTariffsView.as_view(), name='import_tariffs'),
    path('create/', CreateOrderView.as_view(), name='create_order'),
    path('update-address/', UpdateOrderAddressView.as_view(), name='update_order_address'),
    path('my-orders/', MyOrdersView.as_view(), name='my_orders'),
]