"""
Product detail matching utilities.
Handles matching of product details (color, storage, SIM) with variation names.
"""

from apps.v1.product.constants import SIMKeywords


def match_product_detail(detail, variation_name):
    """
    Match product detail with variation name based on color, storage, and SIM.
    
    This function checks if a product detail matches a variation name by comparing:
    - Color (if present in detail)
    - Storage (if present in detail)
    - SIM type (if present in detail and variation has SIM info)
    
    Args:
        detail: ProductDetails instance with color, storage, sim, and price attributes
        variation_name: str - Variation name to match against (e.g., "GRAY TITANIUM 256GB DUAL SIM")
        
    Returns:
        tuple: (is_match: bool, price: float or None)
            - is_match: True if all conditions match
            - price: Price from detail if match, None otherwise
    """
    if not detail or not variation_name:
        return False, None
    
    # Normalize inputs
    color = (detail.color or "").upper()
    storage = (detail.storage or "").upper()
    sim = (detail.sim or "").upper()
    variation_name_upper = variation_name.upper()
    
    # Color matching
    color_match = color in variation_name_upper if color else True
    
    # Storage matching
    storage_match = storage in variation_name_upper if storage else True
    
    # SIM matching - only required if both detail and variation have SIM info
    sim_match = True
    if sim:
        variation_has_sim_info = SIMKeywords.has_sim_info(variation_name_upper)
        if variation_has_sim_info:
            sim_normalized = sim.replace("+", "").replace(" ", "")
            variation_normalized = variation_name_upper.replace(" ", "").replace("+", "")
            
            # Check multiple SIM matching strategies
            sim_match = (
                sim in variation_name_upper or
                sim_normalized in variation_normalized or
                any(keyword in sim_normalized and keyword in variation_name_upper 
                    for keyword in SIMKeywords.SIM_KEYWORDS)
            )
        # If variation doesn't have SIM info, we don't require SIM match
        else:
            sim_match = True
    
    # All conditions must match
    if color_match and storage_match and sim_match:
        price = float(detail.price) if detail.price is not None else None
        return True, price
    
    return False, None


def find_matching_detail_price(product, variation_name):
    """
    Find matching detail price for a product and variation name.
    
    Args:
        product: Products instance
        variation_name: str - Variation name to match
        
    Returns:
        float or None: Price from matching detail, None if no match found
    """
    if not product or not variation_name:
        return None
    
    details = product.details.all()
    
    for detail in details:
        is_match, price = match_product_detail(detail, variation_name)
        if is_match and price is not None:
            return price
    
    return None

