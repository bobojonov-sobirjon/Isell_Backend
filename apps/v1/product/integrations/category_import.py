import requests
import json
import os
from pathlib import Path

from apps.v1.product.models import Categories

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
Isell_PRODUCT_CATEGORIES = os.getenv('ISell_PRODUCT_CATEGORIES') or os.getenv('Isell_PRODUCT_CATEGORIES')


def get_url(table_name):
    return f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{table_name}/records"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


def get_categories():
    url = get_url(Isell_PRODUCT_CATEGORIES)
    
    try:
        response = requests.get(url, headers=headers)
        
        records = response.json().get("records", [])
        
        created_count = 0
        existing_count = 0
        
        for category in records:
            fields = category.get("fields", {})
            category_name = fields.get("name")
            category_desc = fields.get("description")
            
            
            category_obj, created = Categories.objects.get_or_create(
                name=category_name,
                defaults={"description": category_desc}
            )
            
            if created:
                created_count += 1
            else:
                existing_count += 1
        
        return {
            "message": "Categories added successfully",
            "created": created_count,
            "existing": existing_count,
            "total": len(records)
        }
        
    except Exception as e:
        return {"error": str(e), "message": "Failed to import categories"}




