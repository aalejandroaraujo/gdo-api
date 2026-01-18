# Authentication System

**Last Updated:** 2026-01-18

## Overview

GDO Health API uses JWT (JSON Web Tokens) for authentication with a sliding expiration mechanism. This provides a balance between security and user experience.

---

## Token Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| Algorithm | HS256 | HMAC with SHA-256 |
| Lifetime | 1 hour | Token expires 60 minutes after creation |
| Refresh Threshold | 30 minutes | Tokens refreshed when < 30 min remaining |
| Secret Key | `JWT_SIGNING_KEY` env var | Must be set in Azure Function App settings |

---

## How Sliding Expiration Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        TOKEN LIFECYCLE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  0 min          30 min                    60 min               │
│    │              │                         │                   │
│    ├──────────────┼─────────────────────────┤                   │
│    │  NORMAL ZONE │     REFRESH ZONE        │   EXPIRED        │
│    │              │                         │                   │
│    │  No refresh  │  X-New-Token header     │   401 error      │
│    │  needed      │  returned on requests   │   re-login       │
│    │              │                         │   required       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Flow

1. **Login** - User authenticates, receives token (expires in 1 hour)
2. **API Calls (0-30 min)** - Normal operation, no refresh
3. **API Calls (30-60 min)** - Server adds `X-New-Token` header with fresh token
4. **Client Updates** - Client replaces stored token with new one
5. **Session Extends** - New token valid for another hour
6. **Inactivity** - If no calls for 60+ min, token expires, must re-login

---

## Response Headers

When a token needs refresh, these headers are added to the response:

| Header | Value | Description |
|--------|-------|-------------|
| `X-New-Token` | JWT string | The refreshed token |
| `X-Token-Expires-In` | `3600` | Seconds until new token expires |

---

## Client Implementation

### JavaScript/Axios

```javascript
import axios from 'axios';

// Create axios instance
const api = axios.create({
  baseURL: 'https://func-gdo-health-prod.azurewebsites.net/api',
});

// Request interceptor - add token to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor - handle token refresh
api.interceptors.response.use(
  (response) => {
    // Check for refreshed token
    const newToken = response.headers['x-new-token'];
    if (newToken) {
      console.log('Token refreshed');
      localStorage.setItem('token', newToken);
    }
    return response;
  },
  (error) => {
    // Handle 401 - redirect to login
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
```

### React Native/Expo

```javascript
import AsyncStorage from '@react-native-async-storage/async-storage';

const apiCall = async (endpoint, options = {}) => {
  const token = await AsyncStorage.getItem('token');

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  // Handle token refresh
  const newToken = response.headers.get('X-New-Token');
  if (newToken) {
    await AsyncStorage.setItem('token', newToken);
  }

  // Handle 401
  if (response.status === 401) {
    await AsyncStorage.removeItem('token');
    // Navigate to login screen
  }

  return response;
};
```

### Flutter/Dart

```dart
class ApiClient {
  static const String baseUrl = 'https://func-gdo-health-prod.azurewebsites.net/api';

  Future<http.Response> request(String endpoint, {
    String method = 'GET',
    Map<String, dynamic>? body,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('token');

    final response = await http.Request(method, Uri.parse('$baseUrl$endpoint'))
      ..headers['Authorization'] = 'Bearer $token'
      ..headers['Content-Type'] = 'application/json';

    if (body != null) {
      response.body = jsonEncode(body);
    }

    final streamedResponse = await response.send();
    final httpResponse = await http.Response.fromStream(streamedResponse);

    // Handle token refresh
    final newToken = httpResponse.headers['x-new-token'];
    if (newToken != null) {
      await prefs.setString('token', newToken);
    }

    // Handle 401
    if (httpResponse.statusCode == 401) {
      await prefs.remove('token');
      // Navigate to login
    }

    return httpResponse;
  }
}
```

---

## Security Considerations

### Why 1 Hour + Sliding?

| Alternative | Pros | Cons |
|-------------|------|------|
| 24-hour tokens | Simple client | Long exposure if stolen |
| 15-min tokens | Very secure | Poor UX, frequent re-auth |
| Refresh tokens | Best security | Complex, extra storage |
| **1h + sliding** | **Good balance** | **Slightly more complex** |

### Threat Mitigation

| Threat | Mitigation |
|--------|------------|
| Token theft | 1-hour max exposure window |
| Session hijacking | HTTPS only, secure headers |
| Brute force | Rate limiting (Azure front door) |
| Token replay | Short expiry + sliding invalidates old tokens |

### Best Practices

1. **Always use HTTPS** - Never send tokens over HTTP
2. **Secure storage** - Use `localStorage` (web) or `Keychain`/`SecureStorage` (mobile)
3. **Clear on logout** - Remove token when user logs out
4. **Handle 401 gracefully** - Redirect to login, don't expose errors

---

## Endpoints

### POST /api/auth/login

Get a token by authenticating with email/password.

```bash
curl -X POST https://func-gdo-health-prod.azurewebsites.net/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}'
```

Response:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 3600,
  "token_type": "Bearer",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "User Name",
    "account_type": "freemium"
  }
}
```

### POST /api/auth/register

Create a new account.

```bash
curl -X POST https://func-gdo-health-prod.azurewebsites.net/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "SecurePass123!",
    "display_name": "New User",
    "store_history_consent": true
  }'
```

### POST /api/auth/dev-token (Development Only)

Generate a token for testing without password verification.

```bash
curl -X POST https://func-gdo-health-prod.azurewebsites.net/api/auth/dev-token \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test-user-123"}'
```

**Note:** Can be disabled via `DISABLE_DEV_TOKENS=true` environment variable.

---

## Error Responses

| HTTP Code | Message | Cause |
|-----------|---------|-------|
| 401 | Missing Authorization header | No `Authorization` header in request |
| 401 | Invalid Authorization header format | Missing `Bearer ` prefix |
| 401 | Token has expired | Token past expiration (must re-login) |
| 401 | Invalid token | Signature verification failed |
| 500 | Authentication not configured | `JWT_SIGNING_KEY` not set |

---

## Testing Token Refresh

To test sliding expiration locally:

```python
# Create a token that expires in 25 minutes (within refresh zone)
import os
os.environ['JWT_SIGNING_KEY'] = 'test-secret'

from datetime import datetime, timedelta, timezone
import jwt

token = jwt.encode({
    'sub': 'test-user',
    'iat': datetime.now(timezone.utc),
    'exp': datetime.now(timezone.utc) + timedelta(minutes=25)
}, 'test-secret', algorithm='HS256')

print(f"Token: {token}")
# Use this token in API calls - should trigger X-New-Token header
```

---

## Future Considerations

1. **Refresh Tokens** - For longer sessions without re-authentication
2. **Token Revocation** - Blacklist for compromised tokens
3. **Microsoft Entra ID** - Migration path for enterprise SSO
4. **Multi-factor Auth** - Additional security layer

---

## Files

| File | Purpose |
|------|---------|
| [src/auth/middleware.py](../src/auth/middleware.py) | JWT creation, validation, sliding expiration |
| [src/auth/__init__.py](../src/auth/__init__.py) | Module exports |
| [function_app.py](../function_app.py) | Login, register, dev-token endpoints |

---

*See also: [API.md](API.md) for complete endpoint reference*
