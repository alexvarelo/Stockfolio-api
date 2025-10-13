from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
import logging
from supabase import create_client, Client as SupabaseClient

from app.models.auth import TokenRequest, TokenResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class SupabaseAuthService:
    """Service for handling authentication using Supabase as the backend"""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = "HS256"
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        
        # Initialize Supabase client
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
        
        self.supabase: SupabaseClient = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )
        self.table_name = settings.SUPABASE_CLIENTS_TABLE
    
    def verify_client_credentials(self, client_id: str, client_secret: str) -> Optional[Dict[str, Any]]:
        """
        Verify client credentials against Supabase database.
        
        Args:
            client_id: The client ID to verify
            client_secret: The client secret to verify
            
        Returns:
            Client data dict if credentials are valid, None otherwise
        """
        try:
            # Query Supabase for the client
            response = self.supabase.table(self.table_name).select("*").eq(
                "client_id", client_id
            ).eq("is_active", True).execute()
            
            if not response.data or len(response.data) == 0:
                logger.warning(f"Client not found or inactive: {client_id}")
                return None
            
            client = response.data[0]
            
            # Verify the client secret
            # Check if the stored secret is hashed or plain text
            stored_secret = client.get("client_secret")
            if not stored_secret:
                logger.error(f"No client_secret found for client: {client_id}")
                return None
            
            # Try to verify as hashed password first
            try:
                if pwd_context.verify(client_secret, stored_secret):
                    return client
            except Exception:
                # If verification fails, try plain text comparison
                if client_secret == stored_secret:
                    logger.warning(f"Client {client_id} is using plain text password. Consider hashing it.")
                    return client
            
            logger.warning(f"Invalid credentials for client: {client_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error verifying client credentials: {str(e)}")
            return None
    
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire, "iat": datetime.utcnow()})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            logger.error(f"JWT verification failed: {str(e)}")
            return None
    
    def authenticate_client(self, request: TokenRequest) -> Optional[TokenResponse]:
        """
        Authenticate client and return token.
        
        Args:
            request: TokenRequest containing client_id and client_secret
            
        Returns:
            TokenResponse with JWT token if authentication successful, None otherwise
        """
        client = self.verify_client_credentials(request.client_id, request.client_secret)
        
        if not client:
            return None
        
        # Create token
        access_token_expires = timedelta(minutes=self.access_token_expire_minutes)
        access_token = self.create_access_token(
            data={
                "sub": client["client_id"],
                "client_id": client["client_id"],
                "name": client.get("name", "")
            },
            expires_delta=access_token_expires
        )
        
        # Calculate expiration
        expires_at = datetime.utcnow() + access_token_expires
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=self.access_token_expire_minutes * 60,  # Convert to seconds
            expires_at=expires_at
        )
    
    def get_current_client(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get current client from token.
        
        Args:
            token: JWT token string
            
        Returns:
            Client data dict if token is valid, None otherwise
        """
        payload = self.verify_token(token)
        if payload is None:
            return None
        
        client_id = payload.get("client_id")
        if client_id is None:
            return None
        
        try:
            # Fetch client from Supabase
            response = self.supabase.table(self.table_name).select("*").eq(
                "client_id", client_id
            ).eq("is_active", True).execute()
            
            if not response.data or len(response.data) == 0:
                return None
            
            return response.data[0]
            
        except Exception as e:
            logger.error(f"Error fetching client: {str(e)}")
            return None
