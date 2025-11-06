import requests
import json
import os

from apps.v1.order.models import Tariffs


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    load_dotenv = None

API_KEY = os.getenv('ISell_API_KEY')

DOC_ID = os.getenv('ISell_DOC_ID')

Isell_TARIFFS = os.getenv('ISell_TARIFFS')


def get_url(table_name):
    return f"https://isell.getgrist.com/api/docs/{DOC_ID}/tables/{table_name}/records"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


def get_tariffs():
    """
    ISell API dan tariflarni olib kelib bazaga saqlaydi
    Response format: [{id: 1, fields: {name: "...", ...}}]
    """
    url = get_url(Isell_TARIFFS)
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        if not isinstance(data, dict) or 'records' not in data:
            return {"error": "Invalid response format"}
        
        records = data.get('records', [])
        
        created_count = 0
        updated_count = 0
        
        for record in records:
            grist_id = str(record.get('id'))
            fields = record.get('fields', {})
            
            # Ma'lumotlarni olish
            name = fields.get('name', '')
            payments_count = fields.get('payments_count', 0)
            offset = fields.get('offset', 0)
            tariff_type = fields.get('type', '')
            coefficient = fields.get('coefficient', 1.0)
            
            # Tariff yaratish yoki yangilash
            tariff, created = Tariffs.objects.update_or_create(
                grist_tariff_id=grist_id,
                defaults={
                    'name': name,
                    'payments_count': payments_count,
                    'offset_days': offset,
                    'type': tariff_type,
                    'coefficient': coefficient,
                    'is_active': True
                }
            )
            
            if created:
                created_count += 1
            else:
                updated_count += 1
        
        return {
            "success": True,
            "message": "Tariffs imported successfully",
            "created": created_count,
            "updated": updated_count,
            "total": len(records)
        }
        
    except requests.RequestException as e:
        return {
            "success": False,
            "error": f"API request failed: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Import failed: {str(e)}"
        }




