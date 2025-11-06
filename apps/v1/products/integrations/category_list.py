import requests
import json
import os

from apps.v1.products.models import Categories


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    load_dotenv = None

API_KEY = os.getenv('ISell_API_KEY')

DOC_ID = os.getenv('ISell_DOC_ID')

Isell_PRODUCT_CATEGORIES = os.getenv('ISell_PRODUCT_CATEGORIES')


def get_url(table_name):
    return f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{table_name}/records"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


def get_categories():
    url = get_url(Isell_PRODUCT_CATEGORIES)
    response = requests.get(url, headers=headers)

    for category in response.json().get("records", []):
        fields = category.get("fields", {})
        Categories.objects.get_or_create(
            name=fields.get("name"),
            description=fields.get("description"),
        )
        
    return {"message": "Categories added successfully"}




