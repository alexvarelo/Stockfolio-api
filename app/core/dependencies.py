from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.services.auth_service import AuthService
from app.models.database import Client

security = HTTPBearer()

def get_auth_service() -> AuthService:
    """Dependency to get auth service instance"""
    return AuthService()

def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
) -> Client:
    """
    Dependency to get the current authenticated client.
    
    This dependency verifies the JWT token and returns the associated client.
    Use this to protect endpoints that require authentication.
    """
    token = credentials.credentials
    client = auth_service.get_current_client(db, token)
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return client 