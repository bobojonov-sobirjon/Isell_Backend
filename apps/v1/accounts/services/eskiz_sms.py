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
        
        print(f"\n  [EskizSMSService.get_token] DEBUG:")
        print(f"    📊 Bazadan token qidiryapman...")
        
        try:
            token_obj = EskizToken.objects.filter(
                expires_at__gt=timezone.now()
            ).latest('created_at')
            print(f"    ✅ Bazadan token topildi: {token_obj.token[:20] + '...'}")
            print(f"    📊 expires_at: {token_obj.expires_at}")
            return token_obj.token
        except EskizToken.DoesNotExist:
            print(f"    ⚠️  Bazada token topilmadi")
            pass
        
        print(f"    📊 _authenticate chaqirilmoqda...")
        token = self._authenticate()
        if token:
            print(f"    ✅ Yangi token olingan: {token[:20] + '...'}")
            EskizToken.objects.all().delete()
            
            expires_at = timezone.now() + timedelta(days=29)
            EskizToken.objects.create(
                token=token,
                expires_at=expires_at
            )
            print(f"    📊 Token bazaga saqlandi, expires_at: {expires_at}")
        else:
            print(f"    ❌ Token olinmadi")
        
        return token
    
    def _authenticate(self):
        """Authenticate with Eskiz API"""
        print(f"\n    [EskizSMSService._authenticate] DEBUG:")
        print(f"      📊 email: {self.email}")
        print(f"      📊 password: {'*' * len(self.password) if self.password else None}")
        
        try:
            url = f"{self.BASE_URL}/auth/login"
            data = {
                "email": self.email,
                "password": self.password
            }
            
            print(f"      📊 URL: {url}")
            print(f"      📊 Request yuborilmoqda...")
            
            response = requests.post(url, data=data)
            
            print(f"      📊 Response status_code: {response.status_code}")
            print(f"      📊 Response text: {response.text[:500]}")
            
            response.raise_for_status()
            
            result = response.json()
            print(f"      📊 result: {result}")
            
            if result.get("message") == "token_generated":
                token = result.get("data", {}).get("token")
                print(f"      ✅ Token olingan: {token[:20] + '...' if token else None}")
                return token
            else:
                print(f"      ❌ Token olinmadi, message: {result.get('message')}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"      ❌ RequestException: {str(e)}")
            import traceback
            print(f"      Traceback: {traceback.format_exc()}")
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
        print(f"\n  [EskizSMSService.send_sms] DEBUG:")
        print(f"    📊 phone_number: {phone_number}")
        print(f"    📊 message: {message}")
        
        token = self.get_token()
        print(f"    📊 token: {token[:20] + '...' if token else None}")
        
        if not token:
            print(f"    ❌ Token topilmadi")
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
            
            print(f"    📊 URL: {url}")
            print(f"    📊 data: {data}")
            print(f"    📊 Request yuborilmoqda...")
            
            response = requests.post(url, headers=headers, data=data)
            
            print(f"    📊 Response status_code: {response.status_code}")
            print(f"    📊 Response text: {response.text[:500]}")
            
            if response.status_code == 401:
                print(f"    ⚠️  401 Unauthorized - token yangilanmoqda")
                from apps.v1.accounts.models import EskizToken
                EskizToken.objects.all().delete()
                token = self.get_token()
                
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    print(f"    📊 Yangi token bilan qayta urinilmoqda...")
                    response = requests.post(url, headers=headers, data=data)
                    print(f"    📊 Response status_code (retry): {response.status_code}")
                    print(f"    📊 Response text (retry): {response.text[:500]}")
            
            try:
                result = response.json()
                print(f"    📊 result: {result}")
            except ValueError:
                print(f"    ❌ Response JSON parse qilishda xatolik")
                return False
            
            status = result.get("status", "")
            message_text = result.get("message", "")
            
            print(f"    📊 status: {status}")
            print(f"    📊 message_text: {message_text}")
            
            is_success = (
                response.status_code == 200 and 
                (status == "success" or 
                 "success" in message_text.lower() or
                 result.get("id") is not None)
            )
            
            print(f"    📊 is_success: {is_success}")
            
            if is_success:
                print(f"    ✅ SMS muvaffaqiyatli yuborildi")
                return True
            else:
                print(f"    ❌ SMS yuborilmadi")
                return False
                
        except Exception as e:
            print(f"    ❌ Exception: {str(e)}")
            import traceback
            print(f"    Traceback: {traceback.format_exc()}")
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
        
        print(f"\n  [EskizSMSService.send_verification_code] DEBUG:")
        print(f"    📊 phone_number: {phone_number}")
        print(f"    📊 code: {code}")
        
        message = f"Код подтверждения для входа в мобильное приложение ISell Uzbekistan: {code}"
        print(f"    📊 message: {message}")
        
        sms_test_mode = getattr(settings, 'SMS_TEST_MODE', False)
        print(f"    📊 SMS_TEST_MODE: {sms_test_mode}")
        
        if sms_test_mode:
            print(f"    ⚠️  SMS_TEST_MODE aktiv - SMS yuborilmaydi")
            return {'success': True, 'code': code, 'sms_sent': False}
        
        print(f"    📊 send_sms chaqirilmoqda...")
        sms_sent = self.send_sms(phone_number, message)
        print(f"    📊 send_sms result: {sms_sent}")
        
        if not sms_sent:
            print(f"    ❌ SMS yuborilmadi")
            return {
                'success': True, 
                'code': code, 
                'sms_sent': False,
                'message': 'SMS sending failed. Check server logs for details.'
            }
        
        print(f"    ✅ SMS muvaffaqiyatli yuborildi")
        return {'success': True, 'code': None, 'sms_sent': True}
