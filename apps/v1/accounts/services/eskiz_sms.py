import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class EskizSMSService:
    """Service for sending SMS through Eskiz API"""
    
    BASE_URL = "https://notify.eskiz.uz/api"
    
    def __init__(self):
        self.email = settings.ESKIZ_EMAIL
        self.password = settings.ESKIZ_PASSWORD
        
    def get_token(self):
        """Get authentication token from database or API"""
        from apps.v1.accounts.models import EskizToken
        
        try:
            token_obj = EskizToken.objects.filter(
                expires_at__gt=timezone.now()
            ).latest('created_at')
            return token_obj.token
        except EskizToken.DoesNotExist:
            pass
        
        token = self._authenticate()
        if token:
            EskizToken.objects.all().delete()
            
            expires_at = timezone.now() + timedelta(days=29)
            EskizToken.objects.create(
                token=token,
                expires_at=expires_at
            )
        
        return token
    
    def _authenticate(self):
        """Authenticate with Eskiz API"""
        try:
            url = f"{self.BASE_URL}/auth/login"
            data = {
                "email": self.email,
                "password": self.password
            }
            
            response = requests.post(url, data=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("message") == "token_generated":
                token = result.get("data", {}).get("token")
                return token
            else:
                return None
                
        except requests.exceptions.RequestException:
            return None
    
    def send_sms(self, phone_number, message):
        """
        Send SMS to phone number
        
        Args:
            phone_number: Phone number in format 998XXXXXXXXX
            message: SMS message text
            
        Returns:
            bool: True if SMS sent successfully, False otherwise
        """
        token = self.get_token()
        
        if not token:
            return False
        
        try:
            url = f"{self.BASE_URL}/message/sms/send"
            headers = {
                "Authorization": f"Bearer {token}"
            }
            data = {
                "mobile_phone": phone_number,
                "message": message,
                "from": "4546"
            }
            
            response = requests.post(url, headers=headers, data=data)
            
            if response.status_code == 401:
                from apps.v1.accounts.models import EskizToken
                EskizToken.objects.all().delete()
                token = self.get_token()
                
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    response = requests.post(url, headers=headers, data=data)
            
            try:
                result = response.json()
            except ValueError:
                return False
            
            status = result.get("status", "")
            message_text = result.get("message", "")
            
            is_success = (
                response.status_code == 200 and 
                (status == "success" or 
                 "success" in message_text.lower() or
                 result.get("id") is not None)
            )
            
            if is_success:
                return True
            else:
                return False
                
        except Exception:
            return False
    
    def add_sms_template(self, template_text):
        """Add SMS template for moderation"""
        token = self.get_token()
        
        if not token:
            return False
        
        try:
            url = f"{self.BASE_URL}/user/template/add"
            headers = {
                "Authorization": f"Bearer {token}"
            }
            data = {
                "text": template_text
            }
            
            response = requests.post(url, headers=headers, data=data)
            
            if response.status_code == 200:
                return True
            else:
                return False
                
        except Exception:
            return False
    
    def send_verification_code(self, phone_number, code):
        """
        Send verification code via SMS
        Returns: dict with 'success', 'code', and 'sms_sent' keys
        """
        from django.conf import settings
        
        message = f"Код подтверждения для входа в мобильное приложение ISell Uzbekistan: {code}"
        
        if getattr(settings, 'SMS_TEST_MODE', False):
            return {'success': True, 'code': code, 'sms_sent': False}
        
        sms_sent = self.send_sms(phone_number, message)
        
        if not sms_sent:
            return {
                'success': True, 
                'code': code, 
                'sms_sent': False,
                'message': 'SMS sending failed. Check server logs for details.'
            }
        
        return {'success': True, 'code': None, 'sms_sent': True}
