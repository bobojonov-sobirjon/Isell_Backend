"""
Product price calculation service.
Handles all product price-related business logic.
"""

import logging
from typing import Dict, List, Optional, Tuple

from apps.v1.product.models import Products, ProductIDs, ProductDetails
from apps.v1.product.utils.detail_matching import find_matching_detail_price

logger = logging.getLogger(__name__)


class ProductPriceService:
    """Service for calculating product prices"""
    
    @staticmethod
    def build_variation_dict(product_ids_objects: List[ProductIDs]) -> Tuple[Dict, Dict]:
        """
        Build variation dictionary and product IDs dictionary from ProductIDs objects.
        
        Args:
            product_ids_objects: List of ProductIDs instances
            
        Returns:
            tuple: (variation_dict, product_ids_dict)
                - variation_dict: {(product_id, variation_id_str): ProductIDs}
                - product_ids_dict: {product_id: [ProductIDs, ...]}
        """
        product_ids_dict = {}
        variation_dict = {}
        
        for product_id_obj in product_ids_objects:
            product_id = product_id_obj.product_id
            
            # Build product_ids_dict
            if product_id not in product_ids_dict:
                product_ids_dict[product_id] = []
            product_ids_dict[product_id].append(product_id_obj)
            
            # Build variation_dict
            variation_id_str = str(product_id_obj.variation_id) if product_id_obj.variation_id else None
            key = (product_id, variation_id_str)
            variation_dict[key] = product_id_obj
        
        return variation_dict, product_ids_dict
    
    @staticmethod
    def get_product_price(
        product: Products,
        variation_id: Optional[int] = None,
        variation_dict: Optional[Dict] = None,
        product_ids_dict: Optional[Dict] = None
    ) -> Optional[float]:
        """
        Get product price with fallback logic.
        
        Priority:
        1. Variation-specific price from ProductDetails (if variation_id provided)
        2. Product.price
        3. Minimum price from all ProductDetails
        
        Args:
            product: Products instance
            variation_id: Optional variation ID
            variation_dict: Dictionary mapping (product_id, variation_id) to ProductIDs
            product_ids_dict: Dictionary mapping product_id to list of ProductIDs
            
        Returns:
            float or None: Product price, None if not found
        """
        if not product:
            return None
        
        product_price = None
        
        # Try to get price from variation-specific detail
        if variation_id and variation_dict:
            product_id = product.id
            key = (product_id, str(variation_id))
            product_id_obj = variation_dict.get(key)
            
            if product_id_obj and product_id_obj.variation_name:
                variation_name = product_id_obj.variation_name
                product_price = find_matching_detail_price(product, variation_name)
        
        # Fallback to product.price
        if product_price is None:
            if product.price is not None:
                product_price = float(product.price)
        
        # Fallback to minimum detail price
        if product_price is None:
            details = product.details.all()
            if details.exists():
                prices = [
                    float(detail.price) 
                    for detail in details 
                    if detail.price is not None
                ]
                if prices:
                    product_price = min(prices)
        
        return product_price
    
    @staticmethod
    def get_response_variation_id(
        variation_id: Optional[int],
        product_id: int,
        product_ids_dict: Optional[Dict]
    ) -> Optional[int]:
        """
        Get variation ID for response.
        
        Priority:
        1. variation_id from request (if provided)
        2. First variation_id from product_ids_dict
        
        Args:
            variation_id: Variation ID from request
            product_id: Product ID
            product_ids_dict: Dictionary mapping product_id to list of ProductIDs
            
        Returns:
            int or None: Variation ID for response
        """
        if variation_id:
            return variation_id
        
        if product_ids_dict and product_id in product_ids_dict:
            product_id_objects = product_ids_dict[product_id]
            if product_id_objects:
                first_obj = product_id_objects[0]
                return first_obj.variation_id if first_obj.variation_id else None
        
        return None
    
    @staticmethod
    def process_product_list(
        product_list: List[Dict],
        products_dict: Dict[int, Products],
        variation_dict: Dict,
        product_ids_dict: Dict
    ) -> Tuple[List[Dict], float]:
        """
        Process product list and calculate total sum.
        
        Args:
            product_list: List of product items from request
            products_dict: Dictionary mapping product_id to Products
            variation_dict: Dictionary mapping (product_id, variation_id) to ProductIDs
            product_ids_dict: Dictionary mapping product_id to list of ProductIDs
            
        Returns:
            tuple: (products_data, total_product_sum)
                - products_data: List of processed product data
                - total_product_sum: Total sum of all products
        """
        products_data = []
        total_product_sum = 0
        
        for item in product_list:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)
            variation_id = item.get('variation_id')
            
            product = products_dict.get(product_id)
            if not product:
                continue
            
            # Get product price
            product_price = ProductPriceService.get_product_price(
                product=product,
                variation_id=variation_id,
                variation_dict=variation_dict,
                product_ids_dict=product_ids_dict
            )
            
            if product_price is None:
                logger.warning(
                    f"Product price not found for product_id={product_id}, variation_id={variation_id}"
                )
                continue
            
            # Get response variation ID
            response_variation_id = ProductPriceService.get_response_variation_id(
                variation_id=variation_id,
                product_id=product_id,
                product_ids_dict=product_ids_dict
            )
            
            # Add to products data
            products_data.append({
                'product': product,
                'quantity': quantity,
                'price': product_price,
                'variation_id': response_variation_id
            })
            
            # Update total sum
            total_product_sum += product_price * quantity
        
        return products_data, total_product_sum

