import requests
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.files.base import ContentFile
from django.db import transaction

from apps.v1.products.models import Categories, Products, ProductIDs, ProductDetails, ProductProperties, ProductCharacteristics, ProductImages

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

ISell_PRODUCT_VARIATIONS_TABLE_NAME = os.getenv('ISell_PRODUCT_VARIATIONS')
Isell_PRODUCT_PRICE = os.getenv('ISell_PRODUCT_PRICE')

ISell_PROPERTY = os.getenv('ISell_PROPERTY')
ISell_PROPERTY_VALUE = os.getenv('ISell_PROPERTY_VALUE')
ISell_PRODUCT_PROPERTY_VALUE = os.getenv('ISell_PRODUCT_PROPERTY_VALUE')

def get_url(table_name):
    return f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{table_name}/records"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


def get_all_actual_true_products(response):
    actual_products = []
    for product in response.get("records", []):
        if product.get("fields", {}).get("actual") == True:
            actual_products.append(product.get("fields"))
    return actual_products


def process_products(products_data):
    grouped_products = {}
    
    for product_data in products_data:
        product_name = product_data.get("product_name")
        variation_name = product_data.get("variation_name", "")
        
        if not product_name:
            continue
            
        if product_name not in grouped_products:
            grouped_products[product_name] = {
                "new_products": [],
                "used_products": []
            }
        
        if "NEW" in variation_name.upper():
            grouped_products[product_name]["new_products"].append(product_data)
        elif "B/U" in variation_name.upper():
            grouped_products[product_name]["used_products"].append(product_data)
        else:
            grouped_products[product_name]["new_products"].append(product_data)
    
    return grouped_products


def save_products_to_db(grouped_products):
    created_count = 0
    skipped_count = 0
    product_ids_saved = 0
    
    for product_name, product_groups in grouped_products.items():
        if product_groups["new_products"]:
            first_product = product_groups["new_products"][0]
            
            try:
                category_name = first_product.get("category_name")
                category = None
                if category_name:
                    category, _ = Categories.objects.get_or_create(
                        name=category_name
                    )
                
                if not category:
                    skipped_count += 1
                    continue
                
                existing_product = Products.objects.filter(
                    name=product_name,
                    category=category
                ).first()
                
                if not existing_product:
                    new_product = Products.objects.create(
                        name=product_name,
                        category=category,
                        price=first_product.get("price"),
                        grist_product_id=first_product.get("product_id"),
                        actual=True
                    )
                    created_count += 1
                    
                    for product_data in product_groups["new_products"]:
                        var_name = product_data.get("variation_name")
                        var_id = product_data.get("variation_id")
                        if var_name:
                            ProductIDs.objects.get_or_create(
                                product=new_product,
                                variation_name=var_name,
                                variation_id=var_id
                            )
                            product_ids_saved += 1
                else:
                    for product_data in product_groups["new_products"]:
                        var_name = product_data.get("variation_name")
                        var_id = product_data.get("variation_id")
                        if var_name:
                            ProductIDs.objects.get_or_create(
                                product=existing_product,
                                variation_name=var_name,
                                variation_id=var_id
                            )
                            product_ids_saved += 1
                    skipped_count += 1
                    
            except Exception as e:
                skipped_count += 1
        
        for product_data in product_groups["used_products"]:
            try:
                category_name = product_data.get("category_name")
                category = None
                if category_name:
                    category, _ = Categories.objects.get_or_create(
                        name=category_name
                    )
                
                if not category:
                    skipped_count += 1
                    continue
                
                bu_product = Products.objects.create(
                    name=product_name,
                    category=category,
                    price=product_data.get("price"),
                    grist_product_id=product_data.get("product_id"),
                    actual=True
                )
                created_count += 1
                
                var_name = product_data.get("variation_name")
                var_id = product_data.get("variation_id")
                if var_name:
                    ProductIDs.objects.get_or_create(
                        product=bu_product,
                        variation_name=var_name,
                        variation_id=var_id
                    )
                    product_ids_saved += 1
                    
            except Exception as e:
                skipped_count += 1
    
    return created_count, skipped_count, product_ids_saved


def get_product_variations():
    try:
        url = get_url(ISell_PRODUCT_VARIATIONS_TABLE_NAME)
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None
        
        variations = []
        for record in response.json().get("records", []):
            fields = record.get("fields", {})
            if fields.get("fully_defined") == True:
                variations.append(fields)
        
        return variations
        
    except Exception as e:
        return None


def get_product_variations_for_images():
    """Rasmlar uchun variations olish (ID va fields bilan)"""
    try:
        url = get_url(ISell_PRODUCT_VARIATIONS_TABLE_NAME)
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None
        
        variations = []
        for record in response.json().get("records", []):
            fields = record.get("fields", {})
            if fields.get("fully_defined") == True:
                # ID ni fields ichiga qo'shamiz
                fields['variation_record_id'] = record.get("id")
                variations.append(fields)
        
        return variations
        
    except Exception as e:
        return None


def process_variations_by_product(variations):
    variations_by_product = {}
    
    for variation in variations:
        variation_name = variation.get("name")
        used = variation.get("used", False)
        product_name = variation.get("product_name")
        
        if not variation_name:
            continue
        
        try:
            product_id_obj = ProductIDs.objects.filter(
                variation_name=variation_name,
                product__name=product_name
            ).first()
            
            if not product_id_obj:
                continue
            
            product = product_id_obj.product
            product_key = f"{product.id}_{'bu' if used else 'new'}"
            
            if product_key not in variations_by_product:
                variations_by_product[product_key] = {
                    "product": product,
                    "used": used,
                    "variations": []
                }
            
            variations_by_product[product_key]["variations"].append(variation)
            
        except Exception as e:
            continue
    
    return variations_by_product


def save_product_details(variations_by_product):
    details_created = 0
    details_skipped = 0
    
    for product_key, data in variations_by_product.items():
        product = data["product"]
        used = data["used"]
        variations = data["variations"]
        
        try:
            if used == False:
                unique_combinations = {}
                
                for variation in variations:
                    color = variation.get("color", "")
                    storage = variation.get("storage", "")
                    sim = variation.get("sim", "")
                    
                    key = f"{color}_{storage}_{sim}"
                    
                    if key not in unique_combinations:
                        unique_combinations[key] = variation
                
                for variation in unique_combinations.values():
                    color = variation.get("color")
                    storage = variation.get("storage")
                    sim = variation.get("sim")
                    
                    try:
                        detail, created = ProductDetails.objects.get_or_create(
                            product=product,
                            color=color,
                            storage=storage,
                            sim_card=sim
                        )
                        
                        if created:
                            details_created += 1
                        else:
                            details_skipped += 1
                    except Exception as e:
                        pass
                        
            elif used == True:
                for variation in variations:
                    color = variation.get("color")
                    storage = variation.get("storage")
                    sim = variation.get("sim")
                    
                    detail, created = ProductDetails.objects.get_or_create(
                        product=product,
                        color=color,
                        storage=storage,
                        sim_card=sim
                    )
                    
                    if created:
                        details_created += 1
                    else:
                        details_skipped += 1
                    
        except Exception as e:
            details_skipped += len(variations)
    
    return details_created, details_skipped


def get_products():
    print("[PRODUCT_LISTS] Starting products import...")
    try:
        url = get_url(Isell_PRODUCT_PRICE)
        print(f"[PRODUCT_LISTS] API URL: {url}")
        response = requests.get(url, headers=headers)
        print(f"[PRODUCT_LISTS] API Response Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"[PRODUCT_LISTS] ERROR: API returned status {response.status_code}")
            return {
                "success": False,
                "message": f"API Error: {response.status_code}"
            }
        
        actual_products = get_all_actual_true_products(response.json())
        print(f"[PRODUCT_LISTS] Total actual products found: {len(actual_products)}")
        
        if not actual_products:
            print("[PRODUCT_LISTS] WARNING: No actual products found")
            return {
                "success": False,
                "message": "Актуальные продукты не найдены"
            }
        
        grouped_products = process_products(actual_products)
        print(f"[PRODUCT_LISTS] Products grouped into {len(grouped_products)} unique products")
        
        created_count, skipped_count, product_ids_saved = save_products_to_db(grouped_products)
        print(f"[PRODUCT_LISTS] Import completed! Created: {created_count}, Skipped: {skipped_count}, Product IDs saved: {product_ids_saved}")
        
        return {
            "success": True,
            "message": "Продукты импортированы успешно",
            "created": created_count,
            "skipped": skipped_count,
            "product_ids_saved": product_ids_saved,
            "total_processed": created_count + skipped_count
        }
        
    except Exception as e:
        print(f"[PRODUCT_LISTS] ERROR: {str(e)}")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def import_product_details():
    print("[PRODUCT_LISTS] Starting product details import...")
    try:
        variations = get_product_variations()
        print(f"[PRODUCT_LISTS] Total variations retrieved: {len(variations) if variations else 0}")
        
        if not variations:
            print("[PRODUCT_LISTS] WARNING: No variations found")
            return {
                "success": False,
                "message": "Вариации не найдены"
            }
        
        variations_by_product = process_variations_by_product(variations)
        print(f"[PRODUCT_LISTS] Variations grouped by {len(variations_by_product)} products")
        
        details_created, details_skipped = save_product_details(variations_by_product)
        print(f"[PRODUCT_LISTS] Details import completed! Created: {details_created}, Skipped: {details_skipped}")
        
        return {
            "success": True,
            "message": "Детали продуктов импортированы успешно",
            "details_created": details_created,
            "details_skipped": details_skipped,
            "total_processed": details_created + details_skipped
        }
        
    except Exception as e:
        print(f"[PRODUCT_LISTS] ERROR in import_product_details: {str(e)}")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def get_product_properties_from_grist():
    """Grist'dan Product_properties table ma'lumotlarini olish"""
    try:
        url = get_url(ISell_PROPERTY)
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None
        
        return response.json().get("records", [])
        
    except Exception as e:
        return None


def save_product_properties(properties_data):
    """ProductProperties modeliga ma'lumotlarni saqlash"""
    created_count = 0
    updated_count = 0
    
    for record in properties_data:
        grist_id = record.get("id")
        fields = record.get("fields", {})
        name = fields.get("name")
        property_type = fields.get("type")
        
        if not grist_id or not name:
            continue
        
        try:
            property_obj, created = ProductProperties.objects.update_or_create(
                grist_property_id=str(grist_id),
                defaults={
                    "name": name,
                    "type": property_type
                }
            )
            
            if created:
                created_count += 1
            else:
                updated_count += 1
                
        except Exception as e:
            continue
    
    return created_count, updated_count


def import_product_properties():
    """Product properties import qilish"""
    print("[PRODUCT_LISTS] Starting product properties import...")
    try:
        properties = get_product_properties_from_grist()
        print(f"[PRODUCT_LISTS] Total properties retrieved: {len(properties) if properties else 0}")
        
        if not properties:
            print("[PRODUCT_LISTS] WARNING: No properties found")
            return {
                "success": False,
                "message": "Свойства продуктов не найдены"
            }
        
        created_count, updated_count = save_product_properties(properties)
        print(f"[PRODUCT_LISTS] Properties import completed! Created: {created_count}, Updated: {updated_count}")
        
        return {
            "success": True,
            "message": "Свойства продуктов импортированы успешно",
            "created": created_count,
            "updated": updated_count,
            "total_processed": created_count + updated_count
        }
        
    except Exception as e:
        print(f"[PRODUCT_LISTS] ERROR in import_product_properties: {str(e)}")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def get_product_property_values_from_grist():
    """Grist'dan Product_property_value table ma'lumotlarini olish"""
    try:
        url = get_url(ISell_PRODUCT_PROPERTY_VALUE)
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None
        
        return response.json().get("records", [])
        
    except Exception as e:
        return None


def get_property_values_from_grist():
    """Grist'dan Property_values table ma'lumotlarini olish"""
    try:
        url = get_url(ISell_PROPERTY_VALUE)
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None
        
        return response.json().get("records", [])
        
    except Exception as e:
        return None


def process_characteristics_data(product_property_values, property_values):
    """Product characteristics ma'lumotlarini qayta ishlash"""
    characteristics_to_save = []
    
    # Property values ni dictionary ga aylantirish (value_id bo'yicha)
    property_values_dict = {}
    for record in property_values:
        value_id = record.get("id")
        fields = record.get("fields", {})
        property_id = fields.get("property_id")
        value = fields.get("value")
        
        if value_id and property_id:
            property_values_dict[value_id] = {
                "property_id": property_id,
                "value": value
            }
    
    # Product IDs bo'yicha guruhlash
    for record in product_property_values:
        fields = record.get("fields", {})
        product_name = fields.get("product_name")
        variation_id = fields.get("variation_id")
        value_id = fields.get("value_id")
        property_id = fields.get("property_id")
        
        if not all([product_name, variation_id, value_id, property_id]):
            continue
        
        # ProductIDs dan product ni topish
        try:
            product_id_obj = ProductIDs.objects.filter(
                product__name=product_name,
                variation_id=str(variation_id)
            ).first()
            
            if not product_id_obj:
                continue
            
            product = product_id_obj.product
            
            # Property values dan value ni topish
            if value_id in property_values_dict:
                prop_value_data = property_values_dict[value_id]
                
                # Property_id tekshirish
                if prop_value_data["property_id"] == property_id:
                    value = prop_value_data["value"]
                    
                    # ProductProperties ni topish
                    property_obj = ProductProperties.objects.filter(
                        grist_property_id=str(property_id)
                    ).first()
                    
                    if property_obj:
                        characteristics_to_save.append({
                            "product": product,
                            "property": property_obj,
                            "value": value
                        })
                        
        except Exception as e:
            continue
    
    return characteristics_to_save


def save_product_characteristics(characteristics_data):
    """ProductCharacteristics modeliga ma'lumotlarni saqlash"""
    created_count = 0
    skipped_count = 0
    
    for char_data in characteristics_data:
        product = char_data.get("product")
        property_obj = char_data.get("property")
        value = char_data.get("value")
        
        if not all([product, property_obj, value]):
            continue
        
        try:
            # Aynan bir xil (product, property, value) kombinatsiyasi borligini tekshiramiz
            existing = ProductCharacteristics.objects.filter(
                product=product,
                property=property_obj,
                value=value
            ).exists()
            
            if not existing:
                # Yangi characteristic yaratamiz (har bir value alohida)
                ProductCharacteristics.objects.create(
                    product=product,
                    property=property_obj,
                    value=value
                )
                created_count += 1
            else:
                skipped_count += 1
                
        except Exception as e:
            continue
    
    return created_count, skipped_count


def import_product_characteristics():
    """Product characteristics import qilish"""
    print("[PRODUCT_LISTS] Starting product characteristics import...")
    try:
        # Product property values olish
        product_property_values = get_product_property_values_from_grist()
        print(f"[PRODUCT_LISTS] Product property values retrieved: {len(product_property_values) if product_property_values else 0}")
        
        if not product_property_values:
            print("[PRODUCT_LISTS] WARNING: No product property values found")
            return {
                "success": False,
                "message": "Product property values не найдены"
            }
        
        # Property values olish
        property_values = get_property_values_from_grist()
        print(f"[PRODUCT_LISTS] Property values retrieved: {len(property_values) if property_values else 0}")
        
        if not property_values:
            print("[PRODUCT_LISTS] WARNING: No property values found")
            return {
                "success": False,
                "message": "Property values не найдены"
            }
        
        # Ma'lumotlarni qayta ishlash
        characteristics_data = process_characteristics_data(
            product_property_values, 
            property_values
        )
        print(f"[PRODUCT_LISTS] Processed characteristics data: {len(characteristics_data)}")
        
        if not characteristics_data:
            print("[PRODUCT_LISTS] WARNING: Failed to process characteristics data")
            return {
                "success": False,
                "message": "Не удалось обработать данные характеристик"
            }
        
        # Saqlash
        created_count, skipped_count = save_product_characteristics(characteristics_data)
        print(f"[PRODUCT_LISTS] Characteristics import completed! Created: {created_count}, Skipped: {skipped_count}")
        
        return {
            "success": True,
            "message": "Характеристики продуктов импортированы успешно",
            "created": created_count,
            "skipped": skipped_count,
            "total_processed": created_count + skipped_count,
            "total_from_grist": len(product_property_values),
            "total_to_save": len(characteristics_data)
        }
        
    except Exception as e:
        print(f"[PRODUCT_LISTS] ERROR in import_product_characteristics: {str(e)}")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def download_image(attachment_id, timeout=30):
    """Bitta rasmni yuklab olish"""
    try:
        url = f"https://isell.getgrist.com/api/docs/{DOC_ID}/attachments/{attachment_id}/download"
        response = requests.get(url, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            return {
                "success": True,
                "content": response.content,
                "attachment_id": attachment_id
            }
        return None
        
    except Exception as e:
        return None


def extract_picture_ids_from_variations(variations_data):
    """Variations dan rasm ID larini olish va product bo'yicha guruhlash"""
    products_pictures = {}
    
    for fields in variations_data:
        picture = fields.get("picture")
        variation_name = fields.get("name", "")
        product_name = fields.get("product_name")
        variation_id = fields.get("variation_record_id")  # Yangi field
        
        if not picture or not isinstance(picture, list) or len(picture) < 2:
            continue
        
        if not product_name or not variation_id:
            continue
        
        attachment_id = picture[1]
        
        # Product ni topish
        try:
            product_id_obj = ProductIDs.objects.filter(
                variation_id=str(variation_id),
                product__name=product_name
            ).select_related('product').first()
            
            if not product_id_obj:
                continue
            
            product = product_id_obj.product
            
            # NEW variantlari uchun guruhlash
            if "NEW" in variation_name.upper():
                if product.id not in products_pictures:
                    products_pictures[product.id] = {
                        "product": product,
                        "attachment_ids": set()
                    }
                products_pictures[product.id]["attachment_ids"].add(attachment_id)
            
        except Exception as e:
            continue
    
    return products_pictures


def save_images_bulk(products_pictures, downloaded_images):
    """Rasmlarni bulk save qilish"""
    created_count = 0
    skipped_count = 0
    
    # Downloaded images ni dict ga aylantirish
    images_dict = {img["attachment_id"]: img["content"] for img in downloaded_images if img}
    
    # Har bir product uchun
    for product_id, data in products_pictures.items():
        product = data["product"]
        attachment_ids = data["attachment_ids"]
        
        # Mavjud rasmlar IDlarini olish (agar picture_id field bo'lsa)
        existing_images = set(
            ProductImages.objects.filter(product=product).values_list('id', flat=True)
        )
        
        images_to_create = []
        
        for attachment_id in attachment_ids:
            if attachment_id not in images_dict:
                skipped_count += 1
                continue
            
            image_content = images_dict[attachment_id]
            
            # Image faylini yaratish
            image_file = ContentFile(image_content)
            
            # ProductImages obyektini yaratish (hali saqlamasdan)
            product_image = ProductImages(product=product)
            product_image.image.save(
                f"product_{product.id}_{attachment_id}.jpg",
                image_file,
                save=True
            )
            created_count += 1
    
    return created_count, skipped_count


def import_product_images():
    """Product rasmlarini import qilish (tez va samarali)"""
    print("[PRODUCT_LISTS] Starting product images import...")
    try:
        # Variations olish (ID bilan)
        variations = get_product_variations_for_images()
        print(f"[PRODUCT_LISTS] Variations for images retrieved: {len(variations) if variations else 0}")
        
        if not variations:
            print("[PRODUCT_LISTS] WARNING: No variations found for images")
            return {
                "success": False,
                "message": "Вариации не найдены"
            }
        
        # Picture ID larini olish va guruhlash
        products_pictures = extract_picture_ids_from_variations(variations)
        print(f"[PRODUCT_LISTS] Products with pictures: {len(products_pictures)}")
        
        if not products_pictures:
            print("[PRODUCT_LISTS] WARNING: No images found in variations")
            return {
                "success": False,
                "message": "Изображения не найдены в вариациях"
            }
        
        # Barcha unique attachment ID larini yig'ish
        all_attachment_ids = set()
        for data in products_pictures.values():
            all_attachment_ids.update(data["attachment_ids"])
        print(f"[PRODUCT_LISTS] Total unique attachment IDs: {len(all_attachment_ids)}")
        
        # Rasmlarni parallel yuklab olish (10 ta bir vaqtda)
        print("[PRODUCT_LISTS] Downloading images in parallel (10 workers)...")
        downloaded_images = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_id = {
                executor.submit(download_image, att_id): att_id 
                for att_id in all_attachment_ids
            }
            
            completed = 0
            for future in as_completed(future_to_id):
                result = future.result()
                if result and result["success"]:
                    downloaded_images.append(result)
                completed += 1
                if completed % 10 == 0:
                    print(f"[PRODUCT_LISTS] Downloaded {completed}/{len(all_attachment_ids)} images...")
        
        print(f"[PRODUCT_LISTS] Total images downloaded: {len(downloaded_images)}")
        
        if not downloaded_images:
            print("[PRODUCT_LISTS] ERROR: Failed to download any images")
            return {
                "success": False,
                "message": "Не удалось загрузить изображения"
            }
        
        # Rasmlarni saqlash
        print("[PRODUCT_LISTS] Saving images to database...")
        created_count, skipped_count = save_images_bulk(products_pictures, downloaded_images)
        print(f"[PRODUCT_LISTS] Images import completed! Created: {created_count}, Skipped: {skipped_count}")
        
        return {
            "success": True,
            "message": "Изображения продуктов импортированы успешно",
            "created": created_count,
            "skipped": skipped_count,
            "total_downloaded": len(downloaded_images),
            "total_products": len(products_pictures)
        }
        
    except Exception as e:
        print(f"[PRODUCT_LISTS] ERROR in import_product_images: {str(e)}")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


