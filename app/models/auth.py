from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ErrorResponse(BaseModel):
    """Schema for error responses"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    status_code: int = Field(..., description="HTTP status code")

class TokenRequest(BaseModel):
    """Schema for token request"""
    client_id: str = Field(..., description="Client ID")
    client_secret: str = Field(..., description="Client Secret")

class TokenResponse(BaseModel):
    """Schema for token response"""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    expires_at: datetime = Field(..., description="Token expiration timestamp")

class ClientCredentials(BaseModel):
    """Schema for client credentials"""
    client_id: str = Field(..., description="Client ID")
    client_secret: str = Field(..., description="Client Secret")
    name: str = Field(..., description="Client name")
    description: Optional[str] = Field(None, description="Client description")
    is_active: bool = Field(default=True, description="Whether client is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

class CreateClientRequest(BaseModel):
    """Schema for creating a new client"""
    name: str = Field(..., description="Client name")
    description: Optional[str] = Field(None, description="Client description")

class CreateClientResponse(BaseModel):
    """Schema for client creation response"""
    client_id: str = Field(..., description="Generated client ID")
    client_secret: str = Field(..., description="Generated client secret")
    name: str = Field(..., description="Client name")
    description: Optional[str] = Field(None, description="Client description")
    created_at: datetime = Field(..., description="Creation timestamp") 