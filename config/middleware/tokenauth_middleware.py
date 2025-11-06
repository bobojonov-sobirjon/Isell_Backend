from channels.middleware import BaseMiddleware
from rest_framework_simplejwt.authentication import JWTAuthentication
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
import jwt
from urllib.parse import parse_qs


@database_sync_to_async
def get_user_from_jwt(token_key):
    try:
        jwt_auth = JWTAuthentication()
        validated_token = jwt_auth.get_validated_token(token_key)
        user = jwt_auth.get_user(validated_token)
        return user
    except jwt.ExpiredSignatureError:
        return AnonymousUser()
    except jwt.InvalidTokenError:
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        query_string = parse_qs(scope["query_string"].decode())
        token_key = query_string.get("token", [None])[0]
        scope["user"] = await get_user_from_jwt(token_key) if token_key else AnonymousUser()
        return await super().__call__(scope, receive, send)
