# Supabase Authentication Setup Guide

## Overview

This API now uses Supabase to store and validate client credentials for authentication. This guide will help you set up the Supabase backend.

## Prerequisites

- A Supabase account (sign up at https://supabase.com)
- A Supabase project created

## Step 1: Create the API Clients Table

1. Go to your Supabase project dashboard
2. Navigate to the SQL Editor
3. Run the following SQL to create the `api_clients` table:

```sql
-- Create the api_clients table
CREATE TABLE api_clients (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id TEXT UNIQUE NOT NULL,
  client_secret TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX idx_api_clients_client_id ON api_clients(client_id);
CREATE INDEX idx_api_clients_is_active ON api_clients(is_active);

-- Add a trigger to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_api_clients_updated_at
BEFORE UPDATE ON api_clients
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
```

## Step 2: Configure Row Level Security (RLS)

For security, enable RLS and create policies:

```sql
-- Enable RLS
ALTER TABLE api_clients ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows the service role to read all clients
CREATE POLICY "Service role can read all clients"
ON api_clients
FOR SELECT
TO service_role
USING (true);

-- Create a policy that allows the service role to insert clients
CREATE POLICY "Service role can insert clients"
ON api_clients
FOR INSERT
TO service_role
WITH CHECK (true);

-- Create a policy that allows the service role to update clients
CREATE POLICY "Service role can update clients"
ON api_clients
FOR UPDATE
TO service_role
USING (true);
```

## Step 3: Insert Your First Client

### Option A: Plain Text Secret (Not Recommended for Production)

```sql
INSERT INTO api_clients (client_id, client_secret, name, description)
VALUES (
  'my_client_id',
  'my_client_secret',
  'My Application',
  'Description of my application'
);
```

### Option B: Hashed Secret (Recommended)

First, hash your secret using Python:

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed_secret = pwd_context.hash("my_client_secret")
print(hashed_secret)
```

Then insert the hashed secret:

```sql
INSERT INTO api_clients (client_id, client_secret, name, description)
VALUES (
  'my_client_id',
  '$2b$12$hashed_secret_here',  -- Replace with your hashed secret
  'My Application',
  'Description of my application'
);
```

## Step 4: Configure Environment Variables

Add the following to your `.env` file:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-anon-or-service-key
SUPABASE_CLIENTS_TABLE=api_clients

# JWT Configuration
SECRET_KEY=your-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=10
```

### Getting Your Supabase Credentials

1. Go to your Supabase project dashboard
2. Navigate to **Settings** > **API**
3. Copy the following:
   - **Project URL** → Use as `SUPABASE_URL`
   - **anon public** key OR **service_role** key → Use as `SUPABASE_KEY`

**Note**: For production, use the `service_role` key and keep it secure. Never expose it in client-side code.

## Step 5: Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

## Step 6: Test the Authentication

Start your API server and test the authentication:

```bash
# Get a token
curl -X POST "http://localhost:8000/api/v1/token" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "my_client_id",
    "client_secret": "my_client_secret"
  }'
```

You should receive a JWT token in response.

## Managing Clients

### View All Clients

```sql
SELECT client_id, name, description, is_active, created_at
FROM api_clients;
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

### Delete a Client

```sql
DELETE FROM api_clients
WHERE client_id = 'client_to_delete';
```

### Update Client Information

```sql
UPDATE api_clients
SET name = 'New Name',
    description = 'New Description'
WHERE client_id = 'client_id_to_update';
```

## Security Best Practices

1. **Use Hashed Secrets**: Always hash client secrets using bcrypt before storing them
2. **Use Service Role Key**: Use the service_role key in your backend, not the anon key
3. **Enable RLS**: Always enable Row Level Security on your tables
4. **Rotate Secrets**: Regularly rotate client secrets
5. **Monitor Access**: Use Supabase's built-in logging to monitor access patterns
6. **HTTPS Only**: Always use HTTPS in production
7. **Environment Variables**: Never commit credentials to version control

## Troubleshooting

### Error: "SUPABASE_URL and SUPABASE_KEY must be set"

Make sure your `.env` file is in the root directory and contains the correct Supabase credentials.

### Error: "Invalid client credentials"

1. Verify the client_id exists in the `api_clients` table
2. Check that `is_active` is set to `true`
3. If using hashed secrets, ensure the hash was generated correctly
4. Try using a plain text secret first to verify the setup

### Error: "relation 'api_clients' does not exist"

Make sure you've created the table in Supabase using the SQL from Step 1.

### Error: "permission denied for table api_clients"

Check your RLS policies and ensure you're using the correct Supabase key (service_role key has more permissions).

## Migration from Local Database

If you were previously using the local SQLite database for authentication:

1. Export your existing clients from SQLite
2. Hash the client secrets if they're not already hashed
3. Insert them into the Supabase `api_clients` table
4. Update your `.env` file with Supabase credentials
5. Restart your API server

The authentication system will automatically use Supabase instead of the local database.
