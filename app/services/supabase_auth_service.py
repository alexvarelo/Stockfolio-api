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
        logger.info(f"Initializing Supabase client for URL: {settings.SUPABASE_URL}")
        logger.info(f"Supabase table name: {settings.SUPABASE_CLIENTS_TABLE}")
        
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            logger.error("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
        
        try:
            self.supabase: SupabaseClient = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_KEY
            )
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {str(e)}")
            raise
        
        self.table_name = settings.SUPABASE_CLIENTS_TABLE
        logger.info(f"Using table: {self.table_name}")
    
    
    def verify_client_credentials(self, client_id: str, client_secret: str) -> Optional[Dict[str, Any]]:
        """
        Verify client credentials against Supabase database.
        
        Args:
            client_id: The client ID to verify
            client_secret: The client secret to verify
            
        Returns:
            Client data dict if credentials are valid, None otherwise
        """
        logger.info(f"Verifying credentials for client_id: {client_id}")
        
        try:
            # Query Supabase for the client
            logger.info(f"Querying Supabase table '{self.table_name}' for client_id: {client_id}")
            response = self.supabase.table(self.table_name).select("*").eq(
                "client_id", client_id
            ).eq("is_active", True).execute()
            
            logger.info(f"Supabase query executed. Response status: {response}")
            logger.info(f"Response data length: {len(response.data) if response.data else 0}")
            
            if not response.data or len(response.data) == 0:
                logger.warning(f"Client not found or inactive: {client_id}")
                return None
            
            client = response.data[0]
            logger.info(f"Client found: {client.get('name', 'Unknown')} (ID: {client_id})")
            
            # Verify the client secret
            # Check if the stored secret is hashed or plain text
            stored_secret = client.get("client_secret")
            if not stored_secret:
                logger.error(f"No client_secret found for client: {client_id}")
                return None
            
            logger.info(f"Attempting to verify client secret for client: {client_id}")
            
            # Try to verify as hashed password first
            try:
                if pwd_context.verify(client_secret, stored_secret):
                    logger.info(f"Client {client_id} authenticated successfully using hashed password")
                    return client
            except Exception as e:
                logger.warning(f"Hash verification failed for client {client_id}: {str(e)}")
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
        logger.info(f"Authenticating client: {request.client_id}")
        
        client = self.verify_client_credentials(request.client_id, request.client_secret)
        
        if not client:
            logger.warning(f"Authentication failed for client: {request.client_id}")
            return None
        
        logger.info(f"Client authenticated successfully: {request.client_id}")
        
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
        
        logger.info(f"JWT token created for client: {request.client_id}, expires at: {expires_at}")
        
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
        logger.info("Verifying JWT token for client lookup")
        payload = self.verify_token(token)
        if payload is None:
            logger.warning("JWT token verification failed")
            return None
        
        client_id = payload.get("client_id")
        if client_id is None:
            logger.warning("No client_id found in JWT token payload")
            return None
        
        logger.info(f"Fetching client data for client_id: {client_id}")
        
        try:
            # Fetch client from Supabase
            response = self.supabase.table(self.table_name).select("*").eq(
                "client_id", client_id
            ).eq("is_active", True).execute()
            
            if not response.data or len(response.data) == 0:
                logger.warning(f"Client not found or inactive during token verification: {client_id}")
                return None
            
            client = response.data[0]
            logger.info(f"Client data retrieved successfully for: {client.get('name', 'Unknown')} (ID: {client_id})")
            return client
            
        except Exception as e:
            logger.error(f"Error fetching client during token verification: {str(e)}")
            return None
