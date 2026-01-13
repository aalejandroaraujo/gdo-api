# WordPress User Sync - Integration Guide

## Overview

This document explains how to sync WordPress users to the GDO Health PostgreSQL database. This enables users who register on WordPress to automatically have an account in the API.

## Operation Model

```
┌─────────────────┐     user_register hook     ┌──────────────────────┐
│    WordPress    │ ────────────────────────►  │  Azure Functions API │
│  (your site)    │   POST /internal/sync-user │  (func-gdo-health)   │
└─────────────────┘                            └──────────┬───────────┘
                                                          │
                                                          ▼
                                               ┌──────────────────────┐
                                               │     PostgreSQL       │
                                               │   (users table)      │
                                               └──────────────────────┘
```

### Sync Behavior

| Scenario | Result |
|----------|--------|
| New WP user, email not in DB | Creates new user (`sync_status: "created"`) |
| WP user already synced | Updates email/display_name (`sync_status: "updated"`) |
| Email exists but no wp_user_id | Links WP ID to existing user (`sync_status: "linked"`) |

### What Gets Synced

- `wp_user_id` - WordPress user ID (integer)
- `email` - User's email address
- `display_name` - User's display name
- `created_at` - WordPress registration timestamp

### What Does NOT Get Synced

- **Passwords are NOT synced** - Users synced from WordPress will need to use the "Forgot Password" flow to set a password for direct API access
- Session data, preferences, etc. are not synced

---

## Security: WP_SYNC_INTERNAL_KEY

### What is it?

A 64-character hex string (256-bit) used to authenticate requests from WordPress to the API. This prevents unauthorized parties from creating users in your database.

### Current Key

```
614ae249196ca5842e08128499a6745e939160fe2a94839e81a2e0bf2abc5ee8
```

> **IMPORTANT**: Store this securely. If compromised, regenerate with:
> ```bash
> az functionapp config appsettings set --name func-gdo-health-prod \
>   --resource-group rg-gdo-health-prod \
>   --settings "WP_SYNC_INTERNAL_KEY=$(openssl rand -hex 32)"
> ```

### How it works

1. WordPress sends `X-Internal-Key` header with every sync request
2. API compares header value to `WP_SYNC_INTERNAL_KEY` environment variable
3. If they don't match, request is rejected with `401 Unauthorized`

---

## WordPress Implementation

### Option A: Add to functions.php (simplest)

Add this code to your WordPress theme's `functions.php`:

```php
/**
 * Sync new WordPress users to GDO Health API
 * Fires when a new user is registered
 */
add_action('user_register', 'gdo_sync_user_to_api');

function gdo_sync_user_to_api($user_id) {
    $user = get_userdata($user_id);
    if (!$user) {
        return;
    }

    // API endpoint and key
    $api_url = 'https://func-gdo-health-prod.azurewebsites.net/api/internal/sync-user';
    $internal_key = 'YOUR_WP_SYNC_INTERNAL_KEY_HERE'; // Replace with actual key

    $response = wp_remote_post($api_url, array(
        'headers' => array(
            'Content-Type' => 'application/json',
            'X-Internal-Key' => $internal_key
        ),
        'body' => json_encode(array(
            'wp_user_id' => $user_id,
            'email' => $user->user_email,
            'display_name' => $user->display_name,
            'created_at' => $user->user_registered
        )),
        'timeout' => 10
    ));

    // Optional: Log errors
    if (is_wp_error($response)) {
        error_log('GDO Sync Error: ' . $response->get_error_message());
    }
}
```

### Option B: Create a Plugin (recommended for production)

Create file `wp-content/plugins/gdo-health-sync/gdo-health-sync.php`:

```php
<?php
/**
 * Plugin Name: GDO Health User Sync
 * Description: Syncs WordPress users to GDO Health API
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;

// Define constants - edit these
define('GDO_API_URL', 'https://func-gdo-health-prod.azurewebsites.net/api/internal/sync-user');
define('GDO_INTERNAL_KEY', 'YOUR_WP_SYNC_INTERNAL_KEY_HERE');

/**
 * Sync user to GDO Health API
 */
function gdo_sync_user($user_id) {
    $user = get_userdata($user_id);
    if (!$user) return;

    $response = wp_remote_post(GDO_API_URL, array(
        'headers' => array(
            'Content-Type' => 'application/json',
            'X-Internal-Key' => GDO_INTERNAL_KEY
        ),
        'body' => json_encode(array(
            'wp_user_id' => $user_id,
            'email' => $user->user_email,
            'display_name' => $user->display_name,
            'created_at' => $user->user_registered
        )),
        'timeout' => 10
    ));

    if (is_wp_error($response)) {
        error_log('[GDO Sync] Error: ' . $response->get_error_message());
        return false;
    }

    $body = json_decode(wp_remote_retrieve_body($response), true);
    if (isset($body['status']) && $body['status'] === 'ok') {
        error_log('[GDO Sync] User ' . $user_id . ' synced: ' . $body['sync_status']);
        return true;
    }

    error_log('[GDO Sync] Failed: ' . wp_remote_retrieve_body($response));
    return false;
}

// Hook into user registration
add_action('user_register', 'gdo_sync_user');

// Optional: Hook into profile updates
add_action('profile_update', 'gdo_sync_user');
```

---

## Syncing Existing Users (Bulk Migration)

For existing WordPress users, you have two options:

### Option 1: PHP Script (run once)

Create `sync-existing-users.php` in WordPress root:

```php
<?php
require_once('wp-load.php');

$api_url = 'https://func-gdo-health-prod.azurewebsites.net/api/internal/sync-user';
$internal_key = 'YOUR_WP_SYNC_INTERNAL_KEY_HERE';

$users = get_users(array('fields' => 'all'));

echo "Syncing " . count($users) . " users...\n";

foreach ($users as $user) {
    $response = wp_remote_post($api_url, array(
        'headers' => array(
            'Content-Type' => 'application/json',
            'X-Internal-Key' => $internal_key
        ),
        'body' => json_encode(array(
            'wp_user_id' => $user->ID,
            'email' => $user->user_email,
            'display_name' => $user->display_name,
            'created_at' => $user->user_registered
        )),
        'timeout' => 10
    ));

    $body = json_decode(wp_remote_retrieve_body($response), true);
    $status = $body['sync_status'] ?? 'error';
    echo "User {$user->ID} ({$user->user_email}): {$status}\n";

    usleep(100000); // 100ms delay to avoid rate limiting
}

echo "Done!\n";
```

Run via CLI: `php sync-existing-users.php`

### Option 2: Export CSV + Python Script

Export users from WordPress admin, then use a Python script to import.

---

## API Reference

### POST /api/internal/sync-user

**Headers:**
```
Content-Type: application/json
X-Internal-Key: <WP_SYNC_INTERNAL_KEY>
```

**Request Body:**
```json
{
    "wp_user_id": 123,
    "email": "user@example.com",
    "display_name": "John Doe",
    "created_at": "2026-01-13T10:00:00Z"
}
```

**Success Response (200):**
```json
{
    "status": "ok",
    "user_id": "e01e48bc-4526-4c7f-bd91-2ae08b1521a8",
    "sync_status": "created"
}
```

**Error Responses:**

| Code | Message | Cause |
|------|---------|-------|
| 401 | Unauthorized | Invalid or missing X-Internal-Key |
| 400 | wp_user_id (integer) is required | Missing or non-integer wp_user_id |
| 400 | Valid email is required | Missing or invalid email |
| 503 | Sync not configured | WP_SYNC_INTERNAL_KEY not set in Azure |
| 500 | Sync failed | Database or server error |

---

## Checklist

- [ ] WP_SYNC_INTERNAL_KEY configured in Azure (done: 2026-01-13)
- [ ] Add PHP hook to WordPress (functions.php or plugin)
- [ ] Replace `YOUR_WP_SYNC_INTERNAL_KEY_HERE` with actual key
- [ ] Test with a new user registration
- [ ] Run bulk sync for existing users (if any)
- [ ] Verify users appear in PostgreSQL `users` table

---

## Troubleshooting

### "Unauthorized" error
- Verify X-Internal-Key header matches WP_SYNC_INTERNAL_KEY in Azure
- Check for extra whitespace in the key

### "Sync not configured" error
- WP_SYNC_INTERNAL_KEY environment variable not set in Azure
- Run: `az functionapp config appsettings list --name func-gdo-health-prod --resource-group rg-gdo-health-prod`

### Users not appearing in database
- Check WordPress error log: `wp-content/debug.log`
- Verify the API URL is correct
- Test manually with curl:
  ```bash
  curl -X POST "https://func-gdo-health-prod.azurewebsites.net/api/internal/sync-user" \
    -H "Content-Type: application/json" \
    -H "X-Internal-Key: YOUR_KEY" \
    -d '{"wp_user_id": 1, "email": "test@example.com"}'
  ```
