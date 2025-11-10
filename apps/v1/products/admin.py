from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Categories, Products,
    ProductDetails, ProductIDs, 
    ProductProperties, ProductCharacteristics, ProductCategory, ProductImages, Banner
)


@admin.register(Categories)
class CategoriesAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')
    
class ProductIDsAdmin(admin.TabularInline):
    model = ProductIDs
    extra = 1
    fk_name = 'product'
    verbose_name = 'Вариация продукта'
    verbose_name_plural = 'Вариации продукта'
    fields = ('variation_name', 'variation_id')
    search_fields = ('variation_name', 'variation_id')
    readonly_fields = ('variation_name', 'variation_id')


class ProductDetailsAdmin(admin.TabularInline):
    model = ProductDetails
    extra = 1
    fk_name = 'product'
    verbose_name = 'Детали продукта'
    verbose_name_plural = 'Детали продукта'
    fields = ('id', 'color', 'storage', 'sim_card')
    search_fields = ('id', 'color', 'storage', 'sim_card')
    readonly_fields = ('id', 'color', 'storage', 'sim_card')


class ProductImagesInline(admin.TabularInline):
    model = ProductImages
    extra = 0
    fk_name = 'product'
    verbose_name = 'Изображение продукта'
    verbose_name_plural = 'Изображения продукта'
    fields = ('image_preview', 'image')
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 100px; max-width: 100px;" />', obj.image.url)
        return '-'
    image_preview.short_description = 'Превью'


class ProductCharacteristicsInline(admin.TabularInline):
    model = ProductCharacteristics
    extra = 1
    fk_name = 'product'
    verbose_name = 'Характеристики продукта'
    verbose_name_plural = 'Характеристики продукта'
    fields = ['property', 'value']
    autocomplete_fields = ['property']


@admin.register(Products)
class ProductsAdmin(admin.ModelAdmin):
    list_display = ('get_first_image', 'name', 'get_variation_names', 'category',  'price', 'battery_capacity', 'processor', 'screen_name')
    search_fields = ('name', 'category__name', 'battery_capacity', 'processor', 'screen_name')
    inlines = [ProductImagesInline, ProductIDsAdmin, ProductDetailsAdmin, ProductCharacteristicsInline]
    
    def get_first_image(self, obj):
        """Display first image of the product"""
        first_image = obj.images.first()
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
    list_display = ('product', 'storage', 'sim_card')
    search_fields = ('product__name', 'storage', 'sim_card')

@admin.register(ProductProperties)
class ProductPropertiesAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'grist_property_id')
    search_fields = ['name', 'type', 'grist_property_id']

@admin.register(ProductCharacteristics)
class ProductCharacteristicsAdmin(admin.ModelAdmin):
    list_display = ('product', 'get_property_name', 'value')
    search_fields = ('product__name', 'property__name', 'value')
    list_filter = ('product', 'property')
    
    def get_property_name(self, obj):
        return obj.property.name if obj.property else '-'
    get_property_name.short_description = 'Property Name'


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('risk_category', 'name', 'percentage', 'grist_product_category_id', 'grist_risk_category_id', 'grist_price_category_id')
    search_fields = ('name', 'risk_category', 'percentage', 'grist_product_category_id', 'grist_risk_category_id', 'grist_price_category_id')
    list_filter = ('risk_category', 'percentage')
    ordering = ["created_at"]


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