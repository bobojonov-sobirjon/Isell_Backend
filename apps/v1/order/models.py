from django.db import models
from apps.v1.accounts.models import CustomUser
from apps.v1.products.models import Products


class Tariffs(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название тарифа")
    payments_count = models.IntegerField(null=True, blank=True, verbose_name="Количество платежей")
    offset_days = models.IntegerField(null=True, blank=True, verbose_name="Количество дней отсрочки")
    type = models.CharField(max_length=255, null=True, blank=True, verbose_name="Тип тарифа")
    grist_tariff_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="ID тарифа в ГРИСТ")
    coefficient = models.FloatField(null=True, blank=True, verbose_name="Коэффициент")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.name or "Неизвестный тариф"
    
    class Meta:
        verbose_name = "01. Тарифы"
        verbose_name_plural = "01. Тарифы"


class CompanyAddress(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название компании")
    address = models.CharField(max_length=255, null=True, blank=True, verbose_name="Адрес компании")
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, verbose_name="Широта")
    longitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, verbose_name="Долгота")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.address or "Неизвестный адрес компании"
    
    class Meta:
        verbose_name = "03. Адреса компаний"
        verbose_name_plural = "03. Адреса компаний"


class OrderCaluculationMode(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название режима расчета")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.name or "Неизвестный режим расчета"
    
    class Meta:
        verbose_name = "02. Режимы расчета"
        verbose_name_plural = "02. Режимы расчета"
        

class Orders(models.Model):
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'В ожидании'
        PROCESSING = 'processing', 'В обработке'
        SHIPPED = 'shipped', 'Отправлен'
        DELIVERED = 'delivered', 'Доставлен'
        CANCELLED = 'cancelled', 'Отменен'
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name="Пользователь")
    order_calculation_mode = models.ForeignKey(OrderCaluculationMode, on_delete=models.CASCADE, verbose_name="Режим расчета")
    status = models.CharField(
        max_length=255,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус заказа"
    )
    company_address = models.ForeignKey(CompanyAddress, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Адрес компании")
    address = models.CharField(max_length=255, null=True, blank=True, verbose_name="Адрес доставки")
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, verbose_name="Широта")
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True, verbose_name="Долгота")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.user.username or "Неизвестный заказ"
    
    class Meta:
        verbose_name = "02. Заказы"
        verbose_name_plural = "02. Заказы"


class OrderItems(models.Model):
    order = models.ForeignKey(Orders, on_delete=models.CASCADE, related_name="items", verbose_name="Заказ")
    product = models.ForeignKey(Products, on_delete=models.CASCADE, verbose_name="Продукт")
    tariff = models.ForeignKey(Tariffs, on_delete=models.CASCADE, verbose_name="Тариф")
    quantity = models.IntegerField(null=True, blank=True, verbose_name="Количество")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Цена")
    down_payment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Первоначальный взнос")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return self.product.name or "Неизвестный товар"
    
    class Meta: 
        verbose_name = "03. Товары заказа"
        verbose_name_plural = "03. Товары заказа"


class OrderPaymentSchedule(models.Model):
    order_item = models.ForeignKey(OrderItems, on_delete=models.CASCADE, related_name="payment_schedule", verbose_name="Товар заказа")
    month_number = models.IntegerField(verbose_name="Номер месяца")
    payment_date = models.DateField(verbose_name="Дата платежа")
    monthly_payment_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма ежемесячного платежа")
    is_paid = models.BooleanField(default=False, verbose_name="Оплачено")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата оплаты")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    def __str__(self):
        return f"{self.order_item.product.name} - Месяц {self.month_number}"
    
    class Meta:
        verbose_name = "04. График платежей"
        verbose_name_plural = "04. График платежей"
        ordering = ['order_item', 'month_number']