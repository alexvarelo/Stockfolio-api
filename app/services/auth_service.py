from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import secrets
import logging

from app.models.database import Client, Token
from app.models.auth import TokenRequest, TokenResponse, CreateClientRequest, CreateClientResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    """Service for handling authentication and authorization"""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 10  # 10 minutes as requested
    
    def verify_client_credentials(self, db: Session, client_id: str, client_secret: str) -> Optional[Client]:
        """Verify client credentials"""
        try:
            client = db.query(Client).filter(
                Client.client_id == client_id,
                Client.is_active == True
            ).first()
            
            if client and pwd_context.verify(client_secret, client.client_secret):
                return client
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
    
    def generate_client_credentials(self) -> tuple[str, str]:
        """Generate client ID and secret"""
        client_id = f"client_{secrets.token_urlsafe(16)}"
        client_secret = secrets.token_urlsafe(32)
        return client_id, client_secret
    
    def create_client(self, db: Session, request: CreateClientRequest) -> CreateClientResponse:
        """Create a new client"""
        client_id, client_secret = self.generate_client_credentials()
        hashed_secret = pwd_context.hash(client_secret)
        
        client = Client(
            client_id=client_id,
            client_secret=hashed_secret,
            name=request.name,
            description=request.description
        )
        
        db.add(client)
        db.commit()
        db.refresh(client)
        
        return CreateClientResponse(
            client_id=client_id,
            client_secret=client_secret,  # Return unhashed secret for initial setup
            name=client.name,
            description=client.description,
            created_at=client.created_at
        )
    
    def authenticate_client(self, db: Session, request: TokenRequest) -> Optional[TokenResponse]:
        """Authenticate client and return token"""
        client = self.verify_client_credentials(db, request.client_id, request.client_secret)
        
        if not client:
            return None
        
        # Create token
        access_token_expires = timedelta(minutes=self.access_token_expire_minutes)
        access_token = self.create_access_token(
            data={"sub": client.client_id, "client_id": client.client_id},
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
    
    def get_current_client(self, db: Session, token: str) -> Optional[Client]:
        """Get current client from token"""
        payload = self.verify_token(token)
        if payload is None:
            return None
        
        client_id = payload.get("client_id")
        if client_id is None:
            return None
        
        client = db.query(Client).filter(
            Client.client_id == client_id,
            Client.is_active == True
        ).first()
        
        return client 