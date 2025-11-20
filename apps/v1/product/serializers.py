from rest_framework import serializers
from apps.v1.product.models import (
    Categories, Products, ProductDetails, ProductIDs, 
    ProductImages, ProductCharacteristics, ProductProperties,
    ProductRiskCategory
)


class CategoriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categories
        fields = ['id', 'name']


class ProductPropertiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductProperties
        fields = ['id', 'property_name', 'property_type']


class ProductCharacteristicsSerializer(serializers.ModelSerializer):
    property = ProductPropertiesSerializer(read_only=True)
    
    class Meta:
        model = ProductCharacteristics
        fields = ['id', 'property', 'value_name']


class ProductVariationSerializer(serializers.Serializer):
    """Serializer for product variations"""
    price_id = serializers.SerializerMethodField()
    variation_id = serializers.SerializerMethodField()
    variation_name = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()
    storage = serializers.SerializerMethodField()
    sim = serializers.SerializerMethodField()
    battery_capacity = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    properties = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    is_default = serializers.SerializerMethodField()
    
    def get_price_id(self, obj):
        return obj.id
    
    def _find_matching_product_ids(self, obj):
        """
        Find the matching ProductIDs for this ProductDetails based on color, storage, and sim.
        Tries to match variation_name with the combination of color, storage, and sim.
        """
        color = obj.color or ""
        storage = obj.storage or ""
        sim = obj.sim or ""
        
        sim_normalized = sim.replace("+", "").replace(" ", "").upper() if sim else ""
        
        product_ids = ProductIDs.objects.filter(product=obj.product).all()
        
        for product_id in product_ids:
            if not product_id.variation_name:
                continue
            
            variation_name = product_id.variation_name.upper()
            
            color_match = color.upper() in variation_name if color else False
            storage_match = storage.upper() in variation_name if storage else False
            
            sim_match = False
            if sim:
                if sim.upper() in variation_name:
                    sim_match = True
                elif sim_normalized and sim_normalized in variation_name.replace(" ", "").replace("+", ""):
                    sim_match = True
                elif "SIM" in sim_normalized and "SIM" in variation_name:
                    sim_match = True
                elif "DUAL" in sim_normalized and "DUAL" in variation_name:
                    sim_match = True
                elif "ESIM" in sim_normalized and "ESIM" in variation_name:
                    sim_match = True
            
            if color_match and storage_match and (sim_match if sim else True):
                return product_id
        
        return product_ids.first()
    
    def get_variation_id(self, obj):
        product_id = self._find_matching_product_ids(obj)
        return product_id.variation_id if product_id else None
    
    def get_variation_name(self, obj):
        product_id = self._find_matching_product_ids(obj)
        return product_id.variation_name if product_id else None
    
    def get_color(self, obj):
        return obj.color
    
    def get_storage(self, obj):
        return obj.storage
    
    def get_sim(self, obj):
        return obj.sim
    
    def get_battery_capacity(self, obj):
        return obj.battery_capacity
    
    def get_image(self, obj):
        request = self.context.get('request')
        first_image = obj.images.first()
        if first_image and first_image.image:
            if request:
                return request.build_absolute_uri(first_image.image.url)
            return first_image.image.url
        return None
    
    def get_price(self, obj):
        if obj.price:
            return float(obj.price)
        return None
    
    def get_properties(self, obj):
        product_id_obj = self._find_matching_product_ids(obj)
        
        if not product_id_obj:
            return []
        
        characteristics = ProductCharacteristics.objects.filter(
            product=obj.product,
            product_ids=product_id_obj
        ).select_related('property')
        
        properties_data = []
        for char in characteristics:
            properties_data.append({
                'property_id': char.property.id,
                'property_type': char.property.property_type,
                'property_name': char.property.property_name,
                'value_id': char.id,
                'value_name': char.value_name
            })
        
        return properties_data
    
    def get_is_default(self, obj):
        """Check if this variation has the minimum price (is_default)"""
        min_price_id = self.context.get('min_price_id')
        if min_price_id is not None:
            return obj.id == min_price_id
        return False


class ProductListSerializer(serializers.Serializer):
    """Serializer for all products list API"""
    id = serializers.SerializerMethodField()
    used = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    category_id = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    product_id = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    price_category_id = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    properties = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    variations = serializers.SerializerMethodField()
    filter_options = serializers.SerializerMethodField()
    
    def get_id(self, obj):
        first_detail = obj.details.first()
        return first_detail.id if first_detail else obj.id
    
    def get_used(self, obj):
        product_id = ProductIDs.objects.filter(product=obj).first()
        if product_id and product_id.variation_name:
            variation_lower = product_id.variation_name.lower()
            if 'б/у' in variation_lower or 'бу' in variation_lower or 'used' in variation_lower:
                return 1
        return 2
    
    def get_display_name(self, obj):
        product_name = obj.name or ""
        product_id = ProductIDs.objects.filter(product=obj).first()
        
        used_text = "Б/У" if self.get_used(obj) == 1 else "Новый"
        display = f"{product_name} {used_text}"
        
        if product_id and product_id.variation_name and self.get_used(obj) == 1:
            display += f", {product_id.variation_name}"
        
        return display
    
    def get_category_id(self, obj):
        return obj.category.id if obj.category else None
    
    def get_category_name(self, obj):
        return obj.category.name if obj.category else None
    
    def get_product_id(self, obj):
        return obj.id
    
    def get_product_name(self, obj):
        return obj.name
    
    def get_price_category_id(self, obj):
        return obj.price_category
    
    def get_image(self, obj):
        product_id = ProductIDs.objects.filter(product=obj).first()
        has_variation = product_id and (product_id.variation_id or product_id.variation_name)
        
        if has_variation:
            return None
        
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        first_detail = obj.details.first()
        if first_detail:
            first_image = first_detail.images.first()
            if first_image and first_image.image:
                if request:
                    return request.build_absolute_uri(first_image.image.url)
                return first_image.image.url
        return None
    
    def get_price(self, obj):
        product_id = ProductIDs.objects.filter(product=obj).first()
        has_variation = product_id and (product_id.variation_id or product_id.variation_name)
        
        if has_variation:
            return None
        
        if obj.price:
            return float(obj.price)
        first_detail = obj.details.first()
        if first_detail and first_detail.price:
            return float(first_detail.price)
        return None
    
    def get_properties(self, obj):
        product_id = ProductIDs.objects.filter(product=obj).first()
        has_variation = product_id and (product_id.variation_id or product_id.variation_name)
        
        if has_variation:
            return []
        
        characteristics = ProductCharacteristics.objects.filter(
            product=obj,
            product_ids__isnull=True
        ).select_related('property')
        
        properties_data = []
        for char in characteristics:
            properties_data.append({
                'property_id': char.property.id,
                'property_type': char.property.property_type,
                'property_name': char.property.property_name,
                'value_id': char.id,
                'value_name': char.value_name
            })
        
        return properties_data
    
    def _get_filter_params(self):
        """Get filter parameters from context"""
        return {
            'color_name': self.context.get('color_name'),
            'storage_name': self.context.get('storage_name'),
            'sim_card_name': self.context.get('sim_card_name')
        }
    
    def _get_filtered_details(self, obj):
        """Get filtered ProductDetails based on filter parameters"""
        filters = self._get_filter_params()
        details = obj.details.all()
        
        if filters['color_name']:
            details = details.filter(color=filters['color_name'])
        if filters['storage_name']:
            details = details.filter(storage=filters['storage_name'])
        if filters['sim_card_name']:
            details = details.filter(sim=filters['sim_card_name'])
        
        return details.prefetch_related('images')
    
    def _build_color_list(self, obj, color_name):
        """Build color list with is_active flags"""
        all_details = obj.details.all()
        colors = all_details.values_list('color', flat=True).distinct()
        
        color_list = []
        for color in colors:
            if color:
                color_list.append({
                    'is_active': color == color_name if color_name else False,
                    'color_name': color
                })
        return color_list
    
    def _build_storage_list(self, obj, color_name, storage_name):
        """Build storage list with is_active flags"""
        all_details = obj.details.all()
        
        if color_name:
            filtered_details = all_details.filter(color=color_name)
        else:
            filtered_details = all_details
        
        storages = filtered_details.values_list('storage', flat=True).distinct()
        
        storage_list = []
        for storage in storages:
            if storage:
                storage_list.append({
                    'is_active': storage == storage_name if storage_name else False,
                    'storage_name': storage
                })
        return storage_list
    
    def _build_sim_card_list(self, obj, color_name, storage_name, sim_card_name):
        """Build sim_card list with is_active flags"""
        all_details = obj.details.all()
        
        if color_name and storage_name:
            filtered_details = all_details.filter(color=color_name, storage=storage_name)
        elif color_name:
            filtered_details = all_details.filter(color=color_name)
        else:
            filtered_details = all_details
        
        sim_cards = filtered_details.values_list('sim', flat=True).distinct()
        
        sim_card_list = []
        for sim_card in sim_cards:
            if sim_card:
                sim_card_list.append({
                    'is_active': sim_card == sim_card_name if sim_card_name else False,
                    'sim_card_name': sim_card
                })
        return sim_card_list
    
    def get_variations(self, obj):
        details = self._get_filtered_details(obj)
        
        min_price = None
        min_price_id = None
        
        for detail in details:
            if detail.price is not None:
                price = float(detail.price)
                if min_price is None or price < min_price:
                    min_price = price
                    min_price_id = detail.id
        
        context = self.context.copy()
        context['min_price_id'] = min_price_id
        
        return ProductVariationSerializer(details, many=True, context=context).data
    
    def get_filter_options(self, obj):
        """Get all filter options combined in one object"""
        filters = self._get_filter_params()
        return {
            'color_list': self._build_color_list(obj, filters['color_name']),
            'storage_list': self._build_storage_list(obj, filters['color_name'], filters['storage_name']),
            'sim_card_list': self._build_sim_card_list(
                obj, 
                filters['color_name'], 
                filters['storage_name'], 
                filters['sim_card_name']
            )
        }


class ProductDetailSerializer(serializers.ModelSerializer):
    """Serializer for product detail API"""
    category = CategoriesSerializer(read_only=True)
    characteristics = ProductCharacteristicsSerializer(many=True, read_only=True)
    details = ProductVariationSerializer(many=True, read_only=True)
    images = serializers.SerializerMethodField()
    
    class Meta:
        model = Products
        fields = [
            'id',
            'name',
            'category',
            'price',
            'actual',
            'image',
            'images',
            'characteristics',
            'details',
            'created_at',
            'updated_at'
        ]
    
    def get_images(self, obj):
        request = self.context.get('request')
        images = []
        
        if obj.image:
            if request:
                images.append(request.build_absolute_uri(obj.image.url))
            else:
                images.append(obj.image.url)
        
        for detail in obj.details.all():
            for img in detail.images.all():
                if img.image:
                    if request:
                        images.append(request.build_absolute_uri(img.image.url))
                    else:
                        images.append(img.image.url)
        
        return images

