from django.urls import path
from apps.v1.products.views.import_views import ImportProductsView, ImportCategoriesView, ImportCharacteristicsView, ImportAdvancedPaymentAssessmentView, ImportProductImagesView
from apps.v1.products.views.category_views import CategoryListView
from apps.v1.products.views.product_views import ProductListView, ProductDetailView, ProductDetailFilterView, CalculateMonthlyPaymentView, CalculatePaymentScheduleView


urlpatterns = [
    
    # Импорт категорий
    path('import-categories/', ImportCategoriesView.as_view(), name='import-categories'),
    
    # Импорт Продукты
    path('import-products/', ImportProductsView.as_view(), name='import-products'),
    
    # Импорт характеристик
    path('import-characteristics/', ImportCharacteristicsView.as_view(), name='import-characteristics'),
    
    # Импорт advanced payment assessment
    path('import-advanced-payment/', ImportAdvancedPaymentAssessmentView.as_view(), name='import-advanced-payment'),
    
    # Импорт изображений продуктов
    path('import-images/', ImportProductImagesView.as_view(), name='import-images'),
    
    # Список категорий
    path('categories/', CategoryListView.as_view(), name='categories'),
    
    # Список продуктов
    path('', ProductListView.as_view(), name='products'),
    
    # Детальная информация о продукте
    path('<int:product_id>/', ProductDetailView.as_view(), name='product-detail'),
    
    # Фильтрованные детали продукта (Cascading Filter)
    path('<int:product_id>/filter/', ProductDetailFilterView.as_view(), name='product-detail-filter'),
    
    # Расчет ежемесячного платежа
    path('<int:product_id>/calculate/', CalculateMonthlyPaymentView.as_view(), name='calculate-monthly-payment'),
    
    # Расчет графика платежей
    path('calculate-schedule/', CalculatePaymentScheduleView.as_view(), name='calculate-payment-schedule'),
]