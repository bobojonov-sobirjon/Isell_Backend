"""
Helper functions for processing sales data
Optimized for performance and clean code
"""
from collections import defaultdict
from apps.v1.product.models import Products, ProductIDs, ProductDetails, ProductImages
import logging

logger = logging.getLogger(__name__)


def extract_counterparty_ids_from_orders(orders):
    """
    Extract unique counterparty_ids from orders
    Returns set of counterparty_ids
    """
    counterparty_ids = set()
    for order in orders:
        if order.counterparty_id:
            try:
                counterparty_id = int(order.counterparty_id)
                counterparty_ids.add(counterparty_id)
            except (ValueError, TypeError):
                pass
    return counterparty_ids


def build_product_price_map(product_price_data):
    """
    Build a map for quick lookup of product price data
    Key: (product_id, variation_id)
    Value: {id, product_name, variation_name}
    """
    product_price_map = {}
    
    for record in product_price_data:
        fields = record.get("fields", {})
        product_id = fields.get("product_id")
        variation_id = fields.get("variation_id")
        
        if product_id and variation_id:
            key = (product_id, variation_id)
            product_price_map[key] = {
                "id": record.get("id"),
                "product_name": fields.get("product_name"),
                "variation_name": fields.get("variation_name")
            }
    
    return product_price_map


def group_sales_products_by_sale_id(sales_products):
    """
    Group sales products by sale_id
    Returns defaultdict with sale_id as key and list of products as value
    """
    sales_products_by_sale = defaultdict(list)
    
    for sp in sales_products:
        fields = sp.get("fields", {})
        sale_id = fields.get("sale_id")
        if sale_id:
            sales_products_by_sale[sale_id].append(sp)
    
    return sales_products_by_sale


def process_transactions_for_sale_products(sale_products, all_transactions):
    """
    Process transactions for sale products
    Returns map: (sale_id, product_id, variation_id) -> list of transactions
    """
    from datetime import datetime
    
    transactions_by_sale_id = {}
    for transaction in all_transactions:
        fields = transaction.get("fields", {})
        sale_id = fields.get("sale_id")
        if sale_id:
            if sale_id not in transactions_by_sale_id:
                transactions_by_sale_id[sale_id] = []
            transactions_by_sale_id[sale_id].append(transaction)
    
    transactions_map = {}
    for sp in sale_products:
        sp_fields = sp.get("fields", {})
        sale_id = sp_fields.get("sale_id")
        grist_product_id = sp_fields.get("product_id")
        grist_variation_id = sp_fields.get("variation_id")
        
        if sale_id and grist_product_id and grist_variation_id:
            key = (sale_id, grist_product_id, grist_variation_id)
            transactions_for_sale = transactions_by_sale_id.get(sale_id, [])
            
            transactions_list = []
            for trans in transactions_for_sale:
                trans_fields = trans.get("fields", {})
                date_timestamp = trans_fields.get("date")
                amount = trans_fields.get("amount", 0) or 0
                
                formatted_date = None
                if date_timestamp:
                    try:
                        dt = datetime.fromtimestamp(int(date_timestamp))
                        formatted_date = dt.strftime("%d/%m/%Y")
                    except (ValueError, TypeError, OSError):
                        formatted_date = str(date_timestamp)
                
                transactions_list.append({
                    "date": formatted_date,
                    "amount": float(amount) if amount else 0
                })
            
            transactions_map[key] = transactions_list
    
    return transactions_map


def process_sale_product_by_variation_id(sale_product, transactions_map=None, all_transactions=None, request=None):
    """
    Process a single sale product by variation_id from SALES_PRODUCTS
    Returns product data and variation data
    """
    from datetime import datetime
    
    sp_fields = sale_product.get("fields", {})
    sale_id = sp_fields.get("sale_id")
    variation_id = sp_fields.get("variation_id")  # Bu SALES_PRODUCTS'dan keladi
    product_id = sp_fields.get("product_id")
    
    if not variation_id:
        return None, None
    
    # ProductIDs table'dan variation_id bo'yicha qidirish
    try:
        product_id_obj = ProductIDs.objects.filter(variation_id=str(variation_id)).select_related('product').first()
    except Exception as e:
        logger.error(f"[process_sale_product_by_variation_id] Error querying ProductIDs: {str(e)}", exc_info=True)
        product_id_obj = None
    
    if not product_id_obj or not product_id_obj.product:
        return None, None
    
    product = product_id_obj.product
    
    # Product data
    product_image_url = None
    if product.image:
        if request:
            product_image_url = request.build_absolute_uri(product.image.url)
        else:
            product_image_url = product.image.url
    
    product_data = {
        "id": product.id,
        "name": product.name or "",
        "price": float(product.price) if product.price else 0,
        "price_category": product.price_category or "",
        "actual": product.actual,
        "image": product_image_url,
        "category": {
            "id": product.category.id if product.category else None,
            "name": product.category.name if product.category else ""
        } if product.category else None
    }
    
    # Transactions list
    transactions_list = []
    if transactions_map and sale_id:
        grist_product_id = sp_fields.get("product_id")
        grist_variation_id = sp_fields.get("variation_id")
        transactions_key = (sale_id, grist_product_id, grist_variation_id)
        transactions_list = transactions_map.get(transactions_key, [])
    
    # Variation data
    variation_data = {
        "id": product_id_obj.id,
        "variation_id": product_id_obj.variation_id or "",
        "variation_name": product_id_obj.variation_name or "",
        "grist_product_id": product_id_obj.grist_product_id or "",
        "product_id": product_id_obj.product.id if product_id_obj.product else None,
        "transactions": transactions_list
    }
    
    # Product details ni topish
    matching_product_detail = None
    if product_id_obj.product and product_id_obj.variation_name:
        product_id = product_id_obj.product.id
        details_for_product = ProductDetails.objects.filter(
            product_id=product_id
        ).select_related('product').prefetch_related('images')
        
        variation_name_upper = product_id_obj.variation_name.upper()
        
        best_match_score = 0
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
            image_data = {
                "id": image.id,
                "image": request.build_absolute_uri(image.image.url) if image.image and request else (image.image.url if image.image else None)
            }
            product_images_list.append(image_data)
        
        variation_data["product_details"] = {
            "id": matching_product_detail.id,
            "color": matching_product_detail.color or "",
            "storage": matching_product_detail.storage or "",
            "sim": matching_product_detail.sim or "",
            "battery_capacity": matching_product_detail.battery_capacity or "",
            "price": float(matching_product_detail.price) if matching_product_detail.price else 0,
            "images": product_images_list
        }
    else:
        variation_data["product_details"] = None
    
    return product_data, variation_data


def process_fact_planned_transactions(fact_planned_transactions):
    """
    Process fact_planned_transactions from Grist format
    Format: ["L", ["L", ["d", timestamp], amount], ...]
    Returns list of {date, amount, is_paid}
    """
    from datetime import datetime
    
    processed_transactions = []
    
    if not isinstance(fact_planned_transactions, list) or len(fact_planned_transactions) <= 1:
        return processed_transactions
    
    for trans in fact_planned_transactions[1:]:
        if not isinstance(trans, list) or len(trans) < 2:
            continue
        
        date_part = None
        amount = 0
        
        if len(trans) >= 3 and isinstance(trans[1], list):
            date_part = trans[1]
            amount = trans[2] if len(trans) > 2 else 0
        elif len(trans) >= 2 and isinstance(trans[0], list):
            date_part = trans[0]
            amount = trans[1] if len(trans) > 1 else 0
        
        if date_part and isinstance(date_part, list) and len(date_part) >= 2:
            timestamp = date_part[1]
            is_paid = (amount == 0) if isinstance(amount, (int, float)) else False
            
            formatted_date = None
            if timestamp:
                try:
                    dt = datetime.fromtimestamp(int(timestamp))
                    formatted_date = dt.strftime("%d/%m/%Y")
                except (ValueError, TypeError, OSError):
                    formatted_date = str(timestamp)
            
            processed_transactions.append({
                "date": formatted_date,
                "amount": float(amount) if amount else 0,
                "is_paid": is_paid
            })
    
    return processed_transactions


def process_sale_data_with_all_variations(sale, sale_products, transactions_map=None, all_transactions=None, request=None):
    """
    Process a single sale with all its products/variations
    Bir sales_id ga tegishli barcha product'lar bitta object ichida variation_list sifatida to'planadi
    Agar bir nechta turli product bo'lsa, har bir product uchun alohida product_data yaratiladi
    """
    from datetime import datetime
    from collections import defaultdict
    
    sale_id = sale.get("id")
    fields = sale.get("fields", {})
    
    # Sale ma'lumotlari
    total = fields.get("total", 0) or 0
    remainder = fields.get("reminder", 0) or 0
    advance_corrected = fields.get("advance_corrected", 0) or 0
    paid = fields.get("paid", 0) or 0
    debet_0 = fields.get("debet_0", 0) or 0
    fact_planned_transactions = fields.get("fact_planned_transactions", [])
    
    # Product'larni product_id bo'yicha guruhlash
    products_by_id = defaultdict(list)
    
    for sale_product in sale_products:
        product_data_item, variation_data = process_sale_product_by_variation_id(sale_product, transactions_map, all_transactions, request)
        
        if not product_data_item or not variation_data:
            continue
        
        product_id = product_data_item.get("id")
        products_by_id[product_id].append({
            "product_data": product_data_item,
            "variation": variation_data
        })
    
    if not products_by_id:
        return None
    
    # Har bir product uchun product_data yaratish
    product_data_list = []
    
    for product_id, product_items in products_by_id.items():
        # Birinchi item'dan product ma'lumotlarini olish (barcha bir xil)
        product_data = product_items[0]["product_data"]
        
        # Barcha variation'larni to'plash
        variation_list = [item["variation"] for item in product_items]
        
        product_data_list.append({
            "product": product_data,
            "variation_list": variation_list
        })
    
    # Sale transactions
    sale_transactions = []
    if all_transactions and sale_id:
        for transaction in all_transactions:
            trans_fields = transaction.get("fields", {})
            trans_sale_id = trans_fields.get("sale_id")
            
            if trans_sale_id == sale_id:
                date_timestamp = trans_fields.get("date")
                amount = trans_fields.get("amount", 0) or 0
                
                formatted_date = None
                if date_timestamp:
                    try:
                        dt = datetime.fromtimestamp(int(date_timestamp))
                        formatted_date = dt.strftime("%d/%m/%Y")
                    except (ValueError, TypeError, OSError):
                        formatted_date = str(date_timestamp)
                
                sale_transactions.append({
                    "date": formatted_date,
                    "amount": float(amount) if amount else 0
                })
    
    processed_transactions = process_fact_planned_transactions(fact_planned_transactions)
    
    # Sale data yaratish (barcha product'lar bilan)
    sale_data = {
        "product_data": product_data_list,  # Barcha product'lar ro'yxati
        "total": float(total) if total else 0,
        "remainder": float(remainder) if remainder else 0,
        "advance_corrected": float(advance_corrected) if advance_corrected else 0,
        "paid": float(paid) if paid else 0,
        "debet_0": float(debet_0) if debet_0 else 0,
        "transactions": sale_transactions,
        "fact_planned_transactions": processed_transactions,
        "status": "finished"  # Default status
    }
    
    return sale_data


def separate_active_and_completed_sales_new(all_sales, sales_products_by_sale, all_transactions, request=None):
    """
    Process all sales and separate into active and completed
    Bir sales_id ga tegishli barcha product'lar bitta object ichida variation_list sifatida to'planadi
    Returns (active_sales, completed_sales)
    """
    all_sale_products = []
    for sale_products in sales_products_by_sale.values():
        all_sale_products.extend(sale_products)
    
    transactions_map = process_transactions_for_sale_products(all_sale_products, all_transactions)
    
    active_sales = []
    completed_sales = []
    
    for sale in all_sales:
        sale_id = sale.get("id")
        sale_products = sales_products_by_sale.get(sale_id, [])
        
        if not sale_products:
            continue
        
        # Bir sales_id ga tegishli barcha product'larni bitta object ichida to'plash
        sale_data = process_sale_data_with_all_variations(sale, sale_products, transactions_map, all_transactions, request)
        
        if not sale_data:
            continue
        
        debet_0 = sale_data.get("debet_0", 0)
        
        if debet_0 > 0:
            active_sales.append(sale_data)
        else:
            completed_sales.append(sale_data)
    
    return active_sales, completed_sales

