from django.urls import path
from apps.v1.order.views import (
    ImportTariffsView, 
    TariffsListView, 
    CreateOrderView, 
    CompanyAddressListView,
    UpdateOrderAddressView
)


urlpatterns = [
    path('import-tariffs/', ImportTariffsView.as_view(), name='import_tariffs'),
    path('tariffs/', TariffsListView.as_view(), name='tariffs_list'),
    path('create/', CreateOrderView.as_view(), name='create_order'),
    path('company-addresses/', CompanyAddressListView.as_view(), name='company_addresses'),
    path('update-address/', UpdateOrderAddressView.as_view(), name='update_order_address'),
]