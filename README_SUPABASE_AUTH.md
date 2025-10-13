# Supabase Authentication Implementation

## 🎉 Overview

The authentication system has been successfully migrated from local SQLite to **Supabase**. Client credentials (clientId/clientSecret) are now stored and validated against your Supabase database.

## 📋 What's New

### ✅ Implemented Features

1. **Supabase Integration**
   - New `SupabaseAuthService` for authentication
   - Validates credentials against Supabase database
   - Supports both plain text and bcrypt-hashed secrets

2. **Updated Endpoints**
   - `/api/v1/token` - Get JWT token (unchanged for clients)
   - `/api/v1/clients/me` - Get current client info (unchanged for clients)
   - ~~`/api/v1/clients` POST~~ - **REMOVED** (create clients in Supabase directly)

3. **New Configuration**
   - `SUPABASE_URL` - Your Supabase project URL
   - `SUPABASE_KEY` - Your Supabase API key (service role recommended)
   - `SUPABASE_CLIENTS_TABLE` - Table name for clients (default: `api_clients`)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Supabase

Follow the detailed guide in [`SUPABASE_SETUP.md`](./SUPABASE_SETUP.md) to:
- Create the `api_clients` table
- Set up Row Level Security (RLS)
- Insert your first client

### 3. Configure Environment Variables

Create a `.env` file (or copy from `.env.example`):

```env
# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-service-role-key
SUPABASE_CLIENTS_TABLE=api_clients

# JWT Configuration
SECRET_KEY=your-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=10
```

### 4. Start the API

```bash
uvicorn app.main:app --reload
```

## 📚 Documentation Files

- **[SUPABASE_SETUP.md](./SUPABASE_SETUP.md)** - Complete setup guide for Supabase
- **[AUTHENTICATION_GUIDE.md](./AUTHENTICATION_GUIDE.md)** - Updated authentication guide
- **[MIGRATION_SUMMARY.md](./MIGRATION_SUMMARY.md)** - Detailed migration information
- **[.env.example](./.env.example)** - Example environment variables

## 🔑 Creating Clients

Clients are now created directly in Supabase, not via the API.

### Option 1: Plain Text Secret (Quick Start)

```sql
INSERT INTO api_clients (client_id, client_secret, name, description)
VALUES (
  'my_app_client',
  'my_secret_key_123',
  'My Application',
  'Description of my application'
);
```

### Option 2: Hashed Secret (Recommended for Production)

First, hash your secret:

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = pwd_context.hash("my_secret_key_123")
print(hashed)
```

Then insert:

```sql
INSERT INTO api_clients (client_id, client_secret, name, description)
VALUES (
  'my_app_client',
  '$2b$12$hashed_secret_here',
  'My Application',
  'Description of my application'
);
```

## 🔐 Using the API (No Changes for Clients)

The authentication flow remains the same for API consumers:

### 1. Get Token

```bash
curl -X POST "http://localhost:8000/api/v1/token" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "my_app_client",
    "client_secret": "my_secret_key_123"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 600,
  "expires_at": "2025-10-13T12:00:00"
}
```

### 2. Use Token

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/v1/search?query=AAPL"
```

## 🛠️ Managing Clients

### View All Clients

```sql
SELECT client_id, name, description, is_active, created_at
FROM api_clients
ORDER BY created_at DESC;
```

### Disable a Client

```sql
UPDATE api_clients
SET is_active = false
WHERE client_id = 'client_to_disable';
```

### Enable a Client

```sql
UPDATE api_clients
SET is_active = true
WHERE client_id = 'client_to_enable';
```

### Update Client Info

```sql
UPDATE api_clients
SET name = 'New Name',
    description = 'New Description'
WHERE client_id = 'my_app_client';
```

### Delete a Client

```sql
DELETE FROM api_clients
WHERE client_id = 'client_to_delete';
```

## 🔒 Security Best Practices

1. **Use Service Role Key**: Use the `service_role` key in your backend, not the `anon` key
2. **Hash Secrets**: Always hash client secrets using bcrypt in production
3. **Enable RLS**: Always enable Row Level Security on your Supabase tables
4. **HTTPS Only**: Always use HTTPS in production
5. **Rotate Secrets**: Regularly rotate client secrets
6. **Monitor Access**: Use Supabase's built-in logging to monitor access patterns
7. **Environment Variables**: Never commit credentials to version control

## 📊 Architecture

```
Client Request
     ↓
API Endpoint (FastAPI)
     ↓
SupabaseAuthService
     ↓
Supabase Database (api_clients table)
     ↓
Validate Credentials
     ↓
Generate JWT Token
     ↓
Return Token to Client
```

## 🔄 Migration from Old System

If you were using the old SQLite-based authentication:

1. Export existing clients from SQLite
2. Hash the secrets if not already hashed
3. Import into Supabase `api_clients` table
4. Update `.env` with Supabase credentials
5. Restart the API

See [MIGRATION_SUMMARY.md](./MIGRATION_SUMMARY.md) for detailed migration steps.

## ⚠️ Breaking Changes

- **Removed Endpoint**: `/api/v1/clients` POST endpoint has been removed
- **Client Creation**: Clients must now be created directly in Supabase
- **Database**: Local SQLite is no longer used for authentication

## ✅ Benefits

1. **Centralized Management**: All credentials in Supabase
2. **Better Scalability**: Supabase handles database scaling
3. **Built-in Features**: RLS, logging, monitoring out of the box
4. **Easier Management**: Use Supabase dashboard for client management
5. **No Local Database**: No SQLite files to manage for auth

## 🐛 Troubleshooting

### Error: "SUPABASE_URL and SUPABASE_KEY must be set"

- Ensure your `.env` file exists in the root directory
- Check that `SUPABASE_URL` and `SUPABASE_KEY` are set correctly

### Error: "Invalid client credentials"

- Verify the client exists in Supabase
- Check that `is_active` is `true`
- If using hashed secrets, ensure the hash is correct
- Try plain text first to verify setup

### Error: "relation 'api_clients' does not exist"

- Run the table creation SQL from `SUPABASE_SETUP.md`

### Error: "permission denied for table api_clients"

- Check your RLS policies
- Ensure you're using the correct Supabase key (service_role has more permissions)

## 📞 Support

For detailed setup instructions, see:
- [SUPABASE_SETUP.md](./SUPABASE_SETUP.md)
- [AUTHENTICATION_GUIDE.md](./AUTHENTICATION_GUIDE.md)
- [MIGRATION_SUMMARY.md](./MIGRATION_SUMMARY.md)

## 🎯 Next Steps

1. ✅ Install dependencies: `pip install -r requirements.txt`
2. ✅ Set up Supabase table (see SUPABASE_SETUP.md)
3. ✅ Configure environment variables
4. ✅ Create your first client in Supabase
5. ✅ Test authentication with `/api/v1/token`
6. ✅ Start using the API!

---

**Ready to go!** Your authentication system is now powered by Supabase. 🚀
