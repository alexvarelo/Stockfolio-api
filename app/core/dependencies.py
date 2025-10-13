from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any

from app.services.supabase_auth_service import SupabaseAuthService

security = HTTPBearer()

def get_auth_service() -> SupabaseAuthService:
    """Dependency to get Supabase auth service instance"""
    return SupabaseAuthService()

def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: SupabaseAuthService = Depends(get_auth_service)
) -> Dict[str, Any]:
    """
    Dependency to get the current authenticated client.
    
    This dependency verifies the JWT token and returns the associated client data.
    Use this to protect endpoints that require authentication.
    """
    token = credentials.credentials
    client = auth_service.get_current_client(token)
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return client 