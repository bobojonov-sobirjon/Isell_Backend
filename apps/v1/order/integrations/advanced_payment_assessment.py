import requests
import json
import os

from apps.v1.products.models import ProductCategory


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    load_dotenv = None

API_KEY = os.getenv('ISell_API_KEY')

DOC_ID = os.getenv('ISell_DOC_ID')

Isell_ADVANCED_PAYMENT_ASSESSMENT = os.getenv('ISell_PRODUCT_ADVANCED_PAYMENT_ASSESSMENT')
Isell_RISK_CATEGORIES = os.getenv('ISell_RISK_CATEGORY')
Isell_PRICE_CATEGORIES = os.getenv('ISell_PRICE_CATEGORY')

ISell_APPLICATION = os.getenv('ISell_APPLICATION')
ISell_PRODUCTS = os.getenv('ISell_PRODUCTS')


def get_url(table_name):
    return f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{table_name}/records"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


def get_advanced_payment_assessment():
    """
    Advanced payment assessment ma'lumotlarini Grist'dan olib ProductCategory modeliga saqlash
    """
    print("[ADVANCED_PAYMENT] Starting advanced payment assessment import...")
    try:
        # Environment variables check
        if not Isell_RISK_CATEGORIES:
            print("[ADVANCED_PAYMENT] ERROR: Environment variable 'Isell_RISK_CATEGORIES' is not set")
            return {
                "success": False,
                "message": "Environment variable 'Isell_RISK_CATEGORIES' is not set"
            }
        if not Isell_PRICE_CATEGORIES:
            print("[ADVANCED_PAYMENT] ERROR: Environment variable 'Isell_PRICE_CATEGORIES' is not set")
            return {
                "success": False,
                "message": "Environment variable 'Isell_PRICE_CATEGORIES' is not set"
            }
        if not Isell_ADVANCED_PAYMENT_ASSESSMENT:
            print("[ADVANCED_PAYMENT] ERROR: Environment variable 'Isell_ADVANCED_PAYMENT_ASSESSMENT' is not set")
            return {
                "success": False,
                "message": "Environment variable 'Isell_ADVANCED_PAYMENT_ASSESSMENT' is not set"
            }
        
        # 1. Risk categories ni olish
        print("[ADVANCED_PAYMENT] Fetching risk categories...")
        risk_categories_url = get_url(Isell_RISK_CATEGORIES)
        print(f"[ADVANCED_PAYMENT] Risk categories URL: {risk_categories_url}")
        risk_response = requests.get(risk_categories_url, headers=headers)
        print(f"[ADVANCED_PAYMENT] Risk categories API Status: {risk_response.status_code}")
        
        if risk_response.status_code != 200:
            try:
                error_detail = risk_response.json()
            except:
                error_detail = risk_response.text
            print(f"[ADVANCED_PAYMENT] ERROR: Risk categories API failed - {error_detail}")
            return {
                "success": False,
                "message": f"Risk categories API Error: {risk_response.status_code}",
                "url": risk_categories_url,
                "table_name": Isell_RISK_CATEGORIES,
                "error_detail": error_detail
            }
        
        # Risk categories mapping yaratish (id -> category name)
        risk_categories_map = {}
        for record in risk_response.json().get("records", []):
            record_id = record.get("id")
            category_name = record.get("fields", {}).get("category")
            if record_id and category_name:
                risk_categories_map[record_id] = category_name
        print(f"[ADVANCED_PAYMENT] Risk categories mapped: {len(risk_categories_map)}")
        
        # 2. Product categories ni olish
        print("[ADVANCED_PAYMENT] Fetching product categories...")
        product_categories_url = get_url(Isell_PRICE_CATEGORIES)
        print(f"[ADVANCED_PAYMENT] Product categories URL: {product_categories_url}")
        product_response = requests.get(product_categories_url, headers=headers)
        print(f"[ADVANCED_PAYMENT] Product categories API Status: {product_response.status_code}")
        
        if product_response.status_code != 200:
            print(f"[ADVANCED_PAYMENT] ERROR: Product categories API failed - Status {product_response.status_code}")
            return {
                "success": False,
                "message": f"Product categories API Error: {product_response.status_code}"
            }
        
        # Product categories mapping yaratish (id -> category name)
        product_categories_map = {}
        for record in product_response.json().get("records", []):
            record_id = record.get("id")
            category_name = record.get("fields", {}).get("category")
            if record_id and category_name:
                product_categories_map[record_id] = category_name
        print(f"[ADVANCED_PAYMENT] Product categories mapped: {len(product_categories_map)}")
        
        # 3. Advanced payment assessment ni olish
        print("[ADVANCED_PAYMENT] Fetching advanced payment assessment...")
        assessment_url = get_url(Isell_ADVANCED_PAYMENT_ASSESSMENT)
        print(f"[ADVANCED_PAYMENT] Assessment URL: {assessment_url}")
        assessment_response = requests.get(assessment_url, headers=headers)
        print(f"[ADVANCED_PAYMENT] Assessment API Status: {assessment_response.status_code}")
        
        if assessment_response.status_code != 200:
            print(f"[ADVANCED_PAYMENT] ERROR: Assessment API failed - Status {assessment_response.status_code}")
            return {
                "success": False,
                "message": f"Advanced payment assessment API Error: {assessment_response.status_code}"
            }
        
        assessment_records = assessment_response.json().get("records", [])
        print(f"[ADVANCED_PAYMENT] Total assessment records: {len(assessment_records)}")
        
        # 4. ProductCategory modeliga ma'lumotlarni saqlash
        created_count = 0
        updated_count = 0
        skipped_count = 0
        skipped_details = []
        
        for record in assessment_records:
            assessment_id = record.get("id")
            fields = record.get("fields", {})
            risk_category_id = fields.get("risk_category")
            price_category_id = fields.get("price_category")
            percentage = fields.get("percentage")
            
            # ID lardan name larni olish
            risk_category_name = risk_categories_map.get(risk_category_id)
            price_category_name = product_categories_map.get(price_category_id)
            
            if not risk_category_name or not price_category_name:
                skipped_count += 1
                skipped_details.append({
                    "id": assessment_id,
                    "risk_category_id": risk_category_id,
                    "risk_category_name": risk_category_name,
                    "price_category_id": price_category_id,
                    "price_category_name": price_category_name
                })
                print(f"[ADVANCED_PAYMENT] ⚠ Skipped record {assessment_id}: Missing category mapping")
                continue
            
            try:
                # ProductCategory ni yaratish yoki yangilash
                product_category, created = ProductCategory.objects.update_or_create(
                    grist_product_category_id=str(assessment_id),
                    defaults={
                        "name": price_category_name,
                        "risk_category": risk_category_name,
                        "percentage": percentage,
                        "grist_risk_category_id": str(risk_category_id) if risk_category_id else None,
                        "grist_price_category_id": str(price_category_id) if price_category_id else None
                    }
                )
                
                if created:
                    created_count += 1
                    print(f"[ADVANCED_PAYMENT] ✓ Created: {price_category_name} - {risk_category_name} ({percentage}%)")
                else:
                    updated_count += 1
                    print(f"[ADVANCED_PAYMENT] - Updated: {price_category_name} - {risk_category_name} ({percentage}%)")
                    
            except Exception as e:
                skipped_count += 1
                print(f"[ADVANCED_PAYMENT] ⚠ Error processing record {assessment_id}: {str(e)}")
                continue
        
        print(f"[ADVANCED_PAYMENT] Import completed! Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}")
        return {
            "success": True,
            "message": "Advanced payment assessment импортирован успешно",
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "total_processed": created_count + updated_count + skipped_count,
            "risk_categories_found": len(risk_categories_map),
            "product_categories_found": len(product_categories_map),
            "risk_categories_map": risk_categories_map,
            "product_categories_map": product_categories_map,
            "skipped_details": skipped_details[:5] if skipped_details else []  # Faqat birinchi 5 ta
        }
        
    except Exception as e:
        print(f"[ADVANCED_PAYMENT] ERROR: {str(e)}")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }

def get_application():
    application_url = get_url(ISell_APPLICATION)
    application_response = requests.get(application_url, headers=headers)
    return application_response.json()

def get_products_in_grist():
    products_url = get_url(ISell_PRODUCTS)
    products_response = requests.get(products_url, headers=headers)
    return products_response.json()