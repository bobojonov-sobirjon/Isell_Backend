from rest_framework import serializers
from apps.v1.order.models import Tariffs, Orders, OrderItems, CompanyAddress


class TariffsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tariffs
        fields = [
            'id',
            'name',
            'payments_count',
            'offset_days',
            'type',
            'grist_tariff_id',
            'coefficient',
            'is_active',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class OrderItemsSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    tariff_name = serializers.CharField(source='tariff.name', read_only=True)
    
    class Meta:
        model = OrderItems
        fields = [
            'id',
            'product',
            'product_name',
            'tariff',
            'tariff_name',
            'quantity',
            'price',
            'down_payment',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CompanyAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyAddress
        fields = [
            'id',
            'name',
            'address',
            'latitude',
            'longitude',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class OrdersSerializer(serializers.ModelSerializer):
    items = OrderItemsSerializer(many=True, read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    calculation_mode_name = serializers.CharField(source='order_calculation_mode.name', read_only=True)
    company_address_details = CompanyAddressSerializer(source='company_address', read_only=True)
    monthly_payments = serializers.SerializerMethodField()
    
    class Meta:
        model = Orders
        fields = [
            'id',
            'user',
            'user_name',
            'order_calculation_mode',
            'calculation_mode_name',
            'status',
            'company_address',
            'company_address_details',
            'address',
            'latitude',
            'longitude',
            'items',
            'monthly_payments',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_monthly_payments(self, obj):
        from decimal import Decimal
        
        order_items = obj.items.all().prefetch_related('payment_schedule')
        
        if not order_items:
            return []
        
        merged_payments = {}
        
        for item in order_items:
            payment_schedules = item.payment_schedule.all().order_by('month_number')
            
            for schedule in payment_schedules:
                month_num = schedule.month_number
                payment_date = schedule.payment_date
                
                if month_num not in merged_payments:
                    merged_payments[month_num] = {
                        'date': payment_date.strftime('%d/%m/%y'),
                        'amount': Decimal('0')
                    }
                
                merged_payments[month_num]['amount'] += Decimal(str(schedule.monthly_payment_amount))
        
        result = []
        for month_num in sorted(merged_payments.keys()):
            payment_info = merged_payments[month_num]
            result.append({
                'month_number': month_num,
                'date': payment_info['date'],
                'monthly_payment': float(payment_info['amount'])
            })
        
        return result

