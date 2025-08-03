# Stockfolio Financial Data API - Authentication Guide

## Overview

The Stockfolio Financial Data API now includes JWT-based authentication to secure all endpoints. This guide explains how to use the authentication system.

## 🔐 Authentication Flow

### 1. Create a Client
First, you need to create a client to get credentials:

```bash
curl -X POST "http://localhost:8000/api/v1/clients" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Application",
    "description": "My application for accessing financial data"
  }'
```

**Response:**
```json
{
  "client_id": "client_khuSQjxVmg3bJfcqweXWqw",
  "client_secret": "0_VJOmKMLoNbFCNIGffVx8NCAi5a1ev2ACG52fJVLwc",
  "name": "My Application",
  "description": "My application for accessing financial data",
  "created_at": "2025-08-03T12:03:24"
}
```

⚠️ **Important**: Store the `client_secret` securely. It's only shown once during creation.

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

#### Create Client
- **POST** `/api/v1/clients`
- **Description**: Create a new client with generated credentials
- **Body**: `{"name": "string", "description": "string"}`

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

# Database Configuration
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
- **Storage**: Hashed using bcrypt
- **Generation**: Cryptographically secure random strings
- **Validation**: Database-backed verification

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

  async createClient(name, description) {
    const response = await fetch(`${this.baseURL}/api/v1/clients`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description })
    });
    return await response.json();
  }

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

// 1. Create client (do this once)
const client = await api.createClient('My App', 'Financial data app');

// 2. Get token
await api.getToken(client.client_id, client.client_secret);

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

    def create_client(self, name, description):
        response = requests.post(
            f"{self.base_url}/api/v1/clients",
            json={"name": name, "description": description}
        )
        return response.json()

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

# 1. Create client (do this once)
client = api.create_client('My App', 'Financial data app')

# 2. Get token
api.get_token(client['client_id'], client['client_secret'])

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

The authentication system uses SQLite by default (can be changed to PostgreSQL/MySQL):

- **Clients Table**: Stores client credentials
- **Tokens Table**: For token blacklisting (future feature)
- **Auto-creation**: Tables are created automatically on startup

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

You can monitor client usage by checking the database:

```sql
-- View all clients
SELECT * FROM clients;

-- View client activity (future feature)
SELECT * FROM tokens WHERE client_id = 'your_client_id';
```

## 🚀 Production Deployment

For production deployment:

1. **Change SECRET_KEY**: Use a strong, random secret key
2. **Use HTTPS**: Always use HTTPS in production
3. **Database**: Consider using PostgreSQL or MySQL
4. **Environment Variables**: Set all required environment variables
5. **Monitoring**: Add logging and monitoring for security events

The authentication system is now fully functional and ready for production use! 🎉 