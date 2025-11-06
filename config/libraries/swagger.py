# Swagger UI settings for drf-yasg
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT Authorization header using the Bearer scheme. Example: "Authorization: Bearer {token}"'
        },
    },
    'USE_SESSION_AUTH': False,
    'JSON_EDITOR': True,
    'SUPPORTED_SUBMIT_METHODS': [
        'get',
        'post',
        'put',
        'delete',
        'patch'
    ],
    'OPERATIONS_SORTER': 'alpha',
    'TAGS_SORTER': 'alpha',
    'DOC_EXPANSION': 'none',
    'DEEP_LINKING': True,
    'SHOW_EXTENSIONS': True,
    'SHOW_COMMON_EXTENSIONS': True,
    'OAUTH2_REDIRECT_URL': '/swagger/',
}

# Swagger UI OAuth2 Configuration
SWAGGER_UI_OAUTH2_CONFIG = {
    'clientId': 'swagger-ui',
    'clientSecret': None,
    'realm': 'ISell Ecommerce API',
    'appName': 'ISell Ecommerce API',
    'scopeSeparator': ' ',
    'useBasicAuthentication': False,
    'usePkceWithAuthorizationCodeGrant': False
}
