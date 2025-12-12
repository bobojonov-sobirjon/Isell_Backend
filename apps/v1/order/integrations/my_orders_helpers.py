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


def process_sale_products(sale_products, product_price_map, transactions_map=None):
    """
    Process sale products and return product_ids and variation_list
    Optimized with bulk database queries
    """
    if not sale_products:
        return [], []
    
    price_record_ids = []
    price_record_to_product_info = {}
    
    for sp in sale_products:
        sp_fields = sp.get("fields", {})
        sale_id = sp_fields.get("sale_id")
        grist_product_id = sp_fields.get("product_id")
        grist_variation_id = sp_fields.get("variation_id")
        
        if grist_product_id and grist_variation_id:
            price_key = (grist_product_id, grist_variation_id)
            price_info = product_price_map.get(price_key)
            
            if price_info:
                price_record_id = price_info.get("id")
                if price_record_id:
                    price_record_ids.append(str(price_record_id))
                    price_record_to_product_info[str(price_record_id)] = {
                        "grist_product_id": grist_product_id,
                        "grist_variation_id": grist_variation_id
                    }
    
    if not price_record_ids:
        return [], []
    
    product_ids_objs = ProductIDs.objects.filter(
        grist_product_id__in=price_record_ids
    ).select_related('product')
    
    product_ids_list = [obj.product.id for obj in product_ids_objs if obj.product]
    
    product_details_objs = ProductDetails.objects.filter(
        product_id__in=product_ids_list
    ).select_related('product').prefetch_related('images')
    
    product_details_ids = [detail.id for detail in product_details_objs]
    
    product_images_objs = ProductImages.objects.filter(
        product_details_id__in=product_details_ids
    ).select_related('product_details')
    
    product_images_map = {}
    for image in product_images_objs:
        product_details_id = image.product_details.id if image.product_details else None
        if product_details_id:
            if product_details_id not in product_images_map:
                product_images_map[product_details_id] = []
            product_images_map[product_details_id].append(image)
    
    product_details_map = {}
    for detail in product_details_objs:
        product_id = detail.product.id if detail.product else None
        if product_id:
            if product_id not in product_details_map:
                product_details_map[product_id] = []
            product_details_map[product_id].append(detail)
    
    grist_id_to_product_id_obj = {}
    for obj in product_ids_objs:
        grist_id_to_product_id_obj[obj.grist_product_id] = obj
    
    products_list = []
    variation_list = []
    seen_product_ids = set()
    
    for sp in sale_products:
        sp_fields = sp.get("fields", {})
        sale_id = sp_fields.get("sale_id")
        grist_product_id = sp_fields.get("product_id")
        grist_variation_id = sp_fields.get("variation_id")
        
        if grist_product_id and grist_variation_id:
            price_key = (grist_product_id, grist_variation_id)
            price_info = product_price_map.get(price_key)
            
            if price_info:
                price_record_id = str(price_info.get("id"))
                product_id_obj = grist_id_to_product_id_obj.get(price_record_id)
                
                if product_id_obj and product_id_obj.product:
                    product = product_id_obj.product
                    product_id = product.id
                    
                    if product_id not in seen_product_ids:
                        product_data = {
                            "id": product.id,
                            "name": product.name or "",
                            "price": float(product.price) if product.price else 0,
                            "price_category": product.price_category or "",
                            "actual": product.actual,
                            "image": product.image.url if product.image else None,
                            "category": {
                                "id": product.category.id if product.category else None,
                                "name": product.category.name if product.category else ""
                            } if product.category else None
                        }
                        products_list.append(product_data)
                        seen_product_ids.add(product_id)
                    
                    transactions_list = []
                    if transactions_map and sale_id:
                        transactions_key = (sale_id, grist_product_id, grist_variation_id)
                        transactions_list = transactions_map.get(transactions_key, [])
                    
                    variation_data = {
                        "id": product_id_obj.id,
                        "variation_id": product_id_obj.variation_id or "",
                        "variation_name": product_id_obj.variation_name or "",
                        "grist_product_id": product_id_obj.grist_product_id or "",
                        "product_id": product_id_obj.product.id if product_id_obj.product else None,
                        "transactions": transactions_list
                    }
                    
                    matching_product_detail = None
                    if product_id_obj.product and product_id_obj.variation_name:
                        product_id = product_id_obj.product.id
                        details_for_product = product_details_map.get(product_id, [])
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
                        product_details_id = matching_product_detail.id
                        images_for_detail = product_images_map.get(product_details_id, [])
                        
                        for image in images_for_detail:
                            image_data = {
                                "id": image.id,
                                "image": image.image.url if image.image else None
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
                    
                    variation_list.append(variation_data)
    
    return products_list, variation_list


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


def process_sale_data(sale, sale_products, product_price_map, transactions_map=None, all_transactions=None, order=None):
    """
    Process a single sale and return sale data
    """
    from datetime import datetime
    from apps.v1.order.models import Orders
    
    sale_id = sale.get("id")
    fields = sale.get("fields", {})
    
    total = fields.get("total", 0) or 0
    remainder = fields.get("reminder", 0) or 0
    paid = fields.get("paid", 0) or 0
    debet_0 = fields.get("debet_0", 0) or 0
    fact_planned_transactions = fields.get("fact_planned_transactions", [])
    
    products_list, variation_list = process_sale_products(sale_products, product_price_map, transactions_map)
    
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
    
    product_data = products_list[0] if products_list else None
    
    status = None
    if order:
        status = order.status
    
    sale_data = {
        "product": product_data,
        "variation_list": variation_list,
        "total": float(total) if total else 0,
        "remainder": float(remainder) if remainder else 0,
        "paid": float(paid) if paid else 0,
        "debet_0": float(debet_0) if debet_0 else 0,
        "transactions": sale_transactions,
        "fact_planned_transactions": processed_transactions,
        "status": status
    }
    
    return sale_data


def separate_active_and_completed_sales(all_sales, sales_products_by_sale, product_price_map, all_transactions, orders_map=None):
    """
    Process all sales and separate into active and completed
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
        
        sale_fields = sale.get("fields", {})
        counterparty_id = sale_fields.get("counterpart_id") or sale_fields.get("counterparty_id")
        
        order = None
        if orders_map and counterparty_id:
            try:
                counterparty_id_int = int(counterparty_id)
                order = orders_map.get(counterparty_id_int)
            except (ValueError, TypeError):
                pass
        
        sale_data = process_sale_data(sale, sale_products, product_price_map, transactions_map, all_transactions, order)
        
        debet_0 = sale_data.get("debet_0", 0)
        
        if debet_0 > 0:
            active_sales.append(sale_data)
        else:
            completed_sales.append(sale_data)
    
    return active_sales, completed_sales

