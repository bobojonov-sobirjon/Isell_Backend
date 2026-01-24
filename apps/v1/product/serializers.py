from rest_framework import serializers
from apps.v1.product.models import (
    Categories, Products, ProductDetails, ProductIDs, 
    ProductImages, ProductCharacteristics, ProductProperties,
    ProductRiskCategory, Banner
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
        First checks if there's a pre-computed mapping in context, otherwise tries to match.
        """
        # First, check if there's a pre-computed mapping in context
        detail_to_product_id_map = self.context.get('detail_to_product_id_map')
        if detail_to_product_id_map and obj.id in detail_to_product_id_map:
            return detail_to_product_id_map[obj.id]
        
        # Fallback to matching logic if no mapping provided
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
        return obj.id
    
    def get_used(self, obj):
        product_name = (obj.name or "").upper()
        if 'B/U' in product_name or 'B-U' in product_name or 'USED' in product_name:
            return 1
        
        product_id = ProductIDs.objects.filter(product=obj).first()
        if product_id and product_id.variation_name:
            variation_upper = (product_id.variation_name or "").upper()
            if 'B/U' in variation_upper or 'B-U' in variation_upper or 'USED' in variation_upper:
                return 1
        
        return 2
    
    def get_display_name(self, obj):
        product_name = obj.name or ""
        product_id = ProductIDs.objects.filter(product=obj).first()
        is_used = self.get_used(obj) == 1
        
        import re
        cleaned_name = re.sub(r'\s*(B/U|B-U|USED|NEW)\s*', '', product_name, flags=re.IGNORECASE).strip()
        
        if not cleaned_name:
            cleaned_name = product_name
        
        used_text = "Б/У" if is_used else "Новый"
        display = f"{cleaned_name} {used_text}"
        
        if product_id and product_id.variation_name and is_used:
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
        request = self.context.get('request')
        
        # First check if product has a direct image
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        
        # Then check for images in product details (works for both with and without variations)
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
        product_ids = ProductIDs.objects.filter(product=obj)
        has_variations = product_ids.exists() and any(
            pid.variation_name and pid.variation_name.strip() 
            for pid in product_ids
        )
        
        if has_variations:
            actual_product_ids = list(product_ids.filter(is_actual=True))
            
            if not actual_product_ids:
                return []
            
            all_details = list(obj.details.all().prefetch_related('images'))
            
            matched_details = []
            detail_to_product_id_map = {}  # Mapping from detail.id -> product_id
            for product_id in actual_product_ids:
                matching_detail = self._find_detail_for_product_id(product_id, all_details)
                if matching_detail:
                    if not any(d.id == matching_detail.id for d in matched_details):
                        matched_details.append(matching_detail)
                        # Store the mapping: detail.id -> product_id
                        detail_to_product_id_map[matching_detail.id] = product_id
            
            filters = self._get_filter_params()
            if filters['color_name'] or filters['storage_name'] or filters['sim_card_name']:
                filtered_details = []
                filtered_map = {}
                for detail in matched_details:
                    if filters['color_name'] and detail.color != filters['color_name']:
                        continue
                    if filters['storage_name'] and detail.storage != filters['storage_name']:
                        continue
                    if filters['sim_card_name'] and detail.sim != filters['sim_card_name']:
                        continue
                    filtered_details.append(detail)
                    # Preserve mapping for filtered details
                    if detail.id in detail_to_product_id_map:
                        filtered_map[detail.id] = detail_to_product_id_map[detail.id]
                matched_details = filtered_details
                detail_to_product_id_map = filtered_map
            
            details = matched_details
        else:
            if not obj.is_actual:
                return []
            
            details = self._get_filtered_details(obj)
            detail_to_product_id_map = {}  # No mapping for non-variation products
        
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
        context['detail_to_product_id_map'] = detail_to_product_id_map
        
        return ProductVariationSerializer(details, many=True, context=context).data
    
    def _find_product_id_for_detail(self, detail, product_ids_list):
        """
        ProductDetails uchun mos ProductIDs ni topish
        Faqat actual_product_ids_list dan (is_actual=True) mos keladiganini qaytaradi
        Agar topilmasa, None qaytaradi
        """
        color = detail.color or ""
        storage = detail.storage or ""
        sim = detail.sim or ""
        
        sim_normalized = sim.replace("+", "").replace(" ", "").upper() if sim else ""
        
        for product_id in product_ids_list:
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
        
        return None
    
    def _find_detail_for_product_id(self, product_id, details_list):
        """
        ProductID uchun mos ProductDetails ni topish
        Variation name dan color, storage, sim ni ajratib, mos ProductDetails ni qaytaradi
        """
        if not product_id.variation_name:
            return None
        
        variation_name = product_id.variation_name.upper().strip()
        variation_words = set(word.strip() for word in variation_name.split() if word.strip())
        
        best_match = None
        best_score = 0
        
        for detail in details_list:
            color = (detail.color or "").upper().strip()
            storage = (detail.storage or "").upper().strip()
            sim = (detail.sim or "").upper().strip()
            
            score = 0
            
            color_match = False
            if color:
                color_words = set(word.strip() for word in color.split() if word.strip())
                if color in variation_name:
                    color_match = True
                    score += 3
                elif color_words and any(cw in variation_name for cw in color_words if len(cw) > 2):
                    color_match = True
                    score += 2
                elif variation_words and any(vw in color for vw in variation_words if len(vw) > 2 and vw not in ['NEW', 'GB', 'SIM']):
                    color_match = True
                    score += 2
            
            storage_match = True
            if storage:
                if storage in variation_name:
                    storage_match = True
                    score += 2
                elif storage.replace(" ", "") in variation_name.replace(" ", ""):
                    storage_match = True
                    score += 2
                elif any(sw in variation_name for sw in storage.split() if sw and len(sw) > 1):
                    storage_match = True
                    score += 2
                else:
                    storage_match = False
            
            sim_match = True
            if sim:
                sim_normalized = sim.replace("+", "").replace(" ", "").upper()
                variation_normalized = variation_name.replace(" ", "").replace("+", "").upper()
                
                has_sim_in_variation = (
                    "SIM" in variation_name or 
                    "DUAL" in variation_name or 
                    "ESIM" in variation_name
                )
                
                if has_sim_in_variation:
                    if sim in variation_name:
                        sim_match = True
                        score += 1
                    elif sim_normalized in variation_normalized:
                        sim_match = True
                        score += 1
                    elif "SIM" in sim and "SIM" in variation_name:
                        sim_match = True
                        score += 1
                    elif "DUAL" in sim and "DUAL" in variation_name:
                        sim_match = True
                        score += 1
                    elif "ESIM" in sim and "ESIM" in variation_name:
                        sim_match = True
                        score += 1
                    else:
                        sim_match = False
            
            if color_match and storage_match and sim_match:
                if score > best_score:
                    best_score = score
                    best_match = detail
        
        return best_match
    
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



class BannerSerializer(serializers.ModelSerializer):

    class Meta:
        model = Banner
        fields = [
            'id',
            'name',
            'description',
            'link',
            'image',
            'is_active',
            'order'
        ]