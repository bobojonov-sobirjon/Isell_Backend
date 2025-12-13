from rest_framework import serializers
from apps.v1.order.models import Tariffs, Orders, OrderItems, CompanyAddress
from apps.v1.product.models import Products, ProductIDs, ProductDetails, ProductImages
from apps.v1.product.serializers import CategoriesSerializer
from apps.v1.product.services.product_price_service import ProductPriceService
from apps.v1.product.utils.detail_matching import find_matching_detail_price


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


class ProductSerializerForOrder(serializers.ModelSerializer):
    """Serializer for product in order items"""
    category = CategoriesSerializer(read_only=True)
    image = serializers.SerializerMethodField()
    
    class Meta:
        model = Products
        fields = [
            'id',
            'name',
            'price',
            'price_category',
            'actual',
            'image',
            'category'
        ]
    
    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class VariationSerializerForOrder(serializers.ModelSerializer):
    """Serializer for variation in order items"""
    product_details = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductIDs
        fields = [
            'id',
            'variation_id',
            'variation_name',
            'grist_product_id',
            'product_id',
            'product_details'
        ]
    
    def get_product_details(self, obj):
        """Get matching product details for this variation"""
        if not obj.product or not obj.variation_name:
            return None
        
        request = self.context.get('request')
        product_id = obj.product.id
        details_for_product = ProductDetails.objects.filter(
            product_id=product_id
        ).select_related('product').prefetch_related('images')
        
        variation_name_upper = obj.variation_name.upper()
        
        best_match_score = 0
        matching_product_detail = None
        
        for detail in details_for_product:
            score = 0
            color = detail.color or ""
            storage = detail.storage or ""
            sim = detail.sim or ""
            
            if color and color.upper() in variation_name_upper:
                score += 1
            
            if storage and storage.upper() in variation_name_upper:
                score += 1
            
            if sim:
                sim_normalized = sim.replace("+", "").replace(" ", "").upper()
                variation_normalized = variation_name_upper.replace(" ", "").replace("+", "")
                if sim.upper() in variation_name_upper:
                    score += 1
                elif sim_normalized and sim_normalized in variation_normalized:
                    score += 1
                elif "SIM" in sim_normalized and "SIM" in variation_name_upper:
                    score += 1
                elif "DUAL" in sim_normalized and "DUAL" in variation_name_upper:
                    score += 1
                elif "ESIM" in sim_normalized and "ESIM" in variation_name_upper:
                    score += 1
            
            if score > best_match_score:
                best_match_score = score
                matching_product_detail = detail
        
        if matching_product_detail:
            product_images_list = []
            images_for_detail = matching_product_detail.images.all()
            
            for image in images_for_detail:
                image_url = None
                if image.image:
                    if request:
                        image_url = request.build_absolute_uri(image.image.url)
                    else:
                        image_url = image.image.url
                
                product_images_list.append({
                    "id": image.id,
                    "image": image_url
                })
            
            return {
                "id": matching_product_detail.id,
                "color": matching_product_detail.color or "",
                "storage": matching_product_detail.storage or "",
                "sim": matching_product_detail.sim or "",
                "battery_capacity": matching_product_detail.battery_capacity or "",
                "price": float(matching_product_detail.price) if matching_product_detail.price else 0,
                "images": product_images_list
            }
        
        return None


class OrderItemsSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    tariff_name = serializers.CharField(source='tariff.name', read_only=True)
    product = ProductSerializerForOrder(read_only=True)
    variation = VariationSerializerForOrder(read_only=True)
    price = serializers.SerializerMethodField()
    
    def get_price(self, obj):
        """
        Get product price based on variation, similar to CalculatePaymentScheduleSimpleView.
        Priority:
        1. Variation-specific price from ProductDetails (if variation exists)
        2. Stored price in OrderItems
        3. Product.price
        4. Minimum price from all ProductDetails
        """
        product = obj.product
        variation = obj.variation
        
        # If variation exists, try to get price from matching detail
        if variation and variation.variation_name:
            variation_name = variation.variation_name
            product_price = find_matching_detail_price(product, variation_name)
            if product_price is not None:
                return str(product_price)
        
        # Fallback to stored price in OrderItems
        if obj.price is not None:
            return str(obj.price)
        
        # Fallback to product.price
        if product and product.price is not None:
            return str(product.price)
        
        # Fallback to minimum detail price
        if product:
            details = product.details.all()
            if details.exists():
                prices = [
                    float(detail.price) 
                    for detail in details 
                    if detail.price is not None
                ]
                if prices:
                    return str(min(prices))
        
        return None
    
    class Meta:
        model = OrderItems
        fields = [
            'id',
            'product',
            'product_name',
            'variation',
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
            'longitude'
        ]
        read_only_fields = ['id']


class OrdersSerializer(serializers.ModelSerializer):
    items = OrderItemsSerializer(many=True, read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    calculation_mode_name = serializers.SerializerMethodField()
    company_address_details = CompanyAddressSerializer(source='company_address', read_only=True)
    monthly_payments = serializers.SerializerMethodField()
    
    def get_calculation_mode_name(self, obj):
        return obj.get_order_calculation_mode_display()
    
    def get_monthly_payments(self, obj):
        """Get merged monthly payments for all order items"""
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
    
