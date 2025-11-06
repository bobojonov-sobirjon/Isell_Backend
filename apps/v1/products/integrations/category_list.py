import requests
import json
import os
from pathlib import Path

from apps.v1.products.models import Categories

# Django settings dan BASE_DIR ni olish
try:
    from django.conf import settings
    BASE_DIR = settings.BASE_DIR
except:
    # Agar Django settings yuklanmagan bo'lsa, o'zimiz aniqlaymiz
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent

try:
    from dotenv import load_dotenv
    # .env faylga to'liq yo'l bilan yuklash
    env_path = BASE_DIR / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        # Agar .env fayl topilmasa, joriy directorydan qidiramiz
        load_dotenv(override=True)
except ImportError:
    load_dotenv = None
except Exception:
    pass

# Environment variablelarni olish
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
    print("[CATEGORY_LIST] Starting categories import...")
    url = get_url(Isell_PRODUCT_CATEGORIES)
    print(f"[CATEGORY_LIST] API URL: {url}")
    
    try:
        response = requests.get(url, headers=headers)
        print(f"[CATEGORY_LIST] API Response Status: {response.status_code}")
        
        records = response.json().get("records", [])
        print(f"[CATEGORY_LIST] Total records received: {len(records)}")
        
        created_count = 0
        existing_count = 0
        
        for category in records:
            fields = category.get("fields", {})
            category_name = fields.get("name")
            category_desc = fields.get("description")
            
            print(f"[CATEGORY_LIST] Processing category: {category_name}")
            
            category_obj, created = Categories.objects.get_or_create(
                name=category_name,
                defaults={"description": category_desc}
            )
            
            if created:
                created_count += 1
                print(f"[CATEGORY_LIST] ✓ Created new category: {category_name}")
            else:
                existing_count += 1
                print(f"[CATEGORY_LIST] - Category already exists: {category_name}")
        
        print(f"[CATEGORY_LIST] Import completed! Created: {created_count}, Existing: {existing_count}")
        return {
            "message": "Categories added successfully",
            "created": created_count,
            "existing": existing_count,
            "total": len(records)
        }
        
    except Exception as e:
        print(f"[CATEGORY_LIST] ERROR: {str(e)}")
        return {"error": str(e), "message": "Failed to import categories"}




