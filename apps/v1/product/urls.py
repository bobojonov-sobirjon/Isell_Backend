from django.urls import path
from apps.v1.product.views import (
    CategoriesListView,
    ProductListView,
    ProductDetailView,
    CalculateMonthlyPaymentView,
    CalculatePaymentScheduleView
)
from apps.v1.order.views import TariffsListView

urlpatterns = [
    # Список категорий (только с продуктами)
    path('categories/', CategoriesListView.as_view(), name='product-categories'),
    
    # Список всех продуктов
    path('', ProductListView.as_view(), name='product-list'),
    
    # Детальная информация о продукте
    path('<int:product_id>/', ProductDetailView.as_view(), name='product-detail'),
    
    # Расчет ежемесячного платежа
    path('<int:product_id>/calculate/', CalculateMonthlyPaymentView.as_view(), name='calculate-monthly-payment'),
    
    # Расчет графика платежей
    path('calculate-schedule/', CalculatePaymentScheduleView.as_view(), name='calculate-payment-schedule'),
    
    # Список тарифов
    path('tariffs/', TariffsListView.as_view(), name='tariffs_list'),
]

