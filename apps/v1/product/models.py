from django.db import models


class Categories(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название категории")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.name or "Неизвестная категория"

    class Meta:
        db_table = 'product_categories'
        verbose_name = "01. Категория"
        verbose_name_plural = "01. Категории"


class ProductRiskCategory(models.Model):
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
        db_table = 'product_risk_categories'
        verbose_name = "02.  Оценка авансового платежа"
        verbose_name_plural = "02. Оценка авансового платежа"


class Products(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название продукта")
    category = models.ForeignKey(Categories, on_delete=models.CASCADE, related_name="products", verbose_name="Категория")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Цена")
    price_category = models.CharField(max_length=255, null=True, blank=True, verbose_name="Категория цены")
    actual = models.BooleanField(default=True, verbose_name="Актуальный")
    image = models.ImageField(upload_to="products/", null=True, blank=True, verbose_name="Изображение")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.name or "Неизвестный продукт"
    
    class Meta:
        db_table = 'product_products'
        verbose_name = "03. Продукт"
        verbose_name_plural = "03. Продукты"


class ProductIDs(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="ids", verbose_name="Продукт")
    grist_product_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID продукта в ГРИСТ")
    variation_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название вариации")
    variation_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID вариации")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.variation_name or "Неизвестная вариация"
    
    class Meta:
        db_table = 'product_product_ids'
        verbose_name = "09. Вариация продукта"
        verbose_name_plural = "09. Вариации продукта"


class ProductDetails(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="details", verbose_name="Продукт")
    color = models.CharField(max_length=255, null=True, blank=True, verbose_name="Цвет")
    storage = models.CharField(max_length=255, null=True, blank=True, verbose_name="Память")
    sim = models.CharField(max_length=255, null=True, blank=True, verbose_name="SIM-карта")
    battery_capacity = models.CharField(max_length=255, null=True, blank=True, verbose_name="Емкость аккумулятора")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Цена")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return f"{self.product.name} - {self.color} {self.storage}" if self.product else "Неизвестный продукт"
    
    class Meta:
        db_table = 'product_product_details'
        verbose_name = "05. Детали продукта"
        verbose_name_plural = "05. Детали продукта"
        unique_together = [['product', 'color', 'storage', 'sim']]
        

class ProductImages(models.Model):
    product_details = models.ForeignKey(ProductDetails, on_delete=models.CASCADE, related_name="images", verbose_name="Детали продукта")
    image = models.ImageField(upload_to="products/", null=True, blank=True, verbose_name="Изображение")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        if self.image:
            return f"{self.product_details.product.name} - {self.image.name}"
        return f"{self.product_details.product.name} - Без изображения"
    
    class Meta:
        db_table = 'product_product_images'
        verbose_name = "04. Изображение детали продукта"
        verbose_name_plural = "04. Изображения детали продукта"


class ProductProperties(models.Model):
    property_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название свойства")
    property_type = models.CharField(max_length=255, null=True, blank=True, verbose_name="Тип свойства")
    grist_property_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID свойства в ГРИСТ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.property_name or "Неизвестное свойство"
    
    class Meta:
        db_table = 'product_product_properties'
        verbose_name = "06. Свойства продукта"
        verbose_name_plural = "06. Свойства продукта"


class ProductCharacteristics(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="characteristics", verbose_name="Продукт")
    product_ids = models.ForeignKey(ProductIDs, on_delete=models.CASCADE, related_name="characteristics", verbose_name="Вариация продукта", null=True, blank=True)
    property = models.ForeignKey(ProductProperties, on_delete=models.CASCADE, related_name="characteristics", verbose_name="Свойство")
    value_name = models.TextField(null=True, blank=True, verbose_name="Значение свойства")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.property.property_name or "Неизвестное свойство"
    
    class Meta:
        db_table = 'product_product_characteristics'
        verbose_name = "07. Характеристика продукта"
        verbose_name_plural = "07. Характеристики продукта"
    

class ProductAutomaticallyImportedTime(models.Model):
    TIME_TYPE_CHOICES = [
        ('minutes', 'Минуты'),
        ('hours', 'Часы'),
    ]
    
    time = models.IntegerField(null=True, blank=True, verbose_name="Время автоматического импорта")
    time_type = models.CharField(max_length=10, choices=TIME_TYPE_CHOICES, default='minutes', verbose_name="Тип времени")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def get_interval_minutes(self):
        """Возвращает интервал в минутах"""
        if not self.time:
            return None
        if self.time_type == 'hours':
            return self.time * 60
        return self.time
    
    def __str__(self):
        if self.time:
            time_type_str = 'минут' if self.time_type == 'minutes' else 'часов'
            return f"{self.time} {time_type_str}"
        return "Неизвестное время автоматического импорта"
    
    class Meta:
        db_table = 'product_product_automatically_imported_time'
        verbose_name = "08. Время автоматического импорта"
        verbose_name_plural = "08. Время автоматического импорта"
        

class Banner(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название баннера")
    description = models.TextField(null=True, blank=True, verbose_name="Описание баннера")
    link = models.URLField(null=True, blank=True, verbose_name="Ссылка на баннер")
    image = models.ImageField(upload_to="banners/", null=True, blank=True, verbose_name="Изображение")
    is_active = models.BooleanField(default=True, verbose_name="Активный")
    order = models.IntegerField(default=0, verbose_name="Порядок")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.name or "Неизвестный баннер"
    
    class Meta:
        verbose_name = "08. Баннер"
        verbose_name_plural = "08. Баннеры"