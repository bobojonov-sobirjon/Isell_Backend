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
                return await response.json()
            else:
                return None
    except Exception as e:
        logger.error(f"[fetch_api_data_async] Exception fetching data from {url}: {str(e)}")
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
        
        # Group by sale_id and filter by counterparty_id
        # NOTE: In Grist, the field is named "counterpart_id" not "counterparty_id"
        sale_ids = set()
        
        for record in records:
            fields = record.get("fields", {})
            # Try both field names for compatibility
            record_counterparty_id = fields.get("counterpart_id") or fields.get("counterparty_id")
            sale_id = fields.get("sale_id")
            
            # Check type matching
            if record_counterparty_id is not None:
                try:
                    if int(record_counterparty_id) == int(counterparty_id) and sale_id:
                        sale_ids.add(sale_id)
                except (ValueError, TypeError):
                    pass
        
        return list(sale_ids)
        
    except Exception as e:
        logger.error(f"[get_transactions_by_counterparty_id] Exception: {str(e)}")
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
        
        # Filter by sale_id and counterparty_id
        # NOTE: In Grist, the field is named "counterpart_id" not "counterparty_id"
        filtered_sales = []
        for record in records:
            record_id = record.get("id")
            fields = record.get("fields", {})
            # Try both field names for compatibility
            record_counterparty_id = fields.get("counterpart_id") or fields.get("counterparty_id")
            
            # Compare as integers for type safety
            try:
                if record_id in sale_ids_set and int(record_counterparty_id) == int(counterparty_id):
                    filtered_sales.append(record)
            except (ValueError, TypeError):
                pass
        
        return filtered_sales
        
    except Exception as e:
        logger.error(f"[get_sales_by_sale_ids_and_counterparty] Exception: {str(e)}")
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
        
        # Filter by sale_id
        filtered_products = []
        for record in records:
            fields = record.get("fields", {})
            sale_id = fields.get("sale_id")
            
            if sale_id in sale_ids_set:
                filtered_products.append(record)
        
        return filtered_products
        
    except Exception as e:
        logger.error(f"[get_sales_products_by_sale_ids] Exception: {str(e)}")
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
        logger.error(f"[get_product_price_data] Exception: {str(e)}")
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
        
        # Filter by sale_id
        filtered_transactions = []
        for record in records:
            fields = record.get("fields", {})
            sale_id = fields.get("sale_id")
            
            if sale_id in sale_ids_set:
                filtered_transactions.append(record)
        
        return filtered_transactions
        
    except Exception as e:
        logger.error(f"[get_transactions_by_sale_ids] Exception: {str(e)}")
        return []


def get_all_grist_data_for_counterparties(counterparty_ids):
    """
    Get all Grist data for multiple counterparty_ids concurrently
    Optimized to fetch product_price_data only once
    """
    if not counterparty_ids:
        return [], [], [], []
    
    # Get all sale_ids for all counterparty_ids
    all_sale_ids = set()
    for counterparty_id in counterparty_ids:
        sale_ids = get_transactions_by_counterparty_id(counterparty_id)
        all_sale_ids.update(sale_ids)
    
    if not all_sale_ids:
        return [], [], [], []
    
    # Fetch all data concurrently (product_price only once)
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit tasks for each counterparty_id
        sales_futures = []
        
        for counterparty_id in counterparty_ids:
            sale_ids = get_transactions_by_counterparty_id(counterparty_id)
            if sale_ids:
                sales_futures.append(
                    executor.submit(get_sales_by_sale_ids_and_counterparty, sale_ids, counterparty_id)
                )
        
        # Sales products for all sale_ids at once
        sales_products_future = executor.submit(get_sales_products_by_sale_ids, list(all_sale_ids))
        # Product price data only once
        product_price_future = executor.submit(get_product_price_data)
        # Transactions for all sale_ids
        transactions_future = executor.submit(get_transactions_by_sale_ids, list(all_sale_ids))
        
        # Collect results
        all_sales = []
        for future in sales_futures:
            all_sales.extend(future.result())
        
        all_sales_products = sales_products_future.result()
        product_price_data = product_price_future.result()
        all_transactions = transactions_future.result()
    
    return all_sales, all_sales_products, product_price_data, all_transactions

