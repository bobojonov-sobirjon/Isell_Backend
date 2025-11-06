from tabnanny import verbose
from django.db import models


class Categories(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название категории")
    description = models.TextField(null=True, blank=True, verbose_name="Описание категории")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.name or "Неизвестная категория"

    class Meta:
        verbose_name = "01. Категория"
        verbose_name_plural = "01. Категории"


class ProductCategory(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название оценки авансового платежа")
    risk_category = models.CharField(max_length=255, null=True, blank=True, verbose_name="Рисковая категория")
    percentage = models.FloatField(null=True, blank=True, verbose_name="Процент")
    grist_product_category_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID категории в ГРИСТ")
    grist_risk_category_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID рисковой категории в ГРИСТ")
    grist_price_category_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID цены категории в ГРИСТ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.name or "Неизвестная оценка авансового платежа"
    
    class Meta:
        verbose_name = "02.  Оценка авансового платежа"
        verbose_name_plural = "02. Оценка авансового платежа"
        

class Products(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название продукта")
    category = models.ForeignKey(Categories, on_delete=models.CASCADE, related_name="products", verbose_name="Категория")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Цена")
    battery_capacity = models.CharField(max_length=255, null=True, blank=True, verbose_name="Емкость аккумулятора")
    actual = models.BooleanField(default=True, verbose_name="Актуальный")
    processor = models.CharField(max_length=255, null=True, blank=True, verbose_name="Процессор")
    screen_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название экрана")
    grist_product_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID продукта в ГРИСТ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.name or "Неизвестный продукт"
    
    class Meta:
        verbose_name = "03. Продукт"
        verbose_name_plural = "03. Продукты"
        

class ProductIDs(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="ids", verbose_name="Продукт")
    variation_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название вариации")
    variation_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID вариации")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.variation_name or "Неизвестная вариация"
    
    class Meta:
        verbose_name = "09. Вариация продукта"
        verbose_name_plural = "09. Вариации продукта"


class ProductImages(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="images", verbose_name="Продукт")
    image = models.ImageField(upload_to="products/", null=True, blank=True, verbose_name="Изображение")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        if self.image:
            return f"{self.product.name} - {self.image.name}"
        return f"{self.product.name} - Без изображения"
    
    class Meta:
        verbose_name = "04. Изображение продукта"
        verbose_name_plural = "04. Изображения продукта"


class ProductDetails(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="details", verbose_name="Продукт")
    color = models.CharField(max_length=255, null=True, blank=True, verbose_name="Цвет")
    storage = models.CharField(max_length=255, null=True, blank=True, verbose_name="Память")
    sim_card = models.CharField(max_length=255, null=True, blank=True, verbose_name="SIM-карта")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return f"{self.product.name} - {self.color} {self.storage}" if self.product else "Неизвестный продукт"
    
    class Meta:
        verbose_name = "05. Детали продукта"
        verbose_name_plural = "05. Детали продукта"
        unique_together = [['product', 'color', 'storage', 'sim_card']]


class ProductProperties(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название свойства")
    type = models.CharField(max_length=255, null=True, blank=True, verbose_name="Тип свойства")
    grist_property_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID свойства в ГРИСТ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.name or "Неизвестное свойство"
    
    class Meta:
        verbose_name = "06. Свойства продукта"
        verbose_name_plural = "06. Свойства продукта"


class ProductCharacteristics(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="characteristics", verbose_name="Продукт")
    property = models.ForeignKey(ProductProperties, on_delete=models.CASCADE, related_name="characteristics", verbose_name="Свойство")
    value = models.TextField(null=True, blank=True, verbose_name="Значение свойства")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.property.name or "Неизвестное свойство"
    
    class Meta:
        verbose_name = "07. Характеристики продукта"
        verbose_name_plural = "07. Характеристики продукта"