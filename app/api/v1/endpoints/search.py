from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Optional
import logging

from app.models.schemas import SearchResponse, SearchResult, ErrorResponse
from app.services.search_service import SearchService
from app.core.exceptions import SearchError
from app.core.dependencies import get_current_client
from app.models.database import Client

logger = logging.getLogger(__name__)

router = APIRouter()

def get_search_service() -> SearchService:
    """Dependency to get search service instance"""
    return SearchService()

@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search for financial instruments",
    description="Search for stocks, ETFs, and other financial instruments by name, ISIN, or ticker symbol",
    responses={
        200: {"description": "Search results"},
        400: {"model": ErrorResponse, "description": "Invalid search query"},
        500: {"model": ErrorResponse, "description": "Search service error"}
    }
)
async def search_instruments(
    query: str = Query(..., description="Search query (name, ISIN, or ticker symbol)", min_length=2),
    limit: int = Query(20, description="Maximum number of results to return", ge=1, le=100),
    search_service: SearchService = Depends(get_search_service),
    current_client: Client = Depends(get_current_client)
) -> SearchResponse:
    """
    Search for financial instruments by name, ISIN, or ticker symbol.
    
    This endpoint allows you to search for stocks, ETFs, mutual funds, and other
    financial instruments available on Yahoo Finance.
    
    - **query**: Search term (minimum 2 characters)
    - **limit**: Maximum number of results (1-100)
    
    Returns a list of matching instruments with their basic information.
    """
    try:
        if not query or len(query.strip()) < 2:
            raise HTTPException(
                status_code=400,
                detail="Search query must be at least 2 characters long"
            )
        
        results = search_service.search_instruments(query.strip(), limit)
        
        return SearchResponse(
            query=query.strip(),
            results=results,
            total_count=len(results)
        )
        
    except SearchError as e:
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Unexpected error in search: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/search/popular",
    response_model=List[SearchResult],
    summary="Get popular stocks",
    description="Get a list of popular and widely traded stocks",
    responses={
        200: {"description": "List of popular stocks"},
        500: {"model": ErrorResponse, "description": "Service error"}
    }
)
async def get_popular_stocks(
    search_service: SearchService = Depends(get_search_service),
    current_client: Client = Depends(get_current_client)
) -> List[SearchResult]:
    """
    Get a list of popular and widely traded stocks.
    
    Returns a curated list of major stocks that are commonly traded
    and have high market capitalization.
    """
    try:
        return search_service.get_popular_stocks()
    except Exception as e:
        logger.error(f"Error getting popular stocks: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/search/isin/{isin}",
    response_model=SearchResult,
    summary="Search by ISIN",
    description="Search for a specific financial instrument by ISIN code",
    responses={
        200: {"description": "Instrument found"},
        404: {"model": ErrorResponse, "description": "ISIN not found"},
        500: {"model": ErrorResponse, "description": "Search service error"}
    }
)
async def search_by_isin(
    isin: str,
    search_service: SearchService = Depends(get_search_service),
    current_client: Client = Depends(get_current_client)
) -> SearchResult:
    """
    Search for a financial instrument by its ISIN (International Securities Identification Number).
    
    - **isin**: The ISIN code to search for
    
    Returns the instrument information if found.
    """
    try:
        if not isin or len(isin.strip()) < 5:
            raise HTTPException(
                status_code=400,
                detail="ISIN must be at least 5 characters long"
            )
        
        result = search_service.search_by_isin(isin.strip())
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No instrument found with ISIN: {isin}"
            )
        
        return result
        
    except HTTPException:
        raise
    except SearchError as e:
        logger.error(f"ISIN search error: {str(e)}")
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Unexpected error in ISIN search: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

 