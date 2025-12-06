from django.urls import path
from apps.v1.product.views import (
    CategoriesListView,
    ProductListView,
    ProductDetailView,
    CalculateMonthlyPaymentView,
    CalculatePaymentScheduleView,
    CalculatePaymentScheduleSimpleView
)
from apps.v1.order.views import TariffsListView

urlpatterns = [
    path('categories/', CategoriesListView.as_view(), name='product-categories'),
    
    path('', ProductListView.as_view(), name='product-list'),
    
    path('<int:product_id>/', ProductDetailView.as_view(), name='product-detail'),
    
    path('<int:product_id>/calculate/', CalculateMonthlyPaymentView.as_view(), name='calculate-monthly-payment'),
    
    path('calculate-schedule/', CalculatePaymentScheduleView.as_view(), name='calculate-payment-schedule'),
    
    path('calculate-schedule-simple/', CalculatePaymentScheduleSimpleView.as_view(), name='calculate-payment-schedule-simple'),
    
    path('tariffs/', TariffsListView.as_view(), name='tariffs_list'),
]

