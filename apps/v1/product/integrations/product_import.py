import requests
import os
import asyncio
import aiohttp
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.files.base import ContentFile
from django.db import transaction

from apps.v1.product.models import Categories, Products, ProductIDs, ProductDetails, ProductProperties, ProductCharacteristics, ProductImages

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

def debug_print(*args, **kwargs):
    """Debug uchun print funksiyasi"""
    print(*args, **kwargs)

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

ISell_PRODUCT_VARIATIONS = os.getenv('ISell_PRODUCT_VARIATIONS')
Isell_PRODUCT_PRICE = os.getenv('ISell_PRODUCT_PRICE')

ISell_PROPERTY = os.getenv('ISell_PROPERTY')
ISell_PROPERTY_VALUE = os.getenv('ISell_PROPERTY_VALUE')
ISell_PRODUCT_PROPERTY_VALUE = os.getenv('ISell_PRODUCT_PROPERTY_VALUE')

ISell_PRICE_CATEGORY = os.getenv('ISell_PRICE_CATEGORY')
ISell_PRODUCTS = os.getenv('ISell_PRODUCTS')

def get_url(table_name):
    return f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{table_name}/records"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


async def fetch_api_data_async(session, url):
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                return None
    except Exception:
        return None


def get_product_price_data():
    try:
        if not Isell_PRODUCT_PRICE:
            return None
        
        url = get_url(Isell_PRODUCT_PRICE)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return None
        
        records = data.get("records", [])
        return records
        
    except Exception:
        return None


def filter_actual_products(records):
    """Bu funksiya endi ishlatilmaydi, lekin eski kod bilan mosligi uchun qoldirilgan"""
    return records if records else []


def get_or_create_category(category_name):
    if not category_name:
        return None
    
    try:
        category, created = Categories.objects.get_or_create(
            name=category_name,
            defaults={'name': category_name}
        )
        return category
    except Exception:
        return None


def is_bu_product(variation_name):
    if not variation_name:
        return False
    return "B/U" in str(variation_name).upper()


def is_new_product(variation_name):
    if not variation_name:
        return False
    return "NEW" in str(variation_name).upper()


def process_products(all_products):
    grouped_products = {}
    
    for record in all_products:
        fields = record.get("fields", {})
        record_id = record.get("id")
        
        product_name = fields.get("product_name", "").strip()
        category_name = fields.get("category_name", "").strip()
        variation_name_raw = fields.get("variation_name", "")
        variation_name = variation_name_raw.strip() if variation_name_raw else ""
        variation_id = fields.get("variation_id")
        price = fields.get("price")
        actual = fields.get("actual", False)
        
        if not product_name:
            continue
        
        if is_bu_product(variation_name):
            key = f"{product_name}_B/U_{variation_name}_{record_id}"
            grouped_products[key] = {
                "product_name": f"{product_name} ({variation_name})",
                "category_name": category_name,
                "price": None,
                "variations": [{
                    "id": record_id,
                    "variation_name": variation_name,
                    "variation_id": variation_id,
                    "price": price,
                    "actual": actual
                }],
                "is_bu": True
            }
        
        elif is_new_product(variation_name) or not variation_name:
            key = product_name
            if key not in grouped_products:
                grouped_products[key] = {
                    "product_name": product_name,
                    "category_name": category_name,
                    "price": None,
                    "variations": [],
                    "is_bu": False,
                    "is_actual": False
                }
            
            if record_id:
                existing_variation = None
                for v in grouped_products[key]["variations"]:
                    if v.get("id") == record_id:
                        existing_variation = v
                        break
                
                if existing_variation:
                    existing_variation["variation_name"] = variation_name or ""
                    existing_variation["variation_id"] = variation_id
                    existing_variation["price"] = price
                    existing_variation["actual"] = actual
                else:
                    grouped_products[key]["variations"].append({
                        "id": record_id,
                        "variation_name": variation_name or "",
                        "variation_id": variation_id,
                        "price": price,
                        "actual": actual
                    })
            
            if not variation_name:
                if actual:
                    grouped_products[key]["is_actual"] = True
                    if price:
                        grouped_products[key]["price"] = price
                elif not grouped_products[key]["is_actual"]:
                    grouped_products[key]["is_actual"] = False
    
    return grouped_products


@transaction.atomic
def save_products_to_db(grouped_products):
    created_count = 0
    updated_count = 0
    skipped_count = 0
    product_ids_count = 0
    product_ids_updated_count = 0
    
    for key, product_data in grouped_products.items():
        try:
            product_name = product_data.get("product_name")
            category_name = product_data.get("category_name")
            price = product_data.get("price")
            variations = product_data.get("variations", [])
            is_bu = product_data.get("is_bu", False)
            is_actual = product_data.get("is_actual", False)
            
            if not product_name:
                skipped_count += 1
                continue
            
            category = get_or_create_category(category_name)
            if not category:
                skipped_count += 1
                continue
            
            has_real_variations = any(v.get("variation_name", "").strip() for v in variations)
            
            if not has_real_variations:
                if is_bu:
                    product, created = Products.objects.get_or_create(
                        name=product_name,
                        category=category,
                        defaults={
                            "name": product_name,
                            "category": category,
                            "price": None,
                            "actual": True,
                            "is_actual": is_actual
                        }
                    )
                else:
                    product, created = Products.objects.get_or_create(
                        name=product_name,
                        category=category,
                        defaults={
                            "name": product_name,
                            "category": category,
                            "price": price,
                            "actual": True,
                            "is_actual": is_actual
                        }
                    )
                
                if created:
                    created_count += 1
                else:
                    updated = False
                    if product.price != price and price is not None:
                        product.price = price
                        updated = True
                    if product.is_actual != is_actual:
                        product.is_actual = is_actual
                        updated = True
                    if updated:
                        product.save()
                        updated_count += 1
            
            else:
                product, created = Products.objects.get_or_create(
                    name=product_name,
                    category=category,
                    defaults={
                        "name": product_name,
                        "category": category,
                        "price": None,
                        "actual": True,
                        "is_actual": False
                    }
                )
                
                if created:
                    created_count += 1
                elif product.is_actual != False:
                    product.is_actual = False
                    product.save()
                    updated_count += 1
            
            for variation in variations:
                variation_name = variation.get("variation_name", "")
                variation_id = variation.get("variation_id")
                grist_id = variation.get("id")
                variation_actual = variation.get("actual", False)
                
                if grist_id:
                    try:
                        product_id_obj, pid_created = ProductIDs.objects.get_or_create(
                            product=product,
                            grist_product_id=str(grist_id),
                            defaults={
                                "product": product,
                                "grist_product_id": str(grist_id),
                                "variation_name": variation_name or "",
                                "variation_id": str(variation_id) if variation_id else "",
                                "is_actual": variation_actual
                            }
                        )
                        
                        if pid_created:
                            product_ids_count += 1
                        else:
                            updated = False
                            if product_id_obj.variation_name != (variation_name or ""):
                                product_id_obj.variation_name = variation_name or ""
                                updated = True
                            if product_id_obj.variation_id != (str(variation_id) if variation_id else ""):
                                product_id_obj.variation_id = str(variation_id) if variation_id else ""
                                updated = True
                            if product_id_obj.is_actual != variation_actual:
                                product_id_obj.is_actual = variation_actual
                                updated = True
                            if updated:
                                product_id_obj.save()
                                product_ids_updated_count += 1
                    except Exception as e:
                        logger.error(f"Error saving ProductIDs for grist_id {grist_id}, product: {product_name}: {str(e)}", exc_info=True)
                        pass
        
        except Exception as e:
            logger.error(f"Error processing product {key}: {str(e)}", exc_info=True)
            skipped_count += 1
            continue
    
    return created_count, updated_count, skipped_count, product_ids_count, product_ids_updated_count


def import_products_from_price():
    try:
        records = get_product_price_data()
        if not records:
            return {
                "success": False,
                "message": "API'dan ma'lumotlar olinmadi"
            }
        
        all_products = records
        if not all_products:
            return {
                "success": False,
                "message": "Productlar topilmadi"
            }
        
        grouped_products = process_products(all_products)
        if not grouped_products:
            return {
                "success": False,
                "message": "Productlar guruhlanmadi"
            }
        
        created_count, updated_count, skipped_count, product_ids_count, product_ids_updated_count = save_products_to_db(grouped_products)
        
        return {
            "success": True,
            "message": "Productlar muvaffaqiyatli import qilindi",
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "product_ids_saved": product_ids_count,
            "product_ids_updated": product_ids_updated_count,
            "total_processed": created_count + updated_count + skipped_count
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def get_product_variations():
    try:
        if not ISell_PRODUCT_VARIATIONS:
            return None
        
        url = get_url(ISell_PRODUCT_VARIATIONS)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return None
        
        records = data.get("records", [])
        return records
        
    except Exception:
        return None


def get_price_for_variation(product_id, variation_id):
    try:
        if not Isell_PRODUCT_PRICE:
            return None
        
        url = get_url(Isell_PRODUCT_PRICE)
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None
        
        records = response.json().get("records", [])
        
        for record in records:
            fields = record.get("fields", {})
            record_product_id = fields.get("product_id")
            record_variation_id = fields.get("variation_id")
            actual = fields.get("actual", False)
            
            try:
                record_variation_id_int = int(record_variation_id) if record_variation_id is not None else None
                variation_id_int = int(variation_id) if variation_id is not None else None
                
                if (actual and 
                    record_product_id == product_id and 
                    record_variation_id_int == variation_id_int):
                    price = fields.get("price")
                    return price
            except (ValueError, TypeError):
                continue
        
        return None
        
    except Exception:
        return None


async def download_attachment_image_async(session, attachment_id):
    try:
        if not attachment_id:
            return None
        
        url = f"https://isell.getgrist.com/api/docs/{DOC_ID}/attachments/{attachment_id}/download"
        
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.read()
            else:
                return None
        
    except Exception:
        return None


def download_attachment_image(attachment_id):
    try:
        if not attachment_id:
            return None
        
        async def download():
            async with aiohttp.ClientSession() as session:
                return await download_attachment_image_async(session, attachment_id)
        
        return asyncio.run(download())
        
    except Exception:
        return None


def download_attachment_images_parallel(attachment_ids, max_workers=10):
    results = {}
    
    def download_single(attachment_id):
        return attachment_id, download_attachment_image(attachment_id)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_single, aid): aid for aid in attachment_ids}
        
        for future in as_completed(futures):
            attachment_id, content = future.result()
            if content:
                results[attachment_id] = content
    
    return results


def extract_picture_ids(picture_field):
    if not picture_field or not isinstance(picture_field, list):
        return []
    
    if len(picture_field) > 1 and picture_field[0] == "L":
        return [item for item in picture_field[1:] if isinstance(item, (int, str))]
    
    return []


def find_product_by_grist_id(product_id):
    try:
        if not Isell_PRODUCT_PRICE:
            return None
        
        url = get_url(Isell_PRODUCT_PRICE)
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None
        
        records = response.json().get("records", [])
        
        matching_record_id = None
        for record in records:
            fields = record.get("fields", {})
            record_product_id = fields.get("product_id")
            actual = fields.get("actual", False)
            
            if actual and record_product_id == product_id:
                matching_record_id = record.get("id")
                break
        
        if not matching_record_id:
            return None
        
        product_id_obj = ProductIDs.objects.filter(grist_product_id=str(matching_record_id)).first()
        
        if product_id_obj:
            return product_id_obj.product
        
        return None
        
    except Exception:
        return None


def process_variations_for_products(variations_records):
    processed_variations = {}
    
    price_grist_id_cache = {}
    price_data_cache = {}
    if Isell_PRODUCT_PRICE:
        try:
            url = get_url(Isell_PRODUCT_PRICE)
            async def fetch_price_data():
                async with aiohttp.ClientSession() as session:
                    data = await fetch_api_data_async(session, url)
                    return data
            
            data = asyncio.run(fetch_price_data())
            
            if data:
                records = data.get("records", [])
                for record in records:
                    fields = record.get("fields", {})
                    record_product_id = fields.get("product_id")
                    record_variation_id = fields.get("variation_id", 0)
                    variation_name_from_price = fields.get("variation_name", "").strip()
                    actual = fields.get("actual", False)
                    price_value = fields.get("price")
                    if record_product_id is not None:
                        record_id = record.get("id")
                        cache_key = (record_product_id, variation_name_from_price)
                        if cache_key not in price_grist_id_cache:
                            price_grist_id_cache[cache_key] = record_id
                        price_cache_key = (record_product_id, record_variation_id)
                        if price_cache_key not in price_data_cache:
                            price_data_cache[price_cache_key] = price_value
        except Exception:
            pass
    
    for record in variations_records:
        fields = record.get("fields", {})
        record_id = record.get("id")
        
        product_id = fields.get("product_id")
        variation_name = fields.get("name", "").strip()
        color = fields.get("color", "").strip()
        storage = fields.get("storage", "").strip()
        sim = fields.get("sim", "").strip()
        battery_capacity = fields.get("battery_capacity")
        picture = fields.get("picture", [])
        sale_price = fields.get("sale_price")
        
        if not product_id:
            continue
        
        matching_product_id_obj = None
        
        if variation_name:
            grist_product_id = price_grist_id_cache.get((product_id, variation_name))
            
            if grist_product_id:
                matching_product_id_obj = ProductIDs.objects.filter(
                    grist_product_id=str(grist_product_id),
                    variation_name=variation_name
                ).first()
            else:
                matching_product_id_obj = ProductIDs.objects.filter(variation_name=variation_name).first()
        else:
            continue
        
        if not matching_product_id_obj:
            continue
        
        if not matching_product_id_obj.is_actual:
            continue
        
        product = matching_product_id_obj.product
        variation_id = matching_product_id_obj.variation_id
        
        if variation_id in ["", "0", 0]:
            variation_id = None
        
        price = None
        if product_id and variation_id:
            try:
                variation_id_int = int(variation_id) if variation_id else None
                if variation_id_int:
                    price = price_data_cache.get((product_id, variation_id_int))
                    if price is None:
                        price = get_price_for_variation(product_id, variation_id_int)
            except (ValueError, TypeError):
                pass
        
        if not price and sale_price:
            price = sale_price
        
        picture_ids = extract_picture_ids(picture)
        
        key = f"{product.id}_{color}_{storage}_{sim}"
        
        if key not in processed_variations:
            processed_variations[key] = {
                "product": product,
                "product_id": product_id,
                "variation_id": variation_id,
                "color": color,
                "storage": storage,
                "sim": sim,
                "battery_capacity": str(battery_capacity) if battery_capacity else "",
                "price": price,
                "picture_ids": picture_ids,
                "variation_name": variation_name
            }
        else:
            processed_variations[key]["picture_ids"].extend(picture_ids)
    
    return processed_variations


@transaction.atomic
def save_product_details(processed_variations):
    details_created = 0
    details_skipped = 0
    images_created = 0
    
    for key, variation_data in processed_variations.items():
        try:
            product = variation_data.get("product")
            color = variation_data.get("color", "")
            storage = variation_data.get("storage", "")
            sim = variation_data.get("sim", "")
            battery_capacity = variation_data.get("battery_capacity", "")
            price = variation_data.get("price")
            picture_ids = variation_data.get("picture_ids", [])
            
            product_detail, detail_created = ProductDetails.objects.get_or_create(
                product=product,
                color=color,
                storage=storage,
                sim=sim,
                defaults={
                    "product": product,
                    "color": color,
                    "storage": storage,
                    "sim": sim,
                    "battery_capacity": battery_capacity,
                    "price": price
                }
            )
            
            if not detail_created:
                updated = False
                if price is not None and product_detail.price != price:
                    product_detail.price = price
                    updated = True
                if battery_capacity and product_detail.battery_capacity != battery_capacity:
                    product_detail.battery_capacity = battery_capacity
                    updated = True
                if updated:
                    product_detail.save()
            
            if detail_created:
                details_created += 1
            else:
                details_skipped += 1
            
            if picture_ids:
                downloaded_images = download_attachment_images_parallel(picture_ids, max_workers=10)
                
                for picture_id in picture_ids:
                    try:
                        existing_image = ProductImages.objects.filter(
                            product_details=product_detail,
                            image__icontains=f"img_{picture_id}"
                        ).first()
                        
                        if existing_image:
                            continue
                        
                        image_content = downloaded_images.get(picture_id)
                        
                        if image_content:
                            file_name = f"product_{product.id}_detail_{product_detail.id}_img_{picture_id}.jpg"
                            
                            product_image = ProductImages.objects.create(
                                product_details=product_detail
                            )
                            
                            product_image.image.save(
                                file_name,
                                ContentFile(image_content),
                                save=True
                            )
                            images_created += 1
                        
                    except Exception:
                        continue
        
        except Exception:
            details_skipped += 1
            continue
    
    return details_created, details_skipped, images_created


@transaction.atomic
def import_product_main_images_from_products_table():
    """
    ISell_PRODUCTS jadvalidagi picture maydonidan
    variatsiyasiz tovarlar uchun asosiy rasmni (Products.image)
    yuklab oladi va saqlaydi.
    """
    if not ISell_PRODUCTS:
        logger.warning("ISell_PRODUCTS environment variable not set")
        return {
            "success": False,
            "message": "ISell_PRODUCTS environment variable not set"
        }

    try:
        logger.info("🖼️ ISell_PRODUCTS jadvalidan asosiy rasmlarni olish boshlandi")
        url = get_url(ISell_PRODUCTS)

        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data

        data = asyncio.run(fetch())

        if not data:
            logger.warning("❌ ISell_PRODUCTS API'dan ma'lumotlar olinmadi")
            return {
                "success": False,
                "message": "API'dan ma'lumotlar olinmadi"
            }

        records = data.get("records", [])
        if not records:
            logger.warning("❌ ISell_PRODUCTS jadvalida records topilmadi")
            return {
                "success": False,
                "message": "Products topilmadi"
            }

        logger.info(f"📦 ISell_PRODUCTS jadvalida {len(records)} ta record topildi")

        # category_id -> category_name mapping yaratish (Isell_PRODUCT_PRICE jadvalidan)
        category_id_to_name = {}
        if Isell_PRODUCT_PRICE:
            try:
                price_url = get_url(Isell_PRODUCT_PRICE)
                async def fetch_price():
                    async with aiohttp.ClientSession() as session:
                        return await fetch_api_data_async(session, price_url)
                price_data = asyncio.run(fetch_price())
                if price_data:
                    price_records = price_data.get("records", [])
                    for price_record in price_records:
                        price_fields = price_record.get("fields", {})
                        cat_id = price_fields.get("category_id")
                        cat_name = (price_fields.get("category_name") or "").strip()
                        if cat_id and cat_name:
                            category_id_to_name[cat_id] = cat_name
            except Exception as e:
                logger.warning(f"⚠️ Error fetching category mapping: {str(e)}")

        updated_count = 0
        skipped_count = 0
        skipped_reasons = {
            "no_product_name_or_category": 0,
            "no_picture_ids": 0,
            "no_category": 0,
            "product_not_found": 0,
            "has_variations": 0,
            "already_has_image": 0,
            "image_download_failed": 0
        }

        for record in records:
            fields = record.get("fields", {})
            
            # ISell_PRODUCTS jadvalida: name, category_id, picture, with_variations
            product_name = (fields.get("name") or "").strip()
            category_id = fields.get("category_id")
            picture = fields.get("picture", [])
            with_variations = fields.get("with_variations", False)

            # Majburiy ma'lumotlar bo'lmasa o'tkazib yuboramiz
            if not product_name:
                skipped_count += 1
                skipped_reasons["no_product_name_or_category"] += 1
                continue

            picture_ids = extract_picture_ids(picture)
            
            if not picture_ids:
                skipped_count += 1
                skipped_reasons["no_picture_ids"] += 1
                continue

            # category_id orqali kategoriyani topish (cache dan)
            category_name = None
            if category_id:
                category_name = category_id_to_name.get(category_id)

            # Agar category_name topilmasa, barcha productlarni nom bo'yicha qidirish
            if not category_name:
                # Nom bo'yicha qidirish (category ni hisobga olmasdan)
                product = Products.objects.filter(name=product_name).first()
            else:
                # Lokal kategoriyani topamiz / yaratamiz
                category = get_or_create_category(category_name)
                if not category:
                    skipped_count += 1
                    skipped_reasons["no_category"] += 1
                    continue
                
                # Shu nom ва категория бўйича Products ни топамиз
                product = Products.objects.filter(
                    name=product_name,
                    category=category
                ).first()

            if not product:
                skipped_count += 1
                skipped_reasons["product_not_found"] += 1
                continue

            # with_variations maydoni va ProductIDs orqali tekshirish
            # Agar with_variations=True bo'lsa yoki ProductIDs da variation_name bor bo'lsa, skip qilamiz
            has_variations = with_variations or ProductIDs.objects.filter(
                product=product,
                variation_name__isnull=False
            ).exclude(variation_name="").exists()

            if has_variations:
                skipped_count += 1
                skipped_reasons["has_variations"] += 1
                continue

            # Агар allaqachon asosiy rasm bo'lsa, o'tkazib yuboramiz
            if product.image:
                skipped_count += 1
                skipped_reasons["already_has_image"] += 1
                continue

            # Faqat birinchi rasmdan foydalanamiz
            first_picture_id = picture_ids[0]
            image_content = download_attachment_image(first_picture_id)

            if not image_content:
                skipped_count += 1
                skipped_reasons["image_download_failed"] += 1
                continue

            file_name = f"product_{product.id}_img_{first_picture_id}.jpg"
            product.image.save(
                file_name,
                ContentFile(image_content),
                save=True
            )
            updated_count += 1

        logger.info(f"✅ Asosiy rasmlar import qilindi: Updated={updated_count}, Skipped={skipped_count}")
        if skipped_count > 0:
            logger.info(f"📊 Skipped reasons:")
            for reason, count in skipped_reasons.items():
                if count > 0:
                    logger.info(f"   - {reason}: {count}")

        return {
            "success": True,
            "message": "Asosiy rasmlar muvaffaqiyatli import qilindi",
            "updated": updated_count,
            "skipped": skipped_count,
            "skipped_reasons": skipped_reasons,
            "total_processed": updated_count + skipped_count
        }

    except Exception as e:
        logger.error(f"❌ Error in import_product_main_images_from_products_table: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def import_product_details():
    try:
        variations_records = get_product_variations()
        if not variations_records:
            return {
                "success": False,
                "message": "Variations ma'lumotlari olinmadi"
            }
        
        processed_variations = process_variations_for_products(variations_records)
        if not processed_variations:
            return {
                "success": False,
                "message": "Variations moslashtirilmadi"
            }
        
        details_created, details_skipped, images_created = save_product_details(processed_variations)
        
        return {
            "success": True,
            "message": "Product details muvaffaqiyatli import qilindi",
            "details_created": details_created,
            "details_skipped": details_skipped,
            "images_created": images_created,
            "total_processed": details_created + details_skipped
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


@transaction.atomic
def cleanup_removed_products():
    """
    Grist bazasida yo'q bo'lgan Products va ProductIDs ni o'chirish
    Endi actual=False bo'lganlar ham saqlanadi, faqat Gristda yo'q bo'lganlar o'chiladi
    Returns: (products_deleted, product_ids_deleted)
    """
    products_deleted = 0
    product_ids_deleted = 0
    
    try:
        if not Isell_PRODUCT_PRICE:
            return products_deleted, product_ids_deleted
        
        url = get_url(Isell_PRODUCT_PRICE)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return products_deleted, product_ids_deleted
        
        records = data.get("records", [])
        
        all_grist_ids = set()
        for record in records:
            record_id = record.get("id")
            if record_id:
                all_grist_ids.add(str(record_id))
        
        all_product_ids = ProductIDs.objects.all()
        for product_id_obj in all_product_ids:
            grist_id = product_id_obj.grist_product_id
            if grist_id and grist_id not in all_grist_ids:
                product = product_id_obj.product
                product_id_obj.delete()
                product_ids_deleted += 1
                
                remaining_product_ids = ProductIDs.objects.filter(product=product).count()
                if remaining_product_ids == 0:
                    ProductDetails.objects.filter(product=product).delete()
                    product.delete()
                    products_deleted += 1
        
        return products_deleted, product_ids_deleted
        
    except Exception:
        return products_deleted, product_ids_deleted


@transaction.atomic
def cleanup_removed_product_details():
    """
    Grist bazasida yo'q bo'lgan ProductDetails va ProductImages ni o'chirish
    Returns: (details_deleted, images_deleted)
    """
    details_deleted = 0
    images_deleted = 0
    
    try:
        if not ISell_PRODUCT_VARIATIONS:
            return details_deleted, images_deleted
        
        url = get_url(ISell_PRODUCT_VARIATIONS)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return details_deleted, images_deleted
        
        records = data.get("records", [])
        
        existing_variations = set()
        for record in records:
            fields = record.get("fields", {})
            variation_name = fields.get("name", "").strip()
            if variation_name:
                existing_variations.add(variation_name)
        
        all_product_ids = ProductIDs.objects.select_related('product').all()
        valid_products = set()
        for product_id_obj in all_product_ids:
            if product_id_obj.variation_name in existing_variations:
                valid_products.add(product_id_obj.product.id)
        
        all_product_details = ProductDetails.objects.select_related('product').all()
        for product_detail in all_product_details:
            product = product_detail.product
            product_has_valid_variation = product.id in valid_products
            
            if not product_has_valid_variation:
                images_count = ProductImages.objects.filter(product_details=product_detail).count()
                ProductImages.objects.filter(product_details=product_detail).delete()
                images_deleted += images_count
                product_detail.delete()
                details_deleted += 1
        
        return details_deleted, images_deleted
        
    except Exception:
        return details_deleted, images_deleted


@transaction.atomic
def cleanup_removed_characteristics():
    """
    Grist bazasida yo'q bo'lgan ProductCharacteristics ni o'chirish
    Returns: characteristics_deleted
    """
    characteristics_deleted = 0
    
    try:
        if not ISell_PRODUCT_PROPERTY_VALUE or not ISell_PROPERTY_VALUE:
            return characteristics_deleted
        
        async def fetch_all():
            async with aiohttp.ClientSession() as session:
                url1 = get_url(ISell_PRODUCT_PROPERTY_VALUE)
                url2 = get_url(ISell_PROPERTY_VALUE)
                
                task1 = fetch_api_data_async(session, url1)
                task2 = fetch_api_data_async(session, url2)
                
                product_property_values_data, property_values_data = await asyncio.gather(task1, task2)
                
                return product_property_values_data, property_values_data
        
        product_property_values_data, property_values_data = asyncio.run(fetch_all())
        
        if not product_property_values_data or not property_values_data:
            return characteristics_deleted
        
        product_property_values = product_property_values_data.get("records", [])
        property_values = property_values_data.get("records", [])
        
        valid_characteristics = set()
        property_values_dict = {}
        
        for record in property_values:
            value_id = record.get("id")
            fields = record.get("fields", {})
            property_id = fields.get("property_id")
            if value_id and property_id:
                property_values_dict[value_id] = {
                    "property_id": property_id,
                    "value": fields.get("value")
                }
        
        for record in product_property_values:
            fields = record.get("fields", {})
            product_name = fields.get("product_name")
            variation_id = fields.get("variation_id")
            value_id = fields.get("value_id")
            property_id = fields.get("property_id")
            
            if not all([variation_id, value_id, property_id]):
                continue
            
            try:
                product_id_obj = ProductIDs.objects.filter(
                    product__name=product_name,
                    variation_id=str(variation_id)
                ).first()
                
                if not product_id_obj:
                    continue
                
                product = product_id_obj.product
                
                if value_id in property_values_dict:
                    prop_value_data = property_values_dict[value_id]
                    if prop_value_data["property_id"] == property_id:
                        value = prop_value_data["value"]
                        property_obj = ProductProperties.objects.filter(
                            grist_property_id=str(property_id)
                        ).first()
                        
                        if property_obj:
                            valid_characteristics.add((product.id, product_id_obj.id, property_obj.id, value))
            except Exception:
                continue
        
        all_characteristics = ProductCharacteristics.objects.select_related('product', 'product_ids', 'property').all()
        for char in all_characteristics:
            product_ids_id = char.product_ids.id if char.product_ids else None
            key = (char.product.id, product_ids_id, char.property.id, char.value_name)
            if key not in valid_characteristics:
                char.delete()
                characteristics_deleted += 1
        
        return characteristics_deleted
        
    except Exception:
        return characteristics_deleted


@transaction.atomic
def import_product_price_categories():
    """
    Price category ma'lumotlarini import qiladi.
    Ma'lumotlar 3 ta API'dan olinadi:
    1. ISell_PRODUCTS - productlar ro'yxati (price_category_id bilan)
    2. ISell_PRICE_CATEGORY - price category nomlari
    3. Isell_PRODUCT_PRICE - product_id va grist_id mapping
    """
    try:
        if not ISell_PRODUCTS or not ISell_PRICE_CATEGORY or not Isell_PRODUCT_PRICE:
            return {
                "success": False,
                "message": "Environment variables not set"
            }
        
        async def fetch_all():
            async with aiohttp.ClientSession() as session:
                url1 = get_url(ISell_PRODUCTS)
                url2 = get_url(ISell_PRICE_CATEGORY)
                url3 = get_url(Isell_PRODUCT_PRICE)
                
                task1 = fetch_api_data_async(session, url1)
                task2 = fetch_api_data_async(session, url2)
                task3 = fetch_api_data_async(session, url3)
                
                products_data, price_categories_data, price_data = await asyncio.gather(task1, task2, task3)
                
                return products_data, price_categories_data, price_data
        
        products_data, price_categories_data, price_data = asyncio.run(fetch_all())
        
        if not products_data or not price_categories_data or not price_data:
            return {
                "success": False,
                "message": "API'dan ma'lumotlar olinmadi"
            }
        
        products_records = products_data.get("records", [])
        price_categories_records = price_categories_data.get("records", [])
        price_records = price_data.get("records", [])
        
        if not products_records or not price_categories_records:
            return {
                "success": False,
                "message": "Ma'lumotlar topilmadi"
            }
        
        price_categories_dict = {}
        for record in price_categories_records:
            record_id = record.get("id")
            fields = record.get("fields", {})
            category_value = fields.get("category")
            if record_id and category_value:
                price_categories_dict[str(record_id)] = category_value
        
        updated_count = 0
        skipped_count = 0
        skipped_reasons = {
            "no_product_id": 0,
            "no_price_category_id": 0,
            "no_price_category_value": 0,
            "no_product_id_obj": 0,
            "no_product": 0,
            "exception": 0
        }
        
        for idx, record in enumerate(products_records, 1):
            fields = record.get("fields", {})
            product_id_from_products = record.get("id")
            price_category_id = fields.get("price_category_id")
            
            if not product_id_from_products:
                skipped_count += 1
                skipped_reasons["no_product_id"] += 1
                continue
            
            if not price_category_id:
                skipped_count += 1
                skipped_reasons["no_price_category_id"] += 1
                continue
            
            price_category_value = price_categories_dict.get(str(price_category_id))
            
            if not price_category_value:
                skipped_count += 1
                skipped_reasons["no_price_category_value"] += 1
                continue
            
            try:
                
                grist_product_id = product_id_from_products
                product_id_objs = ProductIDs.objects.filter(grist_product_id=grist_product_id)
                
                if not product_id_objs.exists():
                    skipped_count += 1
                    skipped_reasons["no_product_id_obj"] += 1
                    continue
                
                product_id_obj = product_id_objs.first()
                product = product_id_obj.product
                
                if not product:
                    skipped_count += 1
                    skipped_reasons["no_product"] += 1
                    continue
                
                product.price_category = price_category_value
                product.save()
                updated_count += 1
                
            except Exception as e:
                skipped_count += 1
                skipped_reasons["exception"] += 1
                logger.error(f"Error updating product price category for grist_id {product_id_from_products}: {str(e)}", exc_info=True)
                continue
        
        print(f"✅ Updated: {updated_count}")
        print(f"❌ Skipped: {skipped_count}")
        if skipped_count > 0:
            print(f"📊 Skipped reasons:")
            for reason, count in skipped_reasons.items():
                if count > 0:
                    print(f"   - {reason}: {count}")
        
        return {
            "success": True,
            "message": "Product price categories muvaffaqiyatli import qilindi",
            "updated": updated_count,
            "skipped": skipped_count,
            "skipped_reasons": skipped_reasons,
            "total_processed": updated_count + skipped_count
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def import_all_products():
    """
    Barcha product ma'lumotlarini import qiladi.
    Ketma-ketlik:
    1. import_products_from_price() - Productlar va ProductIDs
    2. import_product_price_categories() - Price categories (Product modeliga qo'shiladi)
    3. import_product_details() - ProductDetails va ProductImages
    4. import_product_properties() - ProductProperties
    5. import_product_characteristics() - ProductCharacteristics
    6. Cleanup funksiyalari
    """
    results = {
        "products": None,
        "product_main_images": None,
        "product_details": None,
        "product_properties": None,
        "product_characteristics": None,
        "price_categories": None,
        "cleanup": None,
        "overall_success": False
    }
    
    try:
        products_result = import_products_from_price()
        results["products"] = products_result
        
        if not products_result.get("success"):
            results["overall_success"] = False
            return results
        
        price_categories_result = import_product_price_categories()
        results["price_categories"] = price_categories_result

        # Variatsiyasiz tovarlar uchun asosiy rasmlarni ISell_PRODUCTS dan olish
        logger.info("🖼️ Asosiy rasmlarni ISell_PRODUCTS jadvalidan olish boshlandi...")
        main_images_result = import_product_main_images_from_products_table()
        results["product_main_images"] = main_images_result
        if main_images_result:
            logger.info(f"📊 Asosiy rasmlar natijasi: {main_images_result.get('message', 'N/A')}")
            logger.info(f"   Updated: {main_images_result.get('updated', 0)}, Skipped: {main_images_result.get('skipped', 0)}")
        
        details_result = import_product_details()
        results["product_details"] = details_result
        
        if not details_result.get("success"):
            results["overall_success"] = True
            return results
        
        properties_result = import_product_properties()
        results["product_properties"] = properties_result
        
        characteristics_result = import_product_characteristics()
        results["product_characteristics"] = characteristics_result
        
        products_deleted, product_ids_deleted = cleanup_removed_products()
        details_deleted, images_deleted = cleanup_removed_product_details()
        characteristics_deleted = cleanup_removed_characteristics()
        
        results["cleanup"] = {
            "products_deleted": products_deleted,
            "product_ids_deleted": product_ids_deleted,
            "details_deleted": details_deleted,
            "images_deleted": images_deleted,
            "characteristics_deleted": characteristics_deleted
        }
        
        results["overall_success"] = True
        return results
        
    except Exception as e:
        results["overall_success"] = False
        return results


@transaction.atomic
def save_product_properties(properties_data):
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
                    "property_name": name,
                    "property_type": property_type
                }
            )
            
            if created:
                created_count += 1
            else:
                updated_count += 1
                
        except Exception:
            continue
    
    return created_count, updated_count


def import_product_properties():
    try:
        if not ISell_PROPERTY:
            return {
                "success": False,
                "message": "ISell_PROPERTY environment variable not set"
            }
        
        url = get_url(ISell_PROPERTY)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return {
                "success": False,
                "message": "API'dan ma'lumotlar olinmadi"
            }
        
        records = data.get("records", [])
        
        if not records:
            return {
                "success": False,
                "message": "Properties topilmadi"
            }
        
        created_count, updated_count = save_product_properties(records)
        
        return {
            "success": True,
            "message": "Product properties muvaffaqiyatli import qilindi",
            "created": created_count,
            "updated": updated_count,
            "total_processed": created_count + updated_count
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def process_characteristics_data(product_property_values, property_values):
    characteristics_to_save = []
    
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
    
    for record in product_property_values:
        fields = record.get("fields", {})
        product_name = fields.get("product_name")
        variation_id = fields.get("variation_id")
        value_id = fields.get("value_id")
        property_id = fields.get("property_id")
        
        if not all([variation_id, value_id, property_id]):
            continue
        
        try:
            if product_name:
                product_id_obj = ProductIDs.objects.filter(
                    product__name=product_name,
                    variation_id=str(variation_id)
                ).first()
            else:
                product_id_obj = ProductIDs.objects.filter(
                    variation_id=str(variation_id)
                ).first()
            
            if not product_id_obj:
                continue
            
            product = product_id_obj.product
            
            if value_id in property_values_dict:
                prop_value_data = property_values_dict[value_id]
                
                if prop_value_data["property_id"] == property_id:
                    value = prop_value_data["value"]
                    
                    property_obj = ProductProperties.objects.filter(
                        grist_property_id=str(property_id)
                    ).first()
                    
                    if property_obj:
                        characteristics_to_save.append({
                            "product": product,
                            "product_ids": product_id_obj,
                            "property": property_obj,
                            "value": value
                        })
                        
        except Exception:
            continue
    
    return characteristics_to_save


@transaction.atomic
def save_product_characteristics(characteristics_data):
    created_count = 0
    skipped_count = 0
    
    for char_data in characteristics_data:
        product = char_data.get("product")
        product_ids = char_data.get("product_ids")
        property_obj = char_data.get("property")
        value = char_data.get("value")
        
        if not all([product, property_obj, value]):
            continue
        
        try:
            existing = ProductCharacteristics.objects.filter(
                product=product,
                product_ids=product_ids,
                property=property_obj,
                value_name=value
            ).exists()
            
            if not existing:
                ProductCharacteristics.objects.create(
                    product=product,
                    product_ids=product_ids,
                    property=property_obj,
                    value_name=value
                )
                created_count += 1
            else:
                skipped_count += 1
                
        except Exception:
            continue
    
    return created_count, skipped_count


def import_product_characteristics():
    try:
        if not ISell_PRODUCT_PROPERTY_VALUE or not ISell_PROPERTY_VALUE:
            return {
                "success": False,
                "message": "Environment variables not set"
            }
        
        async def fetch_all():
            async with aiohttp.ClientSession() as session:
                url1 = get_url(ISell_PRODUCT_PROPERTY_VALUE)
                url2 = get_url(ISell_PROPERTY_VALUE)
                
                task1 = fetch_api_data_async(session, url1)
                task2 = fetch_api_data_async(session, url2)
                
                product_property_values_data, property_values_data = await asyncio.gather(task1, task2)
                
                return product_property_values_data, property_values_data
        
        product_property_values_data, property_values_data = asyncio.run(fetch_all())
        
        if not product_property_values_data or not property_values_data:
            return {
                "success": False,
                "message": "API'dan ma'lumotlar olinmadi"
            }
        
        product_property_values = product_property_values_data.get("records", [])
        property_values = property_values_data.get("records", [])
        
        if not product_property_values or not property_values:
            return {
                "success": False,
                "message": "Ma'lumotlar topilmadi"
            }
        
        characteristics_data = process_characteristics_data(
            product_property_values,
            property_values
        )
        
        if not characteristics_data:
            return {
                "success": False,
                "message": "Characteristics ma'lumotlari qayta ishlanmadi"
            }
        
        created_count, skipped_count = save_product_characteristics(characteristics_data)
        
        return {
            "success": True,
            "message": "Product characteristics muvaffaqiyatli import qilindi",
            "created": created_count,
            "skipped": skipped_count,
            "total_processed": created_count + skipped_count,
            "total_from_grist": len(product_property_values),
            "total_to_save": len(characteristics_data)
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


if __name__ == "__main__":
    import os
    import sys
    import django
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    
    django.setup()
    
    result = import_all_products()
