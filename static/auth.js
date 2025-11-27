// Authentication state
let authState = {
    currentStep: 'init',
    backendAccessToken: null, // Access token for API calls (client_credentials)
    sessionId: null,
    authCode: null,
    userAccessToken: null, // Final access token for user
    userData: {
        pinfl: null,
        passData: null,
        birthDate: null,
        isResident: true
    }
};

// DOM Elements
const elements = {
    statusMessage: document.getElementById('status-message'),
    userDataForm: document.getElementById('user-data-form'),
    passportInput: document.getElementById('passport-input'),
    birthDateInput: document.getElementById('birth-date-input'),
    isResidentCheckbox: document.getElementById('is-resident'),
    btnSubmitData: document.getElementById('btn-submit-data'),
    btnScanPassport: document.getElementById('btn-scan-passport'),
    btnProceedToken: document.getElementById('btn-proceed-token'),
    btnCopyToken: document.getElementById('btn-copy-token'),
    btnCopyFinalToken: document.getElementById('btn-copy-final-token'),
    btnRestart: document.getElementById('btn-restart'),
    steps: {
        init: document.getElementById('step-init'),
        face: document.getElementById('step-face'),
        code: document.getElementById('step-code'),
        token: document.getElementById('step-token'),
        success: document.getElementById('step-success')
    },
    myidIframe: document.getElementById('myid-iframe'),
    myidIframeContainer: document.getElementById('myid-iframe-container'),
    faceLoading: document.getElementById('face-loading'),
    codeDisplay: document.getElementById('code-display'),
    authCode: document.getElementById('auth-code'),
    sessionIdDisplay: document.getElementById('session-id'),
    tokenDisplay: document.getElementById('token-display'),
    accessToken: document.getElementById('access-token'),
    finalTokenDisplay: document.getElementById('final-token-display'),
    finalAccessToken: document.getElementById('final-access-token')
};

// Utility Functions
function showStatus(message, type = 'info') {
    elements.statusMessage.textContent = message;
    elements.statusMessage.className = `status-message ${type}`;
    setTimeout(() => {
        elements.statusMessage.className = 'status-message';
    }, 5000);
}

function showStep(stepName) {
    Object.values(elements.steps).forEach(step => {
        step.classList.remove('active');
    });
    if (elements.steps[stepName]) {
        elements.steps[stepName].classList.add('active');
        authState.currentStep = stepName;
    }
}

// Get user's IP address
async function getUserIP() {
    try {
        // Try to get IP from various services
        const response = await fetch('https://api.ipify.org?format=json');
        const data = await response.json();
        return data.ip;
    } catch (error) {
        console.warn('Could not get user IP:', error);
        return null;
    }
}

// Generate UUID v4
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Step 1: Get Access Token (client_credentials)
// NOTE: According to backend response, access_token comes with session creation
// So we'll skip this step and get token from session creation
// Keeping this function for backward compatibility
async function getBackendAccessToken() {
    // This function is now optional - access_token comes with session creation
    // But we'll keep it in case it's needed separately
    return null;
    try {
        const tokenUrl = `${MYID_CONFIG.HOST}/api/v1/oauth2/access-token`;
        
        // According to MYID documentation, use form-urlencoded format
        // Format: grant_type=client_credentials&client_id=...&client_secret=...
        const tokenParams = new URLSearchParams();
        tokenParams.append('grant_type', 'client_credentials');
        tokenParams.append('client_id', MYID_CONFIG.CLIENT_ID);
        tokenParams.append('client_secret', MYID_CONFIG.CLIENT_SECRET);
        
        const requestBody = tokenParams.toString();
        console.log('Requesting backend access token from:', tokenUrl);
        console.log('Request body (form-urlencoded):', requestBody);
        console.log('Client ID:', MYID_CONFIG.CLIENT_ID);
        console.log('Client Secret length:', MYID_CONFIG.CLIENT_SECRET.length);
        console.log('Grant type: client_credentials');
        
        // Try standard form-urlencoded first (as per documentation)
        let response = await fetch(tokenUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'
            },
            body: requestBody
        });
        
        // Log the exact request for debugging
        console.log('Request details:', {
            url: tokenUrl,
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'
            },
            body: requestBody,
            bodyLength: requestBody.length
        });

        const responseText = await response.text();
        console.log('Access token response status:', response.status);
        console.log('Access token response:', responseText);
        console.log('Response headers:', Object.fromEntries(response.headers.entries()));

        if (!response.ok) {
            let errorData;
            try {
                if (responseText && responseText.trim()) {
                    errorData = JSON.parse(responseText);
                } else {
                    errorData = { 
                        message: `Empty response body. Status: ${response.status}`,
                        error: 'empty_response',
                        status: response.status
                    };
                }
            } catch (e) {
                console.error('JSON parse error:', e);
                console.error('Response text that failed to parse:', responseText);
                errorData = { 
                    message: responseText || `No response body. Status: ${response.status}`,
                    error: 'parse_error',
                    status: response.status,
                    rawResponse: responseText
                };
            }
            
            // Parse FastAPI/Pydantic validation errors
            if (errorData.detail && Array.isArray(errorData.detail)) {
                const errors = errorData.detail.map(err => {
                    const field = err.loc ? err.loc.join('.') : 'unknown';
                    return `${field}: ${err.msg || err.message || 'validation error'}`;
                }).join(', ');
                console.error('Validation errors:', errorData.detail);
                console.error('Request body was:', requestBody);
                console.error('Content-Type was: application/x-www-form-urlencoded');
                console.error('Full error response:', errorData);
                
                // If body is empty in error response, it means API couldn't read the body
                if (errorData.body && Object.keys(errorData.body).length === 0) {
                    throw new Error(`API body ni o'qiy olmadi. Ehtimol endpoint noto'g'ri yoki API hozir ishlamayapti. Xatolik: ${errors}`);
                }
                
                throw new Error(`Validation xatolik: ${errors}. Body o'qilmagan - ehtimol API endpoint yoki format noto'g'ri.`);
            }
            
            // More detailed error message
            // If it's a plain text error (like "Invalid grant_type."), show it directly
            let errorMsg;
            if (errorData.error === 'parse_error' && errorData.rawResponse) {
                errorMsg = errorData.rawResponse;
            } else {
                errorMsg = errorData.error_description || errorData.error || errorData.message || `HTTP error! status: ${response.status}`;
            }
            console.error('Access token error details:', errorData);
            throw new Error(errorMsg);
        }

        let responseData;
        try {
            responseData = JSON.parse(responseText);
        } catch (e) {
            throw new Error('Invalid JSON response: ' + responseText);
        }
        
        if (responseData.access_token) {
            authState.backendAccessToken = responseData.access_token;
            console.log('Access token received successfully');
            return responseData.access_token;
        } else {
            throw new Error('Access token olinmadi. Javob: ' + JSON.stringify(responseData));
        }
    } catch (error) {
        console.error('Get access token error:', error);
        throw new Error(`Access token olishda xatolik: ${error.message}`);
    }
}

// Step 2: Create Session or Use Existing
// According to backend response, this endpoint returns both session_id and access_token
// Or use existing session_id and access_token from config
async function createSession() {
    try {
        // If session_id and access_token are already provided in config, use them
        if (MYID_CONFIG.SESSION_ID && MYID_CONFIG.ACCESS_TOKEN) {
            console.log('Using existing session_id and access_token from config');
            authState.sessionId = MYID_CONFIG.SESSION_ID;
            authState.backendAccessToken = MYID_CONFIG.ACCESS_TOKEN;
            return authState.sessionId;
        }
        
        // If backend proxy URL is provided, use it
        if (MYID_CONFIG.BACKEND_PROXY_URL) {
            showStatus('Session yaratilmoqda (backend orqali)...', 'info');
            const sessionUrl = `${MYID_CONFIG.BACKEND_PROXY_URL}/session/`; // Backend endpoint
            
            // Prepare session data with user information
            const sessionData = {};
            
            // Add user data if available
            if (authState.userData.pinfl) {
                sessionData.pinfl = authState.userData.pinfl;
            } else if (authState.userData.passData) {
                sessionData.pass_data = authState.userData.passData;
            }
            
            if (authState.userData.birthDate) {
                sessionData.birth_date = authState.userData.birthDate;
            }
            
            console.log('Creating session via backend proxy:', sessionUrl);
            console.log('Session data:', sessionData);
            
            const response = await fetch(sessionUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(sessionData)
            });

            const responseText = await response.text();
            console.log('Session creation response status:', response.status);
            console.log('Session creation response:', responseText);

            if (!response.ok) {
                let errorData;
                try {
                    errorData = JSON.parse(responseText);
                } catch (e) {
                    errorData = { message: responseText };
                }
                throw new Error(errorData.message || errorData.error || `HTTP error! status: ${response.status}`);
            }

            const responseData = JSON.parse(responseText);
            console.log('Session creation response data:', responseData);
            
            // Handle response format: {success: true, data: {session_id: "...", access_token: "..."}}
            if (responseData.success && responseData.data) {
                if (responseData.data.session_id) {
                    authState.sessionId = responseData.data.session_id;
                }
                if (responseData.data.access_token) {
                    authState.backendAccessToken = responseData.data.access_token;
                    console.log('Access token received from session creation');
                }
            }
            
            if (authState.sessionId) {
                return authState.sessionId;
            } else {
                throw new Error('Session ID olinmadi. Javob: ' + JSON.stringify(responseData));
            }
        }
        
        // Otherwise, try to create session directly from MYID API
        showStatus('Session yaratilmoqda...', 'info');
        
        // According to backend response, session creation endpoint might be different
        // Try the standard endpoint first
        const sessionUrl = `${MYID_CONFIG.HOST}/api/v1/web/sessions`;
        
        // Get user IP
        const userIP = await getUserIP();
        
        const sessionData = {
            max_retries: 3,
            external_id: generateUUID(),
            ip_address: userIP || '127.0.0.1' // Fallback if IP cannot be determined
        };
        
        console.log('Creating session:', sessionUrl);
        console.log('Session data:', sessionData);
        
        // Try with client credentials in header (Basic Auth)
        // Some APIs use Basic Auth with client_id:client_secret
        const credentials = btoa(`${MYID_CONFIG.CLIENT_ID}:${MYID_CONFIG.CLIENT_SECRET}`);
        
        let response = await fetch(sessionUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': `Basic ${credentials}`
            },
            body: JSON.stringify(sessionData)
        });

        // If fails, try with Bearer token (if we have one)
        if (!response.ok && response.status === 401 && authState.backendAccessToken) {
            console.log('Trying with Bearer token...');
            response = await fetch(sessionUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': `Bearer ${authState.backendAccessToken}`
                },
                body: JSON.stringify(sessionData)
            });
        }
        
        // If still fails, try with client_id and client_secret in body
        if (!response.ok && response.status === 401) {
            console.log('Trying with client credentials in body...');
            const sessionDataWithAuth = {
                ...sessionData,
                client_id: MYID_CONFIG.CLIENT_ID,
                client_secret: MYID_CONFIG.CLIENT_SECRET
            };
            response = await fetch(sessionUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(sessionDataWithAuth)
            });
        }

        const responseText = await response.text();
        console.log('Session creation response status:', response.status);
        console.log('Session creation response:', responseText);

        if (!response.ok) {
            let errorData;
            try {
                errorData = JSON.parse(responseText);
            } catch (e) {
                errorData = { message: responseText };
            }
            throw new Error(errorData.message || errorData.error || `HTTP error! status: ${response.status}`);
        }

        const responseData = JSON.parse(responseText);
        console.log('Session creation response data:', responseData);
        
        // Handle different response formats
        // Format 1: {success: true, data: {session_id: "...", access_token: "..."}}
        // Format 2: {session_id: "..."}
        if (responseData.success && responseData.data) {
            if (responseData.data.session_id) {
                authState.sessionId = responseData.data.session_id;
            }
            if (responseData.data.access_token) {
                authState.backendAccessToken = responseData.data.access_token;
                console.log('Access token received from session creation');
            }
        } else if (responseData.session_id) {
            authState.sessionId = responseData.session_id;
        }
        
        if (authState.sessionId) {
            return authState.sessionId;
        } else {
            throw new Error('Session ID olinmadi. Javob: ' + JSON.stringify(responseData));
        }
    } catch (error) {
        console.error('Create session error:', error);
        throw new Error(`Session yaratishda xatolik: ${error.message}`);
    }
}

// Validate passport/PINFL input
function validatePassportInput(value) {
    if (!value) return { valid: false, error: 'Passport yoki PINFL kiriting' };
    
    // Remove spaces and convert to uppercase
    const cleaned = value.replace(/\s/g, '').toUpperCase();
    
    // Check if it's PINFL (14 digits)
    if (/^\d{14}$/.test(cleaned)) {
        return { valid: true, type: 'pinfl', value: cleaned };
    }
    
    // Check if it's passport (2 letters + 7 digits, e.g., AA1234567)
    if (/^[A-Z]{2}\d{7}$/.test(cleaned)) {
        return { valid: true, type: 'passport', value: cleaned };
    }
    
    return { valid: false, error: 'Noto\'g\'ri format. PINFL (14 raqam) yoki Passport (AA1234567) kiriting' };
}

// Format date for API (YYYY-MM-DD)
function formatDateForAPI(dateString) {
    if (!dateString) return null;
    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// Step 3: Initialize MYID Web SDK
async function initializeMYIDWebSDK() {
    try {
        showStep('face');
        showStatus('MYID yuzni tanib olish jarayonini boshlayapti...', 'info');
        
        const { pinfl, passData, birthDate, isResident } = authState.userData;
        
        if (!authState.sessionId) {
            throw new Error('Session ID topilmadi');
        }
        
        if (!birthDate) {
            throw new Error('Tug\'ilgan sana kiritilmagan');
        }
        
        // Build MYID Web SDK URL based on ENV setting
        // Use dev SDK for dev environment, prod SDK for production
        const webSDKBaseUrl = MYID_CONFIG.ENV === 'dev' 
            ? MYID_CONFIG.WEB_SDK_URL.dev 
            : MYID_CONFIG.WEB_SDK_URL.prod;
        
        console.log('MYID Environment:', MYID_CONFIG.ENV);
        console.log('MYID Web SDK URL:', webSDKBaseUrl);
        console.log('MYID HOST:', MYID_CONFIG.HOST);
        
        // Handle redirect_uri
        // According to documentation:
        // - redirect_uri is YOUR page where MYID will redirect user after identification
        // - For iframe mode, redirect_uri is not used for redirect but should still be provided
        // - redirect_uri should be YOUR callback page, NOT MYID SDK URL (https://web.devmyid.uz)
        // - Example: https://myid.uz (your domain) or http://localhost:8080/index.html
        let redirectUri;
        if (MYID_CONFIG.REDIRECT_URI) {
            // Use custom redirect URI from config
            redirectUri = encodeURIComponent(MYID_CONFIG.REDIRECT_URI);
        } else {
            // Use current page URL as redirect_uri (remove query params and hash)
            // This is YOUR page where MYID will redirect after identification
            const currentUrl = window.location.origin + window.location.pathname;
            // Remove trailing slash if it's not root, but keep it for production HTTPS
            let cleanUrl = currentUrl;
            if (currentUrl.endsWith('/') && currentUrl !== window.location.origin + '/') {
                cleanUrl = currentUrl.slice(0, -1);
            }
            redirectUri = encodeURIComponent(cleanUrl);
            console.log('Auto-detected redirect URI:', cleanUrl);
        }
        
        console.log('Redirect URI (where MYID will redirect after identification):', decodeURIComponent(redirectUri));
        const birthDateFormatted = formatDateForAPI(birthDate);
        
        const params = new URLSearchParams({
            session_id: authState.sessionId,
            birth_date: birthDateFormatted,
            redirect_uri: redirectUri,
            iframe: 'true',
            theme: 'light',
            lang: 'uz'
        });
        
        // Add PINFL or passport data
        // According to documentation:
        // - For residents: session_id + pinfl + birth_date + redirect_uri OR session_id + pass_data + birth_date + redirect_uri
        // - For non-residents: session_id + pinfl + birth_date + redirect_uri (with is_resident=false)
        if (pinfl) {
            params.append('pinfl', pinfl);
        } else if (passData) {
            params.append('pass_data', passData);
        }
        
        // Add is_resident parameter
        // According to documentation:
        // - If is_resident=false, can use pinfl+birth_date for non-residents
        // - If sending resident data with is_resident=false, will get error code 2
        // - Default is true (resident), so we only add if false
        if (!isResident) {
            params.append('is_resident', 'false');
            console.log('Non-resident mode: is_resident=false');
        } else {
            // For residents, we can omit is_resident (default is true)
            // But we can also explicitly set it to true if needed
            // params.append('is_resident', 'true'); // Optional
        }
        
        const myidUrl = `${webSDKBaseUrl}/?${params.toString()}`;
        
        // Load MYID Web SDK in iframe
        console.log('Loading MYID Web SDK:', myidUrl);
        
        // Show loading spinner while iframe loads
        elements.faceLoading.style.display = 'block';
        elements.myidIframeContainer.style.display = 'none';
        
        // Ensure iframe has proper permissions before loading
        // Don't set sandbox if we need camera access - sandbox blocks camera
        // Only set allow attribute for permissions
        elements.myidIframe.setAttribute('allow', 'camera; microphone; fullscreen; autoplay');
        // Remove sandbox attribute as it blocks camera access
        elements.myidIframe.removeAttribute('sandbox');
        
        // Load iframe immediately - don't wait for camera check
        // MYID SDK will request camera permission itself
        console.log('Setting iframe src to:', myidUrl);
        
        // Check iframe before loading
        console.log('Iframe element:', myidIframe);
        console.log('Iframe current src:', myidIframe.src);
        
        elements.myidIframe.src = myidUrl;
        
        // Check iframe after setting src
        setTimeout(() => {
            console.log('Iframe src after setting:', myidIframe.src);
            console.log('Iframe contentWindow:', myidIframe.contentWindow);
            console.log('Iframe contentDocument:', myidIframe.contentDocument);
        }, 100);
        
        // According to documentation, we need to send screen info to iframe
        const myidIframe = elements.myidIframe;
        function screenChangeListener(e) {
            if (myidIframe.contentWindow) {
                try {
                    myidIframe.contentWindow.postMessage(
                        {
                            cmd: 'screen',
                            screen: {
                                width: window.screen.width,
                                height: window.screen.height,
                                availWidth: window.screen.availWidth,
                                availHeight: window.screen.availHeight
                            },
                            height: window.innerHeight,
                            width: window.innerWidth,
                        },
                        '*'
                    );
                } catch (err) {
                    console.warn('Failed to send screen info:', err);
                }
            }
        }
        
        // Track if we've received any message from MYID SDK
        let receivedSDKMessage = false;
        
        // Create a wrapper for handleMYIDMessage that tracks SDK messages
        const wrappedHandleMessage = (event) => {
            // Log ALL messages for debugging
            console.log('[DEBUG] Message received:', {
                data: event.data,
                origin: event.origin,
                source: event.data?.source,
                status: event.data?.status
            });
            
            if (event.data && event.data.source === 'MyIDWebSDK') {
                receivedSDKMessage = true;
                console.log('✅ Received MYID SDK message, hiding loading spinner');
                elements.faceLoading.style.display = 'none';
                elements.myidIframeContainer.style.display = 'block';
            }
            handleMYIDMessage(event);
        };
        
        // Listen for messages from iframe according to MYID documentation
        // Remove existing listener to avoid duplicates
        window.removeEventListener('message', handleMYIDMessage);
        window.removeEventListener('message', wrappedHandleMessage);
        window.addEventListener('message', wrappedHandleMessage);
        console.log('Message listener attached');
        
        // Set timeout to show iframe even if load event doesn't fire
        let loadTimeout = setTimeout(() => {
            console.warn('⚠️ MYID iframe load timeout - showing iframe anyway');
            console.log('Iframe src:', myidIframe.src);
            console.log('Iframe contentWindow:', myidIframe.contentWindow);
            elements.faceLoading.style.display = 'none';
            elements.myidIframeContainer.style.display = 'block';
            if (!receivedSDKMessage) {
                showStatus('Iframe yuklandi. Agar kamera ochilmasa, browser sozlamalarida ruxsat bering yoki sahifani yangilang.', 'info');
            }
        }, 3000); // 3 seconds timeout (increased)
        
        myidIframe.addEventListener('load', () => {
            console.log('✅ MYID iframe loaded successfully');
            clearTimeout(loadTimeout);
            
            // Show iframe immediately when loaded
            elements.faceLoading.style.display = 'none';
            elements.myidIframeContainer.style.display = 'block';
            
            // Send screen info immediately after iframe loads
            console.log('Sending screen info to iframe...');
            screenChangeListener();
            
            // Send again after delays to ensure SDK receives it
            setTimeout(() => {
                console.log('Sending screen info (100ms delay)...');
                screenChangeListener();
            }, 100);
            
            setTimeout(() => {
                console.log('Sending screen info (500ms delay)...');
                screenChangeListener();
            }, 500);
            
            setTimeout(() => {
                console.log('Sending screen info (1000ms delay)...');
                screenChangeListener();
                if (!receivedSDKMessage) {
                    console.warn('⚠️ No SDK message received after 1 second');
                    showStatus('Iframe yuklandi. Kamera ruxsatini bering yoki sahifani yangilang.', 'info');
                }
            }, 1000);
        });
        
        // Also listen for error events
        myidIframe.addEventListener('error', (e) => {
            console.error('❌ MYID iframe error:', e);
            clearTimeout(loadTimeout);
            showStatus('Iframe yuklashda xatolik yuz berdi', 'error');
        });
        
        // Periodically check if iframe is loaded and send screen info
        let checkInterval = setInterval(() => {
            if (myidIframe.contentWindow) {
                console.log('Iframe contentWindow is available, sending screen info...');
                screenChangeListener();
            }
        }, 2000); // Check every 2 seconds
        
        // Clear interval after 10 seconds
        setTimeout(() => {
            clearInterval(checkInterval);
        }, 10000);
        
        window.addEventListener('resize', screenChangeListener);
        
    } catch (error) {
        showStatus(`MYID SDK init xatolik: ${error.message}`, 'error');
        showStep('init');
    }
}

// Check camera availability
async function checkCameraAvailability() {
    try {
        // Check if getUserMedia is available
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('getUserMedia is not supported in this browser');
        }
        
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: { 
                facingMode: 'user', // Front camera
                width: { ideal: 1280 },
                height: { ideal: 720 }
            }, 
            audio: false 
        });
        console.log('Camera is available and working');
        stream.getTracks().forEach(track => track.stop()); // Stop the stream
        showStatus('Kamera mavjud va tayyor', 'success');
        return true;
    } catch (error) {
        console.error('Camera error:', error);
        let errorMsg = 'Kamera ochilmayapti. ';
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
            errorMsg += 'Iltimos, browser sozlamalarida kamera ruxsatini bering va sahifani yangilang.';
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
            errorMsg += 'Kamera topilmadi. Iltimos, kamerani ulang.';
        } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
            errorMsg += 'Kamera boshqa dastur tomonidan ishlatilmoqda. Boshqa dasturlarni yoping.';
        } else if (error.name === 'OverconstrainedError' || error.name === 'ConstraintNotSatisfiedError') {
            errorMsg += 'Kamera sozlamalari qo\'llab-quvvatlanmaydi.';
        } else {
            errorMsg += error.message || 'Noma\'lum xatolik';
        }
        showStatus(errorMsg, 'error');
        throw error;
    }
}

// Handle messages from MYID iframe
// According to MYID documentation, iframe sends postMessage events
const MyIDStatus = {
    EXCEPTION: -1,
    IN_PROGRESS: 0,
    LIVENESS_PASSED: 1,
    LIVENESS_FAILED: 2,
    RETRY: 3,
    EXITED: 4,
    LOADING: 100,
    LOADED: 101,
};

function handleMYIDMessage(event) {
    // Check if message is from MyID Web SDK
    if (!event.data || event.data.source !== 'MyIDWebSDK') {
        return; // Already logged in wrappedHandleMessage
    }
    
    // Check origin - allow both dev and prod domains
    const allowedOrigins = [MYID_CONFIG.WEB_SDK_URL.dev, MYID_CONFIG.WEB_SDK_URL.prod];
    if (!allowedOrigins.includes(event.origin)) {
        console.warn('⚠️ Message from unexpected origin:', event.origin, 'Expected:', allowedOrigins);
        return;
    }
    
    console.log('✅ Processing MYID SDK message:', event.data);
    
    // Handle MYID SDK messages according to documentation
    switch (event.data.status) {
        case MyIDStatus.EXCEPTION:
            console.error('MyID Iframe failed to load properly or a runtime error occurred.', event.data.error);
            showStatus('MyID SDK xatolik: ' + (event.data.error || 'Noma\'lum xatolik'), 'error');
            break;
        case MyIDStatus.IN_PROGRESS:
            console.log('Client interacted with the iframe.');
            showStatus('Yuzni tanib olish jarayoni davom etmoqda...', 'info');
            // Ensure iframe is visible when user starts interaction
            elements.faceLoading.style.display = 'none';
            elements.myidIframeContainer.style.display = 'block';
            break;
        case MyIDStatus.LIVENESS_PASSED:
            console.log('Liveness passed:', event.data);
            showStatus('Yuzni tanib olish muvaffaqiyatli!', 'success');
            // Note: This is just a frontend event, actual verification should be done via backend
            break;
        case MyIDStatus.LIVENESS_FAILED:
            console.log('Liveness failed:', event.data.result_code, event.data.result_note);
            showStatus('Yuzni tanib olish muvaffaqiyatsiz: ' + (event.data.result_note || 'Xatolik'), 'error');
            break;
        case MyIDStatus.RETRY:
            console.log('Client is trying again.');
            showStatus('Qayta urinilmoqda...', 'info');
            break;
        case MyIDStatus.EXITED:
            console.log('Client chose to return to your application early.');
            showStatus('Jarayon bekor qilindi', 'info');
            showStep('init');
            break;
        case MyIDStatus.LOADING:
            console.log('MyID SDK is loading...');
            showStatus('MyID SDK yuklanmoqda...', 'info');
            // Keep loading spinner visible
            elements.faceLoading.style.display = 'block';
            elements.myidIframeContainer.style.display = 'none';
            break;
        case MyIDStatus.LOADED:
            console.log('MyID SDK loaded successfully.');
            showStatus('MyID SDK yuklandi. Kamera ochilmoqda...', 'success');
            // Hide loading spinner and show iframe immediately
            elements.faceLoading.style.display = 'none';
            elements.myidIframeContainer.style.display = 'block';
            // Send screen info again when SDK is loaded
            const myidIframe = elements.myidIframe;
            if (myidIframe && myidIframe.contentWindow) {
                try {
                    myidIframe.contentWindow.postMessage(
                        {
                            cmd: 'screen',
                            screen: {
                                width: window.screen.width,
                                height: window.screen.height,
                                availWidth: window.screen.availWidth,
                                availHeight: window.screen.availHeight
                            },
                            height: window.innerHeight,
                            width: window.innerWidth,
                        },
                        '*'
                    );
                } catch (err) {
                    console.warn('Failed to send screen info after LOADED:', err);
                }
            }
            break;
        default:
            console.log('Unknown MyID status:', event.data);
    }
}

// Step 4: Handle OAuth Callback (when redirected back from MYID)
function handleOAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const authCode = urlParams.get('auth_code');
    const sessionId = urlParams.get('session_id');
    const error = urlParams.get('error');
    
    if (error) {
        showStatus(`Xatolik: ${error}`, 'error');
        showStep('init');
        // Clean URL
        window.history.replaceState({}, document.title, window.location.pathname);
        return;
    }
    
    if (authCode && sessionId) {
        authState.authCode = authCode;
        authState.sessionId = sessionId;
        
        // Display code
        elements.authCode.textContent = authCode;
        elements.sessionIdDisplay.textContent = sessionId;
        elements.codeDisplay.style.display = 'block';
        
        showStep('code');
        showStatus('Autentifikatsiya kodi muvaffaqiyatli olindi!', 'success');
        
        // Clean URL
        window.history.replaceState({}, document.title, window.location.pathname);
    }
}

// Step 5: Exchange Auth Code for User Access Token
// According to MYID documentation, use the same endpoint with authorization_code grant type
async function getUserAccessToken(code) {
    try {
        showStep('token');
        showStatus('Access token olinmoqda...', 'info');
        
        // According to documentation: /api/v1/oauth2/access-token with authorization_code
        const tokenUrl = `${MYID_CONFIG.HOST}/api/v1/oauth2/access-token`;
        
        // According to documentation, these parameters are required:
        // grant_type="authorization_code"
        // client_id="**********"
        // client_secret="**********"
        // code="{{auth_code}}"
        // method="strong"
        // scope="common_data"
        const tokenParams = new URLSearchParams();
        tokenParams.append('grant_type', 'authorization_code');
        tokenParams.append('client_id', MYID_CONFIG.CLIENT_ID);
        tokenParams.append('client_secret', MYID_CONFIG.CLIENT_SECRET);
        tokenParams.append('code', code);
        tokenParams.append('method', 'strong');
        tokenParams.append('scope', 'common_data');
        
        console.log('Exchanging auth code for token:', tokenUrl);
        
        try {
            const response = await fetch(tokenUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json'
                },
                body: tokenParams.toString()
            });

            const responseText = await response.text();
            console.log('Token exchange response status:', response.status);
            console.log('Token exchange response:', responseText);

            if (!response.ok) {
                let errorData;
                try {
                    errorData = JSON.parse(responseText);
                } catch (e) {
                    errorData = { message: responseText };
                }
                
                // If endpoint doesn't exist, show auth_code as result
                if (response.status === 404 || response.status === 400) {
                    showStatus('Eslatma: Token exchange endpoint topilmadi. Auth code ni backend da ishlatishingiz kerak.', 'info');
                    // Display auth_code as final result
                    const authCodeData = {
                        auth_code: code,
                        session_id: authState.sessionId,
                        note: 'Bu auth_code ni backend da ishlatishingiz kerak. Token exchange endpoint MYID dokumentatsiyasida ko\'rsatilmagan.'
                    };
                    displayToken(code, authCodeData);
                    showStep('success');
                    return;
                }
                
                throw new Error(errorData.error_description || errorData.error || errorData.message || `HTTP error! status: ${response.status}`);
            }

            const responseData = JSON.parse(responseText);
            
            if (responseData.access_token) {
                authState.userAccessToken = responseData.access_token;
                displayToken(responseData.access_token, responseData);
                showStep('success');
                showStatus('Autentifikatsiya muvaffaqiyatli!', 'success');
            } else {
                throw new Error('Access token olinmadi. Javob: ' + JSON.stringify(responseData));
            }
        } catch (apiError) {
            // If API call fails, show auth_code as result
            console.warn('Token exchange failed, showing auth_code:', apiError);
            showStatus('Eslatma: Token exchange endpoint topilmadi. Auth code ni backend da ishlatishingiz kerak.', 'info');
            const authCodeData = {
                auth_code: code,
                session_id: authState.sessionId,
                note: 'Bu auth_code ni backend da ishlatishingiz kerak. Token exchange endpoint MYID dokumentatsiyasida ko\'rsatilmagan.'
            };
            displayToken(code, authCodeData);
            showStep('success');
        }
    } catch (error) {
        showStatus(`Token olishda xatolik: ${error.message}`, 'error');
        showStep('code');
    }
}

function displayToken(token, fullResponse = {}) {
    // If it's auth_code, display it differently
    if (fullResponse.auth_code || fullResponse.note) {
        const authCodeData = {
            auth_code: fullResponse.auth_code || token,
            session_id: fullResponse.session_id || authState.sessionId,
            note: fullResponse.note || 'Bu auth_code ni backend da ishlatishingiz kerak',
            ...fullResponse
        };
        const tokenJson = JSON.stringify(authCodeData, null, 2);
        elements.accessToken.value = tokenJson;
        elements.finalAccessToken.value = tokenJson;
        elements.tokenDisplay.style.display = 'block';
        return;
    }
    
    // Normal access token display
    const tokenData = {
        access_token: token,
        token_type: fullResponse.token_type || 'Bearer',
        expires_in: fullResponse.expires_in,
        refresh_token: fullResponse.refresh_token,
        scope: fullResponse.scope,
        ...fullResponse
    };
    
    const tokenJson = JSON.stringify(tokenData, null, 2);
    elements.accessToken.value = tokenJson;
    elements.finalAccessToken.value = tokenJson;
    elements.tokenDisplay.style.display = 'block';
}

// Utility Functions
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showStatus('Nusxalandi!', 'success');
    }).catch(err => {
        showStatus('Nusxalashda xatolik', 'error');
        console.error('Copy error:', err);
    });
}

function restartAuth() {
    authState = {
        currentStep: 'init',
        backendAccessToken: null,
        sessionId: null,
        authCode: null,
        userAccessToken: null,
        userData: {
            pinfl: null,
            passData: null,
            birthDate: null,
            isResident: true
        }
    };
    
    // Reset form
    elements.userDataForm.reset();
    elements.isResidentCheckbox.checked = true;
    elements.btnSubmitData.disabled = true;
    
    // Reset UI
    showStep('init');
    showStatus('', 'info');
    elements.codeDisplay.style.display = 'none';
    elements.tokenDisplay.style.display = 'none';
    elements.myidIframeContainer.style.display = 'none';
    elements.myidIframe.src = '';
    
    // Clean URL
    window.history.replaceState({}, document.title, window.location.pathname);
}

// Form validation
function validateForm() {
    const passportValue = elements.passportInput.value.trim();
    const birthDateValue = elements.birthDateInput.value;
    
    const passportValidation = validatePassportInput(passportValue);
    const hasBirthDate = !!birthDateValue;
    
    if (passportValidation.valid && hasBirthDate) {
        elements.btnSubmitData.disabled = false;
        return true;
    } else {
        elements.btnSubmitData.disabled = true;
        return false;
    }
}

// Main flow: Create session and initialize MYID
async function createSessionAndInitMYID() {
    try {
        showStatus('Tayyorlanmoqda...', 'info');
        
        // Step 1: Create session (this also returns access_token according to backend response)
        await createSession();
        
        // Step 2: Initialize MYID Web SDK
        await initializeMYIDWebSDK();
        
    } catch (error) {
        showStatus(`Xatolik: ${error.message}`, 'error');
        showStep('init');
    }
}

// Event Listeners
elements.userDataForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const passportValue = elements.passportInput.value.trim();
    const birthDateValue = elements.birthDateInput.value;
    const isResident = elements.isResidentCheckbox.checked;
    
    // Validate input
    const passportValidation = validatePassportInput(passportValue);
    if (!passportValidation.valid) {
        showStatus(passportValidation.error, 'error');
        return;
    }
    
    if (!birthDateValue) {
        showStatus('Tug\'ilgan sanani kiriting', 'error');
        return;
    }
    
    // Store user data
    if (passportValidation.type === 'pinfl') {
        authState.userData.pinfl = passportValidation.value;
        authState.userData.passData = null;
    } else {
        authState.userData.passData = passportValidation.value;
        authState.userData.pinfl = null;
    }
    
    authState.userData.birthDate = birthDateValue;
    authState.userData.isResident = isResident;
    
    // Create session and initialize MYID
    await createSessionAndInitMYID();
});

elements.passportInput.addEventListener('input', (e) => {
    // Auto-format input
    let value = e.target.value.toUpperCase().replace(/\s/g, '');
    
    // If it's a passport format (2 letters + numbers), add space after letters
    if (/^[A-Z]{2}\d+$/.test(value)) {
        value = value.substring(0, 2) + ' ' + value.substring(2);
    }
    
    e.target.value = value;
    validateForm();
});

elements.birthDateInput.addEventListener('input', validateForm);
elements.birthDateInput.addEventListener('change', validateForm);

elements.btnProceedToken.addEventListener('click', () => {
    if (authState.authCode) {
        getUserAccessToken(authState.authCode);
    }
});

elements.btnCopyToken.addEventListener('click', () => {
    copyToClipboard(elements.accessToken.value);
});

elements.btnCopyFinalToken.addEventListener('click', () => {
    copyToClipboard(elements.finalAccessToken.value);
});

elements.btnRestart.addEventListener('click', restartAuth);

elements.btnScanPassport.addEventListener('click', () => {
    showStatus('Skanner funksiyasi tez orada qo\'shiladi', 'info');
    // TODO: Implement passport scanner
});

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
    // Check if we're returning from MYID callback
    handleOAuthCallback();
    
    // Set max date for birth date (today)
    const today = new Date().toISOString().split('T')[0];
    elements.birthDateInput.setAttribute('max', today);
    
    // Set min date (reasonable limit, e.g., 100 years ago)
    const minDate = new Date();
    minDate.setFullYear(minDate.getFullYear() - 100);
    elements.birthDateInput.setAttribute('min', minDate.toISOString().split('T')[0]);
});
