from rest_framework import serializers
from apps.v1.products.models import Categories, Products, ProductDetails, ProductIDs, ProductImages, ProductCharacteristics, ProductProperties, Banner


class CategoriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categories
        fields = '__all__'  
        

class ProductDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductDetails
        fields = [
            'id',
            'color',
            'storage',
            'sim_card'
        ]


class ProductImagesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImages
        fields = [
            'id',
            'image',
            'product'
        ]


class ProductPropertiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductProperties
        fields = [
            'id',
            'name',
            'type',
            'grist_property_id'
        ]


class ProductCharacteristicsSerializer(serializers.ModelSerializer):
    property = ProductPropertiesSerializer(read_only=True)
    
    class Meta:
        model = ProductCharacteristics
        fields = [
            'id',
            'property',
            'value'
        ]


class ProductsSerializer(serializers.ModelSerializer):
    details = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    characteristics = serializers.SerializerMethodField()
    
    class Meta:
        model = Products
        fields = [
            'id',
            'name',
            'category',
            'price',
            'battery_capacity',
            'processor',
            'screen_name',
            'details',
            'images',
            'characteristics'
        ]
        
    def get_details(self, obj):
        return ProductDetailsSerializer(obj.details.all(), many=True, context=self.context).data
    
    def get_images(self, obj):
        return ProductImagesSerializer(obj.images.all(), many=True, context=self.context).data
    
    def get_category(self, obj):
        return CategoriesSerializer(obj.category).data
    
    def get_characteristics(self, obj):
        return ProductCharacteristicsSerializer(obj.characteristics.all(), many=True, context=self.context).data


class CharacteristicsDetailSerializer(serializers.Serializer):
    """Serializer for characteristic detail values"""
    id = serializers.IntegerField()
    value = serializers.CharField()


class CharacteristicsGroupSerializer(serializers.Serializer):
    """Serializer for grouped characteristics by property name"""
    name_property = serializers.CharField()
    details = CharacteristicsDetailSerializer(many=True)


class ProductDetailFilterSerializer(serializers.Serializer):
    """Serializer for filtered product details with cascading options"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    category = CategoriesSerializer()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    battery_capacity = serializers.CharField()
    processor = serializers.CharField()
    screen_name = serializers.CharField()
    images = ProductImagesSerializer(many=True)
    color_list = serializers.ListField()
    storage_list = serializers.ListField()
    sim_card_list = serializers.ListField()
    characteristics = CharacteristicsGroupSerializer(many=True)
    

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