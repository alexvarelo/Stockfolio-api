from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import logging

from app.core.database import get_db
from app.services.auth_service import AuthService
from app.models.auth import TokenRequest, TokenResponse, CreateClientRequest, CreateClientResponse, ErrorResponse
from app.models.database import Client

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

def get_auth_service() -> AuthService:
    """Dependency to get auth service instance"""
    return AuthService()

@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Get access token",
    description="Authenticate with client credentials and get JWT access token",
    responses={
        200: {"description": "Token generated successfully"},
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_token(
    request: TokenRequest,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    """
    Get JWT access token using client credentials.
    
    This endpoint authenticates clients using their client ID and client secret,
    and returns a JWT token that can be used to access protected endpoints.
    
    - **client_id**: Your client ID
    - **client_secret**: Your client secret
    
    Returns a JWT token valid for 10 minutes.
    """
    try:
        token_response = auth_service.authenticate_client(db, request)
        
        if not token_response:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid client credentials"
            )
        
        return token_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token generation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post(
    "/clients",
    response_model=CreateClientResponse,
    summary="Create new client",
    description="Create a new client with generated credentials",
    responses={
        201: {"description": "Client created successfully"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def create_client(
    request: CreateClientRequest,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
) -> CreateClientResponse:
    """
    Create a new client with generated credentials.
    
    This endpoint creates a new client and returns the client ID and secret.
    Store these credentials securely as they will be needed for authentication.
    
    - **name**: Client name
    - **description**: Optional client description
    
    Returns generated client ID and secret.
    """
    try:
        client_response = auth_service.create_client(db, request)
        return client_response
        
    except Exception as e:
        logger.error(f"Client creation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create client"
        )

@router.get(
    "/clients/me",
    summary="Get current client info",
    description="Get information about the authenticated client",
    responses={
        200: {"description": "Client information"},
        401: {"model": ErrorResponse, "description": "Invalid token"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Get information about the authenticated client.
    
    This endpoint returns information about the client associated with the provided JWT token.
    """
    try:
        token = credentials.credentials
        client = auth_service.get_current_client(db, token)
        
        if not client:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        
        return {
            "client_id": client.client_id,
            "name": client.name,
            "description": client.description,
            "is_active": client.is_active,
            "created_at": client.created_at,
            "updated_at": client.updated_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get client info error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        ) 