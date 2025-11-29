import requests
import json
import os
import asyncio
import aiohttp
from pathlib import Path

from apps.v1.product.models import ProductRiskCategory

# Django settings dan BASE_DIR ni olish
try:
    from django.conf import settings
    BASE_DIR = settings.BASE_DIR
except:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent

try:
    from dotenv import load_dotenv
    env_path = BASE_DIR / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        load_dotenv(override=True)
except ImportError:
    load_dotenv = None
except Exception:
    pass

API_KEY = os.getenv('ISell_API_KEY')
DOC_ID = os.getenv('ISell_DOC_ID')

Isell_ADVANCED_PAYMENT_ASSESSMENT = os.getenv('ISell_PRODUCT_ADVANCED_PAYMENT_ASSESSMENT')
Isell_RISK_CATEGORIES = os.getenv('ISell_RISK_CATEGORY')
Isell_PRICE_CATEGORIES = os.getenv('ISell_PRICE_CATEGORY')

ISell_CONTERPARTIES=os.getenv('ISell_CONTERPARTIES')
ISell_APPLICATION = os.getenv('ISell_APPLICATION')
ISell_PRODUCTS = os.getenv('ISell_PRODUCTS')
ISell_PRODUCT_PRICE = os.getenv('ISell_PRODUCT_PRICE')


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
                product_category, created = ProductRiskCategory.objects.update_or_create(
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

def get_counterparties_in_grist():
    counterparties_url = get_url(ISell_CONTERPARTIES)
    counterparties_response = requests.get(counterparties_url, headers=headers)
    return counterparties_response.json()

def get_products_in_grist():
    products_url = get_url(ISell_PRODUCTS)
    products_response = requests.get(products_url, headers=headers)
    return products_response.json()

async def fetch_price_data_async(session, url):
    """Async function to fetch Price data from Grist"""
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                return None
    except Exception:
        return None

def get_price_data_by_product_ids(product_ids):
    """
    Get Price data from Grist filtered by product_ids
    
    Args:
        product_ids: List of product IDs to filter by
    
    Returns:
        List of Price records matching the product_ids
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not ISell_PRODUCT_PRICE or not product_ids:
        return []
    
    try:
        url = get_url(ISell_PRODUCT_PRICE)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_price_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        records = data.get("records", [])
        
        # Filter records by product_id
        filtered_records = []
        for record in records:
            fields = record.get("fields", {})
            record_product_id = fields.get("product_id")
            
            # Check if this record's product_id is in our list
            if record_product_id in product_ids:
                filtered_records.append(record)
        
        return filtered_records
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching Price data: {str(e)}")
        return []

def get_product_ids_from_price_table_by_grist_ids(grist_product_ids):
    """
    Get product_ids from Price table by grist_product_ids (record ids)
    
    Args:
        grist_product_ids: List of grist_product_ids (Price table record ids)
    
    Returns:
        List of product_ids from Price table fields.product_id
    """
    if not ISell_PRODUCT_PRICE or not grist_product_ids:
        return []
    
    try:
        url = get_url(ISell_PRODUCT_PRICE)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_price_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        records = data.get("records", [])
        
        # Filter records by id (grist_product_id is the record id in Price table)
        product_ids = []
        grist_ids_set = set(grist_product_ids)  # Use set for faster lookup
        
        for record in records:
            record_id = record.get("id")
            if record_id in grist_ids_set:
                fields = record.get("fields", {})
                product_id = fields.get("product_id")
                if product_id:
                    product_ids.append(product_id)
        
        return product_ids
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting product_ids from Price table: {str(e)}")
        return []

def post_to_grist_application(counterparty_id, date, stage, risk_category_id, issue_limit, products):
    """
    Create a new application record in Grist Application table
    
    Args:
        counterparty_id: Counterparty ID
        date: Date (string format YYYY-MM-DD)
        stage: Stage/Status (New, Assessment, Accepted, Denied, Denied by client, Success)
        risk_category_id: Risk category ID
        issue_limit: Issue limit (total_advance_payment)
        products: List of grist_product_ids
    """
    import logging
    logger = logging.getLogger(__name__)
    
    print(f"[DEBUG] [post_to_grist_application] Called with:")
    print(f"[DEBUG] [post_to_grist_application]   - counterparty_id: {counterparty_id}")
    print(f"[DEBUG] [post_to_grist_application]   - date: {date}")
    print(f"[DEBUG] [post_to_grist_application]   - stage: {stage}")
    print(f"[DEBUG] [post_to_grist_application]   - risk_category_id: {risk_category_id}")
    print(f"[DEBUG] [post_to_grist_application]   - issue_limit: {issue_limit}")
    print(f"[DEBUG] [post_to_grist_application]   - products: {products}")
    
    if not API_KEY or not DOC_ID or not ISell_APPLICATION:
        print(f"[DEBUG] [post_to_grist_application] ❌ Missing env vars - API_KEY: {bool(API_KEY)}, DOC_ID: {bool(DOC_ID)}, ISell_APPLICATION: {bool(ISell_APPLICATION)}")
        logger.error("Missing API_KEY, DOC_ID, or ISell_APPLICATION environment variables")
        return None
    
    if not counterparty_id:
        print(f"[DEBUG] [post_to_grist_application] ❌ Missing counterparty_id")
        logger.error("counterparty_id is required but was not provided")
        return None
    
    # Note: products parameter contains product_ids from Price table (fields.product_id)
    
    url = f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{ISell_APPLICATION}/records"
    
    request_headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Convert date string to timestamp (Grist expects timestamp for date fields)
    date_timestamp = None
    if date:
        try:
            from datetime import datetime as dt
            from django.utils import timezone
            import pytz
            
            # Parse date string (YYYY-MM-DD format)
            parsed_date = dt.strptime(date, "%Y-%m-%d").date()
            # Convert to UTC datetime at midnight
            parsed_datetime = dt.combine(parsed_date, dt.min.time())
            parsed_datetime_utc = timezone.make_aware(parsed_datetime, pytz.UTC)
            date_timestamp = int(parsed_datetime_utc.timestamp())
        except Exception as e:
            logger.warning(f"Failed to convert date to timestamp: {date}, error: {str(e)}")
            # Fallback: try to use date as is
            date_timestamp = date
    
    # Format products as Grist reference list: ["L", id1, id2, ...]
    # Grist reference fields that are lists need to be formatted with "L" prefix
    formatted_products = []
    if products and len(products) > 0:
        formatted_products = ["L"] + products
    else:
        formatted_products = []
    
    # Build fields dictionary, only including non-None values
    fields = {
        "counterparty_id": counterparty_id,
        "date": date_timestamp if date_timestamp else date,
        "stage": stage,
        "issue_limit": issue_limit,
        "products": formatted_products
    }
    
    # Only add risk_category_id if it's not None
    if risk_category_id is not None:
        fields["risk_category_id"] = risk_category_id
    
    payload = {
        "records": [
            {
                "fields": fields
            }
        ]
    }
    
    print(f"[DEBUG] [post_to_grist_application] URL: {url}")
    print(f"[DEBUG] [post_to_grist_application] Table name: {ISell_APPLICATION}")
    print(f"[DEBUG] [post_to_grist_application] Payload: {payload}")
    print(f"[DEBUG] [post_to_grist_application] Date timestamp: {date_timestamp}")
    print(f"[DEBUG] [post_to_grist_application] Formatted products: {formatted_products}")
    
    try:
        print(f"[DEBUG] [post_to_grist_application] Sending POST request to Grist...")
        response = requests.post(url, json=payload, headers=request_headers)
        print(f"[DEBUG] [post_to_grist_application] Response status code: {response.status_code}")
        print(f"[DEBUG] [post_to_grist_application] Response text: {response.text[:500]}")
        
        response.raise_for_status()
        result = response.json()
        print(f"[DEBUG] [post_to_grist_application] ✅ Success! Response: {result}")
        return result
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        response_text = ""
        try:
            if hasattr(e, 'response') and e.response is not None:
                response_text = e.response.text
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = response_text
            else:
                error_detail = str(e)
        except Exception as ex:
            error_detail = str(e)
            logger.error(f"Error parsing error response: {str(ex)}")
        
        status_code = e.response.status_code if hasattr(e, 'response') and e.response is not None else 'N/A'
        print(f"[DEBUG] [post_to_grist_application] ❌ HTTP Error! Status: {status_code}")
        print(f"[DEBUG] [post_to_grist_application] Error detail: {error_detail}")
        print(f"[DEBUG] [post_to_grist_application] Response text: {response_text}")
        logger.error(f"HTTP error posting to Grist application: {error_detail}, Status: {status_code}")
        logger.error(f"Response text: {response_text}")
        logger.error(f"Payload was: {payload}")
        return None
    except Exception as e:
        print(f"[DEBUG] [post_to_grist_application] ❌ Exception! Error: {str(e)}, Type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        logger.error(f"Error posting to Grist application: {str(e)}, Type: {type(e).__name__}")
        logger.error(f"Payload was: {payload}")
        return None