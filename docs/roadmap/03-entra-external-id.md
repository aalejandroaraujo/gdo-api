# Phase 3: Microsoft Entra External ID

**Status:** Not Started

---

## Objective

Migrate from self-signed JWT authentication to Microsoft Entra External ID, Microsoft's enterprise-grade Customer Identity and Access Management (CIAM) platform. This replaces the deprecated Azure AD B2C.

---

## Why Entra External ID?

| Feature | Self-Signed JWT | Entra External ID |
|---------|-----------------|-------------------|
| User registration | Manual | Built-in UI flows |
| Password reset | Manual | Built-in |
| Social logins | Not supported | Google, Facebook, Apple, etc. |
| MFA | Not supported | Built-in |
| User management | Custom | Azure Portal |
| Compliance | Manual | SOC 2, ISO 27001, GDPR |
| Token refresh | Manual | Automatic |
| Mobile SDK | None | MSAL (official) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Mobile App                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  MSAL (Microsoft Authentication Library)                │    │
│  │  - Login/Signup flows                                   │    │
│  │  - Token acquisition                                    │    │
│  │  - Token refresh                                        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (1) Redirect to login
┌─────────────────────────────────────────────────────────────────┐
│              Microsoft Entra External ID                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  User Flows                                             │    │
│  │  - Sign up with email                                   │    │
│  │  - Sign in                                              │    │
│  │  - Password reset                                       │    │
│  │  - Profile edit                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼ (2) Issue JWT token               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (3) Bearer token in API calls
┌─────────────────────────────────────────────────────────────────┐
│                    Azure Function App                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Auth Middleware                                        │    │
│  │  - Validate Entra-issued JWT                            │    │
│  │  - Verify issuer, audience, signature                   │    │
│  │  - Extract user claims (sub, email, name)               │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Setup Steps

### Step 1: Create External ID Tenant

1. Go to [Microsoft Entra admin center](https://entra.microsoft.com)
2. Navigate to **Identity** → **External Identities** → **External tenants**
3. Click **Create a new external tenant**
4. Configure:
   - Tenant name: `GDO Health`
   - Domain: `gdohealth.onmicrosoft.com`
   - Location: Switzerland

### Step 2: Configure Branding

1. In the External ID tenant, go to **User experiences** → **Branding**
2. Upload logo, set colors to match GDO Health brand
3. Configure sign-in page text in Spanish

### Step 3: Register Mobile App

1. Go to **Applications** → **App registrations** → **New registration**
2. Configure:
   - Name: `GDO Health Mobile`
   - Supported account types: Customers only
   - Redirect URI (Mobile): `msauth://com.gdohealth.app/callback`
   - Redirect URI (Dev): `exp://localhost:8081`

3. Note the **Application (client) ID**

### Step 4: Register Backend API

1. Create another app registration for the API
2. Configure:
   - Name: `GDO Health API`
   - Supported account types: Customers only

3. Go to **Expose an API**:
   - Set Application ID URI: `api://gdo-health-api`
   - Add scope: `access_as_user`

4. Go to **App roles** (optional):
   - Add roles: `User`, `Premium`, `Admin`

### Step 5: Configure User Flows

1. Go to **User flows**
2. Create **Sign up and sign in** flow:
   - Collect: Email, Display Name
   - Enable email verification

3. Create **Password reset** flow

4. Create **Profile edit** flow (optional)

### Step 6: Grant API Permissions

1. In Mobile App registration, go to **API permissions**
2. Add permission → My APIs → GDO Health API → `access_as_user`
3. Grant admin consent

---

## Code Changes

### Update Auth Middleware

Replace self-signed JWT validation with Entra token validation:

```python
# src/auth/middleware.py
import jwt
from jwt import PyJWKClient
import os

TENANT_ID = os.environ.get("ENTRA_TENANT_ID")
CLIENT_ID = os.environ.get("ENTRA_API_CLIENT_ID")
ISSUER = f"https://{TENANT_ID}.ciamlogin.com/{TENANT_ID}/v2.0"
JWKS_URL = f"https://{TENANT_ID}.ciamlogin.com/{TENANT_ID}/discovery/v2.0/keys"

# Cache the JWKS client
jwks_client = PyJWKClient(JWKS_URL)

def validate_token(token: str) -> dict:
    """Validate Microsoft Entra External ID token."""
    try:
        # Get the signing key from JWKS endpoint
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Decode and validate
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=ISSUER
        )
        return payload

    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {str(e)}")
```

### Update Function App Settings

```bash
az functionapp config appsettings set \
    --name func-gdo-health-prod \
    --resource-group rg-gdo-health-prod \
    --settings \
        "ENTRA_TENANT_ID=<your-external-id-tenant-id>" \
        "ENTRA_API_CLIENT_ID=<your-api-client-id>"
```

### Mobile App Integration (React Native/Expo)

```typescript
// Using @azure/msal-react-native
import { PublicClientApplication } from '@azure/msal-react-native';

const msalConfig = {
  auth: {
    clientId: '<mobile-app-client-id>',
    authority: 'https://<tenant>.ciamlogin.com/',
    redirectUri: 'msauth://com.gdohealth.app/callback',
  },
};

const pca = new PublicClientApplication(msalConfig);

// Sign in
const result = await pca.acquireToken({
  scopes: ['api://gdo-health-api/access_as_user'],
});

// Use token in API calls
const response = await fetch('https://func-gdo-health-prod.azurewebsites.net/api/endpoint', {
  headers: {
    'Authorization': `Bearer ${result.accessToken}`,
  },
});
```

---

## Migration Strategy

### Phase 3a: Parallel Support

1. Deploy Entra validation alongside existing self-signed JWT
2. Accept both token types during transition
3. Test with new mobile app builds

```python
def validate_token(token: str) -> dict:
    """Support both Entra and legacy tokens during migration."""
    try:
        # Try Entra validation first
        return validate_entra_token(token)
    except AuthError:
        # Fall back to legacy self-signed JWT
        return validate_legacy_token(token)
```

### Phase 3b: Full Migration

1. Update all mobile app users to new version
2. Monitor for legacy token usage
3. Remove legacy token support
4. Delete self-signed JWT secret from Key Vault

---

## User Migration

If you have existing users in the database:

1. **Option A: Invite users** - Send email invitations to existing users
2. **Option B: Self-service** - Users create new accounts, link by email
3. **Option C: Bulk import** - Use Microsoft Graph API to create users

```bash
# Bulk import via Graph API
POST https://graph.microsoft.com/v1.0/users
{
  "displayName": "User Name",
  "identities": [{
    "signInType": "emailAddress",
    "issuer": "<tenant>.onmicrosoft.com",
    "issuerAssignedId": "user@email.com"
  }],
  "passwordProfile": {
    "forceChangePasswordNextSignIn": true
  }
}
```

---

## Tasks Checklist

- [ ] Create External ID tenant
- [ ] Configure branding (logo, colors, Spanish text)
- [ ] Register Mobile App
- [ ] Register Backend API with scopes
- [ ] Create user flows (sign up, sign in, password reset)
- [ ] Update `src/auth/middleware.py` for Entra validation
- [ ] Add MSAL to mobile app
- [ ] Test end-to-end authentication flow
- [ ] Migrate existing users (if any)
- [ ] Remove legacy self-signed JWT support
- [ ] Update documentation

---

## Cost Estimate

Microsoft Entra External ID pricing (as of 2026):

| Tier | Monthly Active Users | Price |
|------|---------------------|-------|
| Free | First 50,000 MAU | $0 |
| P1 | 50,001+ MAU | ~$0.01/MAU |

For GDO Health's expected scale (hundreds to low thousands), this will likely remain in the free tier.

---

## Resources

- [Microsoft Entra External ID Documentation](https://learn.microsoft.com/en-us/entra/external-id/customers/)
- [MSAL React Native](https://github.com/AzureAD/microsoft-authentication-library-for-js)
- [External ID Pricing](https://azure.microsoft.com/en-us/pricing/details/active-directory/external-identities/)
- [Migration Guide from B2C](https://learn.microsoft.com/en-us/entra/external-id/customers/concept-migrate-from-b2c)

---

*Previous Phase: [02-function-app-deployment.md](./02-function-app-deployment.md)*
