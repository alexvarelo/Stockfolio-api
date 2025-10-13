# Stockfolio Financial Data API - Authentication Guide

## Overview

The Stockfolio Financial Data API uses JWT-based authentication with client credentials stored in Supabase. This guide explains how to use the authentication system.

## 🔐 Authentication Flow

### 1. Set Up Client Credentials in Supabase

Client credentials are now managed in Supabase. You need to:

1. **Create a table in Supabase** (if not already created) named `api_clients` with the following schema:
   ```sql
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
   ```

2. **Insert client credentials** into the table:
   ```sql
   INSERT INTO api_clients (client_id, client_secret, name, description)
   VALUES (
     'your_client_id',
     'your_client_secret',
     'My Application',
     'My application for accessing financial data'
   );
   ```

⚠️ **Important**: 
- Store the `client_secret` securely
- You can store secrets as plain text or bcrypt-hashed (the service supports both)
- For better security, hash your secrets using bcrypt before storing

### 2. Get Access Token
Use your client credentials to get a JWT token:

```bash
curl -X POST "http://localhost:8000/api/v1/token" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "client_khuSQjxVmg3bJfcqweXWqw",
    "client_secret": "0_VJOmKMLoNbFCNIGffVx8NCAi5a1ev2ACG52fJVLwc"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 600,
  "expires_at": "2025-08-03T12:13:30.319923"
}
```

### 3. Use the Token
Include the token in the Authorization header for all API requests:

```bash
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  "http://localhost:8000/api/v1/search?query=AAPL&limit=5"
```

## 🔑 API Endpoints

### Authentication Endpoints

#### Get Token
- **POST** `/api/v1/token`
- **Description**: Get JWT access token using client credentials
- **Body**: `{"client_id": "string", "client_secret": "string"}`

#### Get Client Info
- **GET** `/api/v1/clients/me`
- **Description**: Get information about the authenticated client
- **Headers**: `Authorization: Bearer <token>`

### Protected Endpoints

All the following endpoints now require authentication:

#### Search Endpoints
- **GET** `/api/v1/search` - Search for financial instruments
- **GET** `/api/v1/search/popular` - Get popular stocks
- **GET** `/api/v1/search/isin/{isin}` - Search by ISIN

#### Stock Endpoints
- **GET** `/api/v1/stock/{ticker}` - Get comprehensive stock information
- **GET** `/api/v1/stock/{ticker}/price` - Get stock price data
- **GET** `/api/v1/stock/{ticker}/info` - Get company information
- **GET** `/api/v1/stock/{ticker}/history` - Get historical data

## ⚙️ Configuration

### Environment Variables

Add these to your `.env` file:

```env
# JWT Configuration
SECRET_KEY=your-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=10

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
SUPABASE_CLIENTS_TABLE=api_clients

# Database Configuration (legacy, not used for auth)
DATABASE_URL=sqlite:///./stockfolio_api.db
```

### Token Expiration

- **Default**: 10 minutes
- **Configurable**: Via `ACCESS_TOKEN_EXPIRE_MINUTES` environment variable
- **Security**: Tokens are automatically invalidated after expiration

## 🔒 Security Features

### 1. JWT Tokens
- **Algorithm**: HS256
- **Expiration**: 10 minutes (configurable)
- **Claims**: Client ID, expiration, issued at

### 2. Client Credentials
- **Storage**: Stored in Supabase (supports both plain text and bcrypt-hashed)
- **Management**: Managed directly in Supabase dashboard or via SQL
- **Validation**: Verified against Supabase database

### 3. Rate Limiting
- **Built-in**: Protects against abuse
- **Per-client**: Based on client ID
- **Configurable**: Via environment variables

## 📝 Usage Examples

### JavaScript/React Example

```javascript
class FinancialDataAPI {
  constructor(baseURL = 'http://localhost:8000') {
    this.baseURL = baseURL;
    this.token = null;
  }

  // Note: Client creation is now managed in Supabase directly
  // No API endpoint for creating clients

  async getToken(clientId, clientSecret) {
    const response = await fetch(`${this.baseURL}/api/v1/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret })
    });
    const data = await response.json();
    this.token = data.access_token;
    return data;
  }

  async searchStocks(query, limit = 10) {
    const response = await fetch(
      `${this.baseURL}/api/v1/search?query=${query}&limit=${limit}`,
      {
        headers: { 'Authorization': `Bearer ${this.token}` }
      }
    );
    return await response.json();
  }

  async getStockInfo(ticker) {
    const response = await fetch(
      `${this.baseURL}/api/v1/stock/${ticker}`,
      {
        headers: { 'Authorization': `Bearer ${this.token}` }
      }
    );
    return await response.json();
  }
}

// Usage
const api = new FinancialDataAPI();

// 1. Use credentials from Supabase
const clientId = 'your_client_id';
const clientSecret = 'your_client_secret';

// 2. Get token
await api.getToken(clientId, clientSecret);

// 3. Use the API
const stocks = await api.searchStocks('Apple');
const appleInfo = await api.getStockInfo('AAPL');
```

### Python Example

```python
import requests
import json

class FinancialDataAPI:
    def __init__(self, base_url='http://localhost:8000'):
        self.base_url = base_url
        self.token = None

    # Note: Client creation is now managed in Supabase directly
    # No API endpoint for creating clients

    def get_token(self, client_id, client_secret):
        response = requests.post(
            f"{self.base_url}/api/v1/token",
            json={"client_id": client_id, "client_secret": client_secret}
        )
        data = response.json()
        self.token = data['access_token']
        return data

    def search_stocks(self, query, limit=10):
        headers = {'Authorization': f'Bearer {self.token}'}
        response = requests.get(
            f"{self.base_url}/api/v1/search",
            params={'query': query, 'limit': limit},
            headers=headers
        )
        return response.json()

    def get_stock_info(self, ticker):
        headers = {'Authorization': f'Bearer {self.token}'}
        response = requests.get(
            f"{self.base_url}/api/v1/stock/{ticker}",
            headers=headers
        )
        return response.json()

# Usage
api = FinancialDataAPI()

# 1. Use credentials from Supabase
client_id = 'your_client_id'
client_secret = 'your_client_secret'

# 2. Get token
api.get_token(client_id, client_secret)

# 3. Use the API
stocks = api.search_stocks('Apple')
apple_info = api.get_stock_info('AAPL')
```

## 🚨 Error Handling

### Common Error Responses

#### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```
**Solution**: Include valid Authorization header

#### 401 Invalid Token
```json
{
  "detail": "Invalid or expired token"
}
```
**Solution**: Get a new token

#### 401 Invalid Credentials
```json
{
  "detail": "Invalid client credentials"
}
```
**Solution**: Check client_id and client_secret

## 🔧 Database

The authentication system uses Supabase as the backend:

- **api_clients Table**: Stores client credentials in Supabase
- **Managed via Supabase**: Use Supabase dashboard or SQL to manage clients
- **Flexible Storage**: Supports both plain text and bcrypt-hashed secrets

## 🛡️ Security Best Practices

1. **Store Secrets Securely**: Never commit client secrets to version control
2. **Rotate Tokens**: Get new tokens before expiration
3. **HTTPS in Production**: Always use HTTPS in production
4. **Strong Secret Key**: Use a strong SECRET_KEY in production
5. **Rate Limiting**: Implement additional rate limiting if needed

## 🔄 Token Refresh

Currently, tokens expire after 10 minutes. To get a new token:

1. Use the same client credentials
2. Call the `/api/v1/token` endpoint again
3. Replace the old token with the new one

## 📊 Monitoring

You can monitor client usage by checking Supabase:

```sql
-- View all clients
SELECT * FROM api_clients;

-- View active clients
SELECT * FROM api_clients WHERE is_active = true;

-- Disable a client
UPDATE api_clients SET is_active = false WHERE client_id = 'your_client_id';
```

## 🚀 Production Deployment

For production deployment:

1. **Change SECRET_KEY**: Use a strong, random secret key
2. **Use HTTPS**: Always use HTTPS in production
3. **Supabase Setup**: Ensure Supabase is properly configured with RLS policies
4. **Hash Secrets**: Use bcrypt to hash client secrets before storing in Supabase
5. **Environment Variables**: Set all required environment variables (SUPABASE_URL, SUPABASE_KEY)
6. **Monitoring**: Add logging and monitoring for security events

## 🔐 Hashing Client Secrets (Recommended)

For better security, hash your client secrets before storing them in Supabase:

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed_secret = pwd_context.hash("your_plain_text_secret")

# Store hashed_secret in Supabase
```

The authentication system is now fully functional with Supabase backend! 🎉 