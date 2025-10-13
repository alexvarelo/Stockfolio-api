from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from app.services.supabase_auth_service import SupabaseAuthService
from app.models.auth import TokenRequest, TokenResponse, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

def get_auth_service() -> SupabaseAuthService:
    """Dependency to get Supabase auth service instance"""
    return SupabaseAuthService()

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
    auth_service: SupabaseAuthService = Depends(get_auth_service)
) -> TokenResponse:
    """
    Get JWT access token using client credentials.
    
    This endpoint authenticates clients using their client ID and client secret,
    and returns a JWT token that can be used to access protected endpoints.
    
    - **client_id**: Your client ID
    - **client_secret**: Your client secret
    
    Returns a JWT token valid for 10 minutes.
    """
    logger.info(f"Token request received for client_id: {request.client_id}")
    logger.info(f"Request data: client_id={request.client_id}, has_secret={bool(request.client_secret)}")
    
    try:
        token_response = auth_service.authenticate_client(request)
        
        if not token_response:
            logger.warning(f"Authentication failed for client_id: {request.client_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid client credentials"
            )
        
        logger.info(f"Token generated successfully for client_id: {request.client_id}")
        return token_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token generation error for client_id {request.client_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

# Note: Client creation is now managed directly in Supabase.
# Clients should be created manually in the Supabase dashboard or via Supabase API.
# This endpoint has been removed as credentials are stored in Supabase.

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
    auth_service: SupabaseAuthService = Depends(get_auth_service)
):
    """
    Get information about the authenticated client.
    
    This endpoint returns information about the client associated with the provided JWT token.
    """
    logger.info("Client info request received")
    logger.info(f"Token prefix: {credentials.scheme}")
    logger.info(f"Token length: {len(credentials.credentials)}")
    
    try:
        token = credentials.credentials
        client = auth_service.get_current_client(token)
        
        if not client:
            logger.warning("Client lookup failed - invalid or expired token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        
        logger.info(f"Client info retrieved for: {client.get('name', 'Unknown')} (ID: {client.get('client_id')})")
        return {
            "client_id": client.get("client_id"),
            "name": client.get("name"),
            "description": client.get("description"),
            "is_active": client.get("is_active"),
            "created_at": client.get("created_at"),
            "updated_at": client.get("updated_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get client info error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        ) 