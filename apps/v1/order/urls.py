from django.urls import path
from apps.v1.order.views import (
    ImportTariffsView, 
    TariffsListView, 
    CreateOrderView, 
    CompanyAddressListView,
    UpdateOrderAddressView,
    MySalesView,
    MyOrdersView,
    MyOrderDetailView
)


urlpatterns = [
    path('create/', CreateOrderView.as_view(), name='create_order'),
    path('update-address/', UpdateOrderAddressView.as_view(), name='update_order_address'),
    path('my-orders/', MyOrdersView.as_view(), name='my_orders'),
    path('my-orders/<int:order_id>/', MyOrderDetailView.as_view(), name='my_order_detail'),
]