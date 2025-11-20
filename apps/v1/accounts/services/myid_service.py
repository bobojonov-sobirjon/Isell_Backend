import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def get_access_token():
    """
    Получение Access Token через API MyID
    
    Returns:
        dict: Ответ от API с access_token или ошибка
    """
    url = f"{settings.MYID_HOST}/api/v1/auth/clients/access-token"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "client_id": settings.MYID_CLIENT_ID,
        "client_secret": settings.MYID_CLIENT_SECRET
    }
    
    logger.info(f"Requesting access token from: {url}")
    logger.debug(f"Payload: client_id={settings.MYID_CLIENT_ID[:20]}...")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        logger.info(f"Response status: {response.status_code}")
        
        response.raise_for_status()  # Raises an HTTPError for bad responses
        
        response_data = response.json()
        logger.info("Access token received successfully")
        
        return {
            "success": True,
            "data": response_data,
            "status_code": response.status_code
        }
    except requests.exceptions.HTTPError as e:
        error_detail = None
        try:
            error_detail = response.json()
        except:
            error_detail = response.text
        logger.error(f"HTTP Error getting access token: {e}, Status: {response.status_code}, Detail: {error_detail}")
        return {
            "success": False,
            "error": str(e),
            "error_detail": error_detail,
            "status_code": response.status_code
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Request Exception getting access token: {e}")
        return {
            "success": False,
            "error": str(e),
            "status_code": None
        }
    except Exception as e:
        logger.error(f"Unexpected error getting access token: {e}")
        return {
            "success": False,
            "error": str(e),
            "status_code": None
        }


def create_session(access_token, phone_number=None, birth_date=None, is_resident=None, 
                   pinfl=None, threshold=None, pass_data=None):
    """
    Создание сессии через API MyID
    
    Args:
        access_token (str): Access token полученный из get_access_token()
        phone_number (str, optional): Номер телефона в формате 998901234567 (min_len=12, max_len=13)
        birth_date (str, optional): Дата рождения в формате YYYY-MM-DD
        is_resident (bool, optional): Является ли пользователь резидентом (default: true)
        pinfl (str, optional): 14-значный персональный ID
        threshold (float, optional): От 0.5 до 0.99
        pass_data (str, optional): Серия и номер паспорта
    
    Returns:
        dict: Ответ от API с данными сессии или ошибка
    """
    url = f"{settings.MYID_HOST}/api/v1/sdk/sessions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    payload = {}
    
    # Добавляем только переданные параметры
    if phone_number is not None:
        payload["phone_number"] = phone_number
    if birth_date is not None:
        payload["birth_date"] = birth_date
    if pinfl is not None:
        payload["pinfl"] = pinfl
    if pass_data is not None:
        payload["pass_data"] = pass_data
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        return {
            "success": True,
            "data": response.json(),
            "status_code": response.status_code
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "status_code": response.status_code if 'response' in locals() else None
        }


def get_user_data(access_token, code):
    """
    Получение данных пользователя через API MyID
    
    Args:
        access_token (str): Access token полученный из get_access_token()
        code (str): Код полученный от SDK после идентификации
    
    Returns:
        dict: Ответ от API с данными пользователя или ошибка
    """
    url = f"{settings.MYID_HOST}/api/v1/sdk/data"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    params = {
        "code": code
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        return {
            "success": True,
            "data": response.json(),
            "status_code": response.status_code
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "status_code": response.status_code if 'response' in locals() else None
        }

