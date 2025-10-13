# Authentication Migration Summary

## Overview

The authentication system has been migrated from a local SQLite database to **Supabase** for storing and validating client credentials.

## What Changed

### 1. **New Supabase Authentication Service**
   - Created `app/services/supabase_auth_service.py`
   - Validates client credentials against Supabase database
   - Supports both plain text and bcrypt-hashed secrets
   - Maintains JWT token generation and validation

### 2. **Updated Authentication Endpoints**
   - Modified `app/api/v1/endpoints/auth.py` to use `SupabaseAuthService`
   - **Removed** `/api/v1/clients` POST endpoint (client creation)
   - **Kept** `/api/v1/token` POST endpoint (get JWT token)
   - **Kept** `/api/v1/clients/me` GET endpoint (get current client info)

### 3. **Configuration Updates**
   - Added Supabase configuration to `app/core/config.py`:
     - `SUPABASE_URL`
     - `SUPABASE_KEY`
     - `SUPABASE_CLIENTS_TABLE`
   - Created `.env.example` with required environment variables

### 4. **Dependencies**
   - Added `supabase==2.3.0` to `requirements.txt`

### 5. **Documentation**
   - Updated `AUTHENTICATION_GUIDE.md` with Supabase-specific instructions
   - Created `SUPABASE_SETUP.md` with detailed setup guide
   - Created this migration summary

## Breaking Changes

### ⚠️ Client Creation Endpoint Removed

The `/api/v1/clients` POST endpoint has been **removed**. Clients must now be created directly in Supabase.

**Before:**
```bash
curl -X POST "http://localhost:8000/api/v1/clients" \
  -H "Content-Type: application/json" \
  -d '{"name": "My App", "description": "My description"}'
```

**After:**
```sql
-- Create client in Supabase
INSERT INTO api_clients (client_id, client_secret, name, description)
VALUES ('my_client_id', 'my_client_secret', 'My App', 'My description');
```

## Migration Steps

### For New Installations

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up Supabase:**
   - Follow the instructions in `SUPABASE_SETUP.md`
   - Create the `api_clients` table
   - Insert your first client

3. **Configure environment variables:**
   - Copy `.env.example` to `.env`
   - Fill in your Supabase credentials

4. **Start the API:**
   ```bash
   uvicorn app.main:app --reload
   ```

### For Existing Installations

1. **Install new dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up Supabase:**
   - Follow the instructions in `SUPABASE_SETUP.md`
   - Create the `api_clients` table

3. **Migrate existing clients (if any):**
   ```python
   # Export from SQLite
   import sqlite3
   conn = sqlite3.connect('stockfolio_api.db')
   cursor = conn.cursor()
   cursor.execute("SELECT client_id, client_secret, name, description FROM clients WHERE is_active = 1")
   clients = cursor.fetchall()
   
   # Import to Supabase (using Supabase dashboard or SQL)
   # Note: client_secret is already hashed in SQLite
   ```

4. **Update environment variables:**
   - Add Supabase credentials to your `.env` file
   - Keep existing variables for backward compatibility

5. **Restart the API:**
   ```bash
   uvicorn app.main:app --reload
   ```

## Authentication Flow (Unchanged)

The authentication flow remains the same for API consumers:

1. **Get Token:**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/token" \
     -H "Content-Type: application/json" \
     -d '{"client_id": "your_id", "client_secret": "your_secret"}'
   ```

2. **Use Token:**
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     "http://localhost:8000/api/v1/search?query=AAPL"
   ```

## Benefits

1. **Centralized Management**: All client credentials in one place (Supabase)
2. **Better Scalability**: Supabase handles database scaling
3. **Built-in Features**: Leverage Supabase's RLS, logging, and monitoring
4. **Easier Management**: Use Supabase dashboard for client management
5. **No Local Database**: No need to manage SQLite files for auth

## Security Improvements

1. **Row Level Security (RLS)**: Protect data at the database level
2. **Flexible Secret Storage**: Support for both plain text and hashed secrets
3. **Centralized Audit Logs**: Track all authentication attempts in Supabase
4. **Easy Revocation**: Disable clients instantly via Supabase

## Backward Compatibility

- JWT tokens remain compatible
- Token expiration settings unchanged
- Protected endpoints work the same way
- No changes required for API consumers (except client creation)

## Testing

Test the authentication system:

```bash
# 1. Create a test client in Supabase
INSERT INTO api_clients (client_id, client_secret, name)
VALUES ('test_client', 'test_secret', 'Test Client');

# 2. Get a token
curl -X POST "http://localhost:8000/api/v1/token" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "test_client", "client_secret": "test_secret"}'

# 3. Use the token
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/clients/me"
```

## Troubleshooting

See `SUPABASE_SETUP.md` for common issues and solutions.

## Support

For questions or issues:
1. Check `SUPABASE_SETUP.md` for setup instructions
2. Check `AUTHENTICATION_GUIDE.md` for usage examples
3. Review Supabase logs for authentication errors
4. Check API logs for detailed error messages
