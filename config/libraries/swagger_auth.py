from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
# from apps.v1.accounts.models import CustomUser


@method_decorator(csrf_exempt, name='dispatch')
class SwaggerTokenView(APIView):
    """
    Swagger OAuth2 token endpoint - email and password authentication
    This endpoint allows Swagger UI to authenticate users and automatically use the token
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Handle GET requests for CORS preflight"""
        return JsonResponse({'status': 'ok'}, status=200)
    
    # def post(self, request):
    #     """
    #     OAuth2 password flow for Swagger
    #     Accepts email/password and returns JWT tokens
    #     """
    #     # Handle both form-urlencoded and JSON data
    #     username = request.data.get('username') or request.POST.get('username')
    #     password = request.data.get('password', '') or request.POST.get('password', '')
    #     grant_type = request.data.get('grant_type', 'password') or request.POST.get('grant_type', 'password')
        
    #     if grant_type != 'password':
    #         return JsonResponse({
    #             'error': 'unsupported_grant_type',
    #             'error_description': 'Only password grant type is supported'
    #         }, status=400)
        
    #     if not username:
    #         return JsonResponse({
    #             'error': 'invalid_request',
    #             'error_description': 'Username is required'
    #         }, status=400)
        
    #     if not password:
    #         return JsonResponse({
    #             'error': 'invalid_request',
    #             'error_description': 'Password is required'
    #         }, status=400)
        
    #     try:
    #         # Try to find user by email
    #         user = CustomUser.objects.get(email=username)
            
    #         # Verify password
    #         if not user.check_password(password):
    #             return JsonResponse({
    #                 'error': 'invalid_grant',
    #                 'error_description': 'Invalid email or password'
    #             }, status=400)
            
    #         # Check if user is active
    #         if not user.is_active:
    #             return JsonResponse({
    #                 'error': 'invalid_grant',
    #                 'error_description': 'User account is inactive'
    #             }, status=400)
                
    #     except CustomUser.DoesNotExist:
    #         return JsonResponse({
    #             'error': 'invalid_grant',
    #             'error_description': 'Invalid email or password'
    #         }, status=400)
        
    #     # Generate JWT tokens
    #     refresh = RefreshToken.for_user(user)
    #     access_token = str(refresh.access_token)
    #     refresh_token = str(refresh)
        
    #     return JsonResponse({
    #         'access_token': access_token,
    #         'refresh_token': refresh_token,
    #         'token_type': 'Bearer',
    #         'expires_in': 3600,  # 1 hour
    #         'scope': 'read write'
    #     })
