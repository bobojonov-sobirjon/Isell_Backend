from django.contrib import admin
from django.utils.html import format_html
from django.conf import settings

from apps.v1.product.models import (
    Products, ProductDetails, ProductIDs,
    ProductProperties, ProductCharacteristics, Categories, ProductImages,
    ProductRiskCategory, ProductAutomaticallyImportedTime, Banner
    
)


@admin.register(Categories)
class CategoriesAdmin(admin.ModelAdmin):
    list_display = ('name', 'id')
    search_fields = ('name',)
    
class ProductImagesInline(admin.TabularInline):
    model = ProductImages
    extra = 0
    fk_name = 'product_details'
    verbose_name = 'Изображение продукта'
    verbose_name_plural = 'Изображения продукта'
    fields = ('image_preview', 'image')
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 100px; max-width: 100px;" />', obj.image.url)
        return '-'
    image_preview.short_description = 'Превью'


class ProductDetailsInline(admin.TabularInline):
    model = ProductDetails
    extra = 1
    fk_name = 'product'
    verbose_name = 'Детали продукта'
    verbose_name_plural = 'Детали продукта'
    fields = ('id', 'color', 'storage', 'sim', 'battery_capacity', 'price', 'images')
    search_fields = ('id', 'color', 'storage', 'sim')
    readonly_fields = ('id', 'color', 'storage', 'sim', 'battery_capacity', 'price', 'images')
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Store request for use in images method
        self.request = request
        return formset
    
    def images(self, obj):
        first_image = obj.images.first()
        if first_image and first_image.image:
            image_url = first_image.image.url
            # Build absolute URL with base URL
            if not image_url.startswith('http'):
                request = getattr(self, 'request', None)
                if request:
                    base_url = request.build_absolute_uri('/').rstrip('/')
                    image_url = f"{base_url}{image_url}"
            return format_html('<img src="{}" style="max-height: 50px; max-width: 50px;" />', image_url)
        return '-'
    images.short_description = 'Изображения'
    

class ProductCharacteristicsInline(admin.TabularInline):
    model = ProductCharacteristics
    extra = 1
    fk_name = 'product'
    verbose_name = 'Характеристики продукта'
    verbose_name_plural = 'Характеристики продукта'
    fields = ['property', 'value_name']
    autocomplete_fields = ['property']


class ProductIDsInline(admin.TabularInline):
    model = ProductIDs
    extra = 1
    fk_name = 'product'
    verbose_name = 'Вариации продукта'
    verbose_name_plural = 'Вариации продукта'
    fields = ('variation_name', 'variation_id', 'grist_product_id')


@admin.register(Products)
class ProductsAdmin(admin.ModelAdmin):
    list_display = ('get_first_image', 'name', 'get_variation_names', 'category', 'price', 'actual')
    search_fields = ('name', 'category__name')
    inlines = [ProductIDsInline, ProductDetailsInline, ProductCharacteristicsInline]
    
    def get_first_image(self, obj):
        """Display first image of the product"""
        if obj.image:
            return format_html('<img src="{}" style="max-height: 50px; max-width: 50px;" />', obj.image.url)
        # Try to get image from product details
        first_detail = obj.details.first()
        if first_detail:
            first_image = first_detail.images.first()
            if first_image and first_image.image:
                return format_html('<img src="{}" style="max-height: 50px; max-width: 50px;" />', first_image.image.url)
        return '-'
    get_first_image.short_description = 'Изображение'
    
    def get_variation_names(self, obj):
        """Display all variation names for this product"""
        variations = obj.ids.all()
        if variations:
            return ', '.join([v.variation_name for v in variations if v.variation_name])
        return '-'
    get_variation_names.short_description = 'Variation Names'
    
    
@admin.register(ProductDetails)
class ProductDetailsAdmin(admin.ModelAdmin):
    list_display = ('product', 'color', 'storage', 'sim', 'price')
    search_fields = ('product__name', 'storage', 'sim', 'color')
    inlines = [ProductImagesInline]

@admin.register(ProductProperties)
class ProductPropertiesAdmin(admin.ModelAdmin):
    list_display = ('property_name', 'property_type', 'grist_property_id')
    search_fields = ['property_name', 'property_type', 'grist_property_id']

@admin.register(ProductCharacteristics)
class ProductCharacteristicsAdmin(admin.ModelAdmin):
    list_display = ('product', 'get_property_name', 'value_name', 'product_ids')
    search_fields = ('product__name', 'property__property_name', 'value_name')
    list_filter = ('product', 'property')
    
    def get_property_name(self, obj):
        return obj.property.property_name if obj.property else '-'
    get_property_name.short_description = 'Property Name'


@admin.register(ProductRiskCategory)
class ProductRiskCategoryAdmin(admin.ModelAdmin):
    list_display = ('risk_category', 'name', 'percentage', 'grist_product_category_id', 'grist_risk_category_id', 'grist_price_category_id')
    search_fields = ('name', 'risk_category', 'percentage', 'grist_product_category_id', 'grist_risk_category_id', 'grist_price_category_id')
    list_filter = ('risk_category', 'percentage')
    ordering = ["created_at"]


@admin.register(ProductIDs)
class ProductIDsAdmin(admin.ModelAdmin):
    list_display = ('product', 'variation_name', 'variation_id')
    search_fields = ('product__name', 'variation_name', 'variation_id')
    list_filter = ('product',)
    

@admin.register(ProductAutomaticallyImportedTime)
class ProductAutomaticallyImportedTimeAdmin(admin.ModelAdmin):
    list_display = ('time', 'time_type', 'is_active', 'created_at', 'updated_at')
    search_fields = ('time',)
    list_filter = ('time_type', 'is_active', 'created_at')
    ordering = ["created_at"]
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        try:
            from django_celery_beat.models import PeriodicTask, IntervalSchedule
            from apps.v1.product.tasks import import_products_task
            import logging
            
            logger = logging.getLogger(__name__)
            
            try:
                task_name = 'Автоматический импорт продуктов'
                
                PeriodicTask.objects.filter(name=task_name).delete()
                
                if obj.is_active and obj.time:
                    interval_minutes = obj.get_interval_minutes()
                    
                    schedule, created = IntervalSchedule.objects.get_or_create(
                        every=interval_minutes,
                        period=IntervalSchedule.MINUTES,
                    )
                    
                    PeriodicTask.objects.create(
                        interval=schedule,
                        name=task_name,
                        task='apps.v1.product.tasks.import_products_task',
                        enabled=True,
                    )
                    
                    time_type_str = 'минут' if obj.time_type == 'minutes' else 'часов'
                    logger.info(f'Автоматический импорт продуктов обновлен: каждые {obj.time} {time_type_str} ({interval_minutes} минут)')
                else:
                    logger.info('Автоматический импорт остановлен')
            except Exception as e:
                logger.error(f'Ошибка при обновлении расписания: {str(e)}', exc_info=True)
        except ImportError:
            pass
    
    
@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    def get_image(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 50px; max-width: 50px;" />', obj.image.url)
        return '-'
    get_image.short_description = 'Изображение'
    
    list_display = ('get_image', 'name', 'description', 'link', 'is_active', 'order')
    search_fields = ('name', 'description', 'link')
    list_filter = ('is_active', 'order')
    ordering = ["created_at"]