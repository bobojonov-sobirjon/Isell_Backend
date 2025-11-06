from django.contrib import admin

from apps.v1.order.models import Tariffs, OrderCaluculationMode, Orders, OrderItems, OrderPaymentSchedule, CompanyAddress

@admin.register(Tariffs)
class TariffsAdmin(admin.ModelAdmin):
    list_display = ('name', 'payments_count', 'offset_days', 'type', 'grist_tariff_id', 'coefficient', 'is_active')
    search_fields = ('name', 'type', 'grist_tariff_id')
    list_filter = ('is_active', 'type')
    readonly_fields = ('created_at', 'updated_at', 'grist_tariff_id')
    ordering = ('-created_at',)
    list_per_page = 20
    list_max_show_all = 100
    list_editable = ('is_active',)
    list_display_links = ('name',)
    

@admin.register(OrderCaluculationMode)
class OrderCaluculationModeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    list_per_page = 20
    list_max_show_all = 100
    list_display_links = ('name',)


@admin.register(CompanyAddress)
class CompanyAddressAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'latitude', 'longitude', 'created_at')
    search_fields = ('name', 'address')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    list_per_page = 20


class OrderPaymentScheduleInline(admin.TabularInline):
    model = OrderPaymentSchedule
    extra = 0
    fields = ('month_number', 'payment_date', 'monthly_payment_amount', 'is_paid', 'paid_at')
    readonly_fields = ('month_number', 'payment_date', 'monthly_payment_amount')
    can_delete = False
    show_change_link = True


class OrderItemsInline(admin.TabularInline):
    model = OrderItems
    extra = 0
    fields = ('product', 'tariff', 'quantity', 'price', 'down_payment')
    readonly_fields = ('product', 'tariff', 'quantity', 'price', 'down_payment')
    can_delete = False
    show_change_link = True


@admin.register(Orders)
class OrdersAdmin(admin.ModelAdmin):
    list_display = ('user', 'order_calculation_mode', 'get_status_display', 'company_address', 'address', 'status', 'created_at')
    search_fields = ('user__username', 'user__email', 'address')
    list_filter = ('status', 'order_calculation_mode', 'company_address', 'created_at')
    readonly_fields = ('created_at', 'updated_at', 'display_payment_schedule')
    ordering = ('-created_at',)
    list_per_page = 20
    inlines = [OrderItemsInline]
    actions = ['mark_as_processing', 'mark_as_shipped', 'mark_as_delivered', 'mark_as_cancelled']
    
    def get_status_display(self, obj):
        return obj.get_status_display()
    get_status_display.short_description = 'Статус'
    
    @admin.action(description='Изменить статус на "В обработке"')
    def mark_as_processing(self, request, queryset):
        updated = queryset.update(status=Orders.Status.PROCESSING)
        self.message_user(request, f'{updated} заказ(ов) изменено на "В обработке"')
    
    @admin.action(description='Изменить статус на "Отправлен"')
    def mark_as_shipped(self, request, queryset):
        updated = queryset.update(status=Orders.Status.SHIPPED)
        self.message_user(request, f'{updated} заказ(ов) изменено на "Отправлен"')
    
    @admin.action(description='Изменить статус на "Доставлен"')
    def mark_as_delivered(self, request, queryset):
        updated = queryset.update(status=Orders.Status.DELIVERED)
        self.message_user(request, f'{updated} заказ(ов) изменено на "Доставлен"')
    
    @admin.action(description='Изменить статус на "Отменен"')
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status=Orders.Status.CANCELLED)
        self.message_user(request, f'{updated} заказ(ов) изменено на "Отменен"')
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'order_calculation_mode', 'status')
        }),
        ('Адрес доставки', {
            'fields': ('company_address', 'address', 'latitude', 'longitude')
        }),
        ('График платежей', {
            'fields': ('display_payment_schedule',),
            'classes': ('collapse',),
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def display_payment_schedule(self, obj):
        from django.utils.html import format_html
        from decimal import Decimal
        
        order_items = obj.items.all().prefetch_related('payment_schedule')
        
        if not order_items:
            return "Нет товаров в заказе"
        
        html = '<div style="margin: 20px 0;">'
        
        # Show products info
        html += '<div style="margin-bottom: 20px;">'
        for item in order_items:
            html += f'<p><strong>Товар:</strong> {item.product.name} | <strong>Тариф:</strong> {item.tariff.name} | <strong>Количество:</strong> {item.quantity} | <strong>Цена:</strong> {item.price} | <strong>Первоначальный взнос:</strong> {item.down_payment}</p>'
        html += '</div>'
        
        # Merge payment schedules
        merged_payments = {}
        
        for item in order_items:
            payment_schedules = item.payment_schedule.all().order_by('month_number')
            
            for schedule in payment_schedules:
                month_num = schedule.month_number
                payment_date = schedule.payment_date
                
                if month_num not in merged_payments:
                    merged_payments[month_num] = {
                        'date': payment_date,
                        'amount': Decimal('0'),
                        'schedules': []
                    }
                
                merged_payments[month_num]['amount'] += Decimal(str(schedule.monthly_payment_amount))
                merged_payments[month_num]['schedules'].append(schedule)
        
        if merged_payments:
            html += '<h3 style="color: #417690;">График платежей по всем товарам:</h3>'
            html += '<table style="width: 100%; border-collapse: collapse; margin-top: 10px;">'
            html += '''
                <thead>
                    <tr style="background-color: #f5f5f5;">
                        <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Месяц</th>
                        <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Дата платежа</th>
                        <th style="border: 1px solid #ddd; padding: 8px; text-align: right;">Сумма платежа</th>
                        <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Оплачено</th>
                        <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Дата оплаты</th>
                    </tr>
                </thead>
                <tbody>
            '''
            
            for month_num in sorted(merged_payments.keys()):
                payment_info = merged_payments[month_num]
                schedules = payment_info['schedules']
                
                # Check if all schedules for this month are paid
                all_paid = all(s.is_paid for s in schedules)
                is_paid_icon = '✅' if all_paid else '❌'
                
                # Get paid date (if all paid, show the latest paid date)
                paid_dates = [s.paid_at for s in schedules if s.paid_at]
                paid_date = max(paid_dates).strftime('%d.%m.%Y %H:%M') if paid_dates else '-'
                
                row_style = 'background-color: #e8f5e9;' if all_paid else ''
                
                html += f'''
                    <tr style="{row_style}">
                        <td style="border: 1px solid #ddd; padding: 8px;">{month_num}</td>
                        <td style="border: 1px solid #ddd; padding: 8px;">{payment_info['date'].strftime('%d.%m.%Y')}</td>
                        <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{payment_info['amount']:.2f}</td>
                        <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{is_paid_icon}</td>
                        <td style="border: 1px solid #ddd; padding: 8px;">{paid_date}</td>
                    </tr>
                '''
            
            html += '</tbody></table>'
        else:
            html += '<p style="color: #666;">Нет графика платежей</p>'
        
        html += '</div>'
        return format_html(html)
    
    display_payment_schedule.short_description = 'График платежей по всем товарам'


@admin.register(OrderItems)
class OrderItemsAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product', 'tariff', 'quantity', 'price', 'down_payment')
    search_fields = ('product__name', 'order__id')
    list_filter = ('tariff', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    list_per_page = 20
    inlines = [OrderPaymentScheduleInline]


@admin.register(OrderPaymentSchedule)
class OrderPaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_item', 'month_number', 'payment_date', 'monthly_payment_amount', 'is_paid', 'paid_at')
    search_fields = ('order_item__product__name', 'order_item__order__id')
    list_filter = ('is_paid', 'payment_date', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('order_item', 'month_number')
    list_per_page = 50
    list_editable = ('is_paid',)