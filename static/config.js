// MYID Configuration
const MYID_CONFIG = {
    // Base URLs (API endpoints) - according to documentation
    BASE_URL: {
        dev: 'https://devmyid.uz',
        prod: 'https://myid.uz'
    },
    // Web SDK URLs
    WEB_SDK_URL: {
        dev: 'https://web.devmyid.uz',
        prod: 'https://web.myid.uz'
    },
    // Backend Proxy URL (if you have a backend proxy for session creation)
    // Automatically detects local vs production based on current URL
    BACKEND_PROXY_URL: (() => {
        const isLocal = window.location.hostname === 'localhost' || 
                       window.location.hostname === '127.0.0.1' ||
                       window.location.hostname === '0.0.0.0';
        if (isLocal) {
            return 'http://127.0.0.1:8000/api/v1/accounts/myid';
        } else {
            // Production: use hardcoded server IP
            return 'http://192.81.218.80:6060/api/v1/accounts/myid';
        }
    })(),
    // Redirect URI for OAuth callback (if different from current page)
    // Leave empty to use current page URL (automatically detected)
    REDIRECT_URI: '', // Will use current page URL automatically
    // Or provide session_id and access_token directly if you already have them
    // Leave empty if you want to create session automatically
    SESSION_ID: '', // Leave empty to create new session via backend
    ACCESS_TOKEN: '', // Leave empty to get new token via backend
    // Client credentials
    CLIENT_ID: 'isell_sdk-0cnI1vDHIIqviRG8dazTki3ZdDHYS1B1iVTHiLaR',
    CLIENT_SECRET: '9BVl7IpGc48adw3k69lScOJjKQGyGt2lNeJ88wEFQLK5m9cDf8GjGKP9oEpuj1eGLlVjX5PNirHcYEHawwoicJ5fUyHGMHZYD3K5',
    CLIENT_HASH_ID: '7a727145-23da-4d42-8f3b-cdd032635a41',
    CLIENT_HASH: 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAsFW3jedThVNXeYv6DFQ43NBBf5kO0yivQrZQ/GKqz64DxhDOj6li+bfGBa9np35W09RoqLYd2r8eIRYK43lxYTS+dA3KJxR1R6ZaoCEEQgkc9EjbfNmmsz/TWyD+WT82F7m8fccD/dyzOF8OEFJrsQlX+X/7iOtcSY+2vK9zGLR+tGig0m+WWhG7DUDyzOp8HWEcBx9arzlBsyvYuP6FfOnR03eaLfHD8wuGC6I3W5POwtD1oSM6Xxwu+SZkkdVU6dADcL8CIP37AIV7K+JYVEqExBsRrrJR7vINTPl+Oof1bDqnaIIjdOZRN7FAcJgQFRfvbXf7koYfx8GuyH5VNwIDAQAB',
    // Environment (change to 'prod' for production)
    ENV: 'dev'
};

// Set HOST based on environment
// According to documentation, base URL is used for API calls
MYID_CONFIG.HOST = MYID_CONFIG.ENV === 'dev' 
    ? MYID_CONFIG.BASE_URL.dev 
    : MYID_CONFIG.BASE_URL.prod;

// Log configuration for debugging
console.log('🔧 MYID Configuration:', {
    ENV: MYID_CONFIG.ENV,
    HOST: MYID_CONFIG.HOST,
    WEB_SDK_URL: MYID_CONFIG.ENV === 'dev' ? MYID_CONFIG.WEB_SDK_URL.dev : MYID_CONFIG.WEB_SDK_URL.prod,
    BACKEND_PROXY_URL: MYID_CONFIG.BACKEND_PROXY_URL
});

