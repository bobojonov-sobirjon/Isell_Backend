import requests
import os
import asyncio
import aiohttp
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

logger = logging.getLogger(__name__)

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

ISell_TRANSACTIONS = os.getenv('ISell_TRANSACTIONS')
ISell_SALES = os.getenv('ISell_SALES')
ISell_SALES_PRODUCTS = os.getenv('ISell_SALES_PRODUCTS')
ISell_PRODUCT_PRICE = os.getenv('ISell_PRODUCT_PRICE')

def get_url(table_name):
    return f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{table_name}/records"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

async def fetch_api_data_async(session, url):
    """Async function to fetch data from Grist API"""
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data
            else:
                return None
    except Exception as e:
        logger.error(f"[fetch_api_data_async] Exception fetching data from {url}: {str(e)}", exc_info=True)
        return None

def get_transactions_by_counterparty_id(counterparty_id):
    """Get transactions from ISell_TRANSACTIONS filtered by counterparty_id, grouped by sale_id"""
    if not ISell_TRANSACTIONS or not counterparty_id:
        return []
    
    try:
        url = get_url(ISell_TRANSACTIONS)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        records = data.get("records", [])
        sale_ids = set()
        
        for record in records:
            fields = record.get("fields", {})
            record_counterparty_id = fields.get("counterpart_id") or fields.get("counterparty_id")
            sale_id = fields.get("sale_id")
            
            if record_counterparty_id is not None:
                try:
                    if int(record_counterparty_id) == int(counterparty_id) and sale_id:
                        sale_ids.add(sale_id)
                except (ValueError, TypeError):
                    pass
        
        return list(sale_ids)
        
    except Exception as e:
        logger.error(f"[get_transactions_by_counterparty_id] Exception for counterparty_id {counterparty_id}: {str(e)}", exc_info=True)
        return []

def get_sales_directly_by_counterparty_id(counterparty_id):
    """Get sales directly from ISell_SALES filtered by counterparty_id"""
    if not ISell_SALES or not counterparty_id:
        return []
    
    try:
        url = get_url(ISell_SALES)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        records = data.get("records", [])
        filtered_sales = []
        
        for record in records:
            fields = record.get("fields", {})
            record_counterparty_id = fields.get("counterpart_id") or fields.get("counterparty_id")
            
            try:
                if record_counterparty_id is not None and int(record_counterparty_id) == int(counterparty_id):
                    filtered_sales.append(record)
            except (ValueError, TypeError):
                pass
        
        return filtered_sales
        
    except Exception as e:
        logger.error(f"[get_sales_directly_by_counterparty_id] Exception: {str(e)}", exc_info=True)
        return []


def get_sales_by_sale_ids_and_counterparty(sale_ids, counterparty_id):
    """Get sales from ISell_SALES filtered by sale_ids and counterparty_id"""
    if not ISell_SALES or not sale_ids or not counterparty_id:
        return []
    
    try:
        url = get_url(ISell_SALES)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        records = data.get("records", [])
        sale_ids_set = set(sale_ids)
        filtered_sales = []
        
        for record in records:
            record_id = record.get("id")
            fields = record.get("fields", {})
            record_counterparty_id = fields.get("counterpart_id") or fields.get("counterparty_id")
            
            try:
                if record_id in sale_ids_set and int(record_counterparty_id) == int(counterparty_id):
                    filtered_sales.append(record)
            except (ValueError, TypeError):
                pass
        
        return filtered_sales
        
    except Exception as e:
        logger.error(f"[get_sales_by_sale_ids_and_counterparty] Exception: {str(e)}", exc_info=True)
        return []

def get_sales_products_by_sale_ids(sale_ids):
    """Get sales products from ISell_SALES_PRODUCTS filtered by sale_ids"""
    if not ISell_SALES_PRODUCTS or not sale_ids:
        return []
    
    try:
        url = get_url(ISell_SALES_PRODUCTS)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        records = data.get("records", [])
        sale_ids_set = set(sale_ids)
        filtered_products = []
        
        for record in records:
            fields = record.get("fields", {})
            sale_id = fields.get("sale_id")
            
            if sale_id in sale_ids_set:
                filtered_products.append(record)
        
        return filtered_products
        
    except Exception as e:
        logger.error(f"[get_sales_products_by_sale_ids] Exception: {str(e)}", exc_info=True)
        return []

def get_product_price_data():
    """Get all product price data from ISell_PRODUCT_PRICE"""
    if not ISell_PRODUCT_PRICE:
        return []
    
    try:
        url = get_url(ISell_PRODUCT_PRICE)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        return data.get("records", [])
        
    except Exception as e:
        logger.error(f"[get_product_price_data] Exception: {str(e)}", exc_info=True)
        return []

def get_transactions_by_sale_ids(sale_ids):
    """Get transactions from ISell_TRANSACTIONS filtered by sale_ids"""
    if not ISell_TRANSACTIONS or not sale_ids:
        return []
    
    try:
        url = get_url(ISell_TRANSACTIONS)
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                data = await fetch_api_data_async(session, url)
                return data
        
        data = asyncio.run(fetch())
        
        if not data:
            return []
        
        records = data.get("records", [])
        sale_ids_set = set(sale_ids)
        filtered_transactions = []
        
        for record in records:
            fields = record.get("fields", {})
            sale_id = fields.get("sale_id")
            
            if sale_id in sale_ids_set:
                filtered_transactions.append(record)
        
        return filtered_transactions
        
    except Exception as e:
        logger.error(f"[get_transactions_by_sale_ids] Exception: {str(e)}", exc_info=True)
        return []


def get_all_grist_data_for_counterparties(counterparty_ids):
    """
    Get all Grist data for multiple counterparty_ids concurrently
    Optimized to fetch product_price_data only once
    TO'G'RI KETMA-KETLIK: Avval SALES jadvalidan sale_id'larni olish, keyin qolgan ma'lumotlarni olish
    """
    if not counterparty_ids:
        return [], [], [], []
    
    # BIRINCHI: SALES jadvalidan sale_id'larni olish (to'g'ri yondashuv)
    all_sale_ids = set()
    all_sales = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Har bir counterparty_id uchun SALES jadvalidan sale'larni olish
        sales_futures = []
        for counterparty_id in counterparty_ids:
            sales_futures.append(
                executor.submit(get_sales_directly_by_counterparty_id, counterparty_id)
            )
        
        # Sale'larni olish va sale_id'larni yig'ish
        for future in sales_futures:
            sales = future.result()
            all_sales.extend(sales)
            # Sale_id'larni yig'ish
            for sale in sales:
                sale_id = sale.get("id")
                if sale_id:
                    all_sale_ids.add(sale_id)
    
    if not all_sale_ids:
        return [], [], [], []
    
    # IKKINCHI: Qolgan ma'lumotlarni parallel olish (sale_id'lar bilan)
    with ThreadPoolExecutor(max_workers=5) as executor:
        sales_products_future = executor.submit(get_sales_products_by_sale_ids, list(all_sale_ids))
        product_price_future = executor.submit(get_product_price_data)
        transactions_future = executor.submit(get_transactions_by_sale_ids, list(all_sale_ids))
        
        all_sales_products = sales_products_future.result()
        product_price_data = product_price_future.result()
        all_transactions = transactions_future.result()
    
    return all_sales, all_sales_products, product_price_data, all_transactions

