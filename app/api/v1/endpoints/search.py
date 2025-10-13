from fastapi import APIRouter, Query, HTTPException, Depends, Body
from typing import List, Optional, Dict, Any
import logging

from app.models.schemas import (
    SearchResponse, SearchResult, ErrorResponse, 
    EquityQuery, EquityScreenResponse, PredefinedScreener
)
from app.services.search_service import SearchService
from app.core.exceptions import SearchError
from app.core.dependencies import get_current_client

logger = logging.getLogger(__name__)

router = APIRouter()

def get_search_service() -> SearchService:
    """Dependency to get search service instance"""
    return SearchService()

@router.post(
    "/screen",
    response_model=EquityScreenResponse,
    summary="Screen equities based on complex criteria",
    description="""Screen for stocks and other financial instruments based on complex filtering criteria.
    
    ## Supported Operators:
    - **eq**: equals
    - **ne**: not equals
    - **gt**: greater than
    - **lt**: less than
    - **gte**: greater than or equal to
    - **lte**: less than or equal to
    - **contains**: string contains
    - **is-in**: value is in a list
    - **starts-with**: string starts with
    - **ends-with**: string ends with
    - **and**: logical AND (combine multiple conditions)
    - **or**: logical OR (combine multiple conditions)
    
    ## Common Filter Fields:
    
    ### Region:
    ar, at, au, be, br, ca, ch, cl, cn, co, cz, de, dk, ee, eg, es, fi, fr, gb, gr, hk, hu, id, ie, il, in, is, it, jp, kr, kw, lk, lt, lv, mx, my, nl, no, nz, pe, ph, pk, pl, pt, qa, ro, ru, sa, se, sg, sr, sw, th, tr, tw, us, ve, vn, za
    
    ### Exchange (by region):
    - **US**: ASE, BTS, CXI, NCM, NGM, NMS, NYQ, OEM, OQB, OQX, PCX, PNK, YHD
    - **CA**: CNQ, NEO, TOR, VAN
    - **GB**: AQS, IOB, LSE
    - **DE**: BER, DUS, FRA, GER, HAM, MUN, STU
    - **JP**: FKA, JPX, SAP
    - **CN**: SHH, SHZ
    - **HK**: HKG
    - **AU**: ASX
    - **IN**: BSE, NSI
    - **KR**: KOE, KSC
    - **TW**: TAI, TWO
    - And many more...
    
    ### Sector:
    - Basic Materials
    - Communication Services
    - Consumer Cyclical
    - Consumer Defensive
    - Energy
    - Financial Services
    - Healthcare
    - Industrials
    - Real Estate
    - Technology
    - Utilities
    
    ### Industry (examples by sector):
    - **Basic Materials**: Agricultural Inputs, Aluminum, Chemicals, Copper, Gold, Steel
    - **Technology**: Software Application, Semiconductors, Computer Hardware, Consumer Electronics
    - **Healthcare**: Biotechnology, Drug Manufacturers, Medical Devices, Pharmaceutical Retailers
    - **Financial Services**: Banks Regional, Asset Management, Insurance, Capital Markets
    - **Energy**: Oil Gas E P, Oil Gas Refining Marketing, Solar
    - And many more...
    
    ### Financial Metrics:
    - **epsgrowth.lasttwelvemonths**: EPS growth (trailing 12 months)
    - **intradaymarketcap**: Market capitalization
    - **peratio.lasttwelvemonths**: P/E ratio (TTM)
    - **pricebookratio.quarterly**: Price-to-book ratio
    - **returnonequity.lasttwelvemonths**: ROE (TTM)
    - **totalrevenues.lasttwelvemonths**: Total revenues (TTM)
    - **avgdailyvol3m**: Average daily volume (3 months)
    - **beta**: Stock beta
    
    ## Example Query:
    ```json
    {
      "operator": "and",
      "conditions": [
        {"operator": "is-in", "field": "exchange", "value": ["NMS", "NYQ"]},
        {"operator": "eq", "field": "sector", "value": "Technology"},
        {"operator": "lt", "field": "epsgrowth.lasttwelvemonths", "value": 15},
        {"operator": "gt", "field": "intradaymarketcap", "value": 1000000000}
      ]
    }
    ```
    """,
    responses={
        200: {"description": "Screening results"},
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {"model": ErrorResponse, "description": "Screening service error"}
    }
)
async def screen_equities(
    query: Dict[str, Any] = Body(..., example={
        "operator": "and",
        "conditions": [
            {"operator": "is-in", "field": "exchange", "value": ["NMS", "NYQ"]},
            {"operator": "lt", "field": "epsgrowth.lasttwelvemonths", "value": 15}
        ]
    }),
    page: int = Query(1, description="Page number (1-indexed)", ge=1),
    page_size: int = Query(20, description="Number of results per page", ge=1, le=100),
    search_service: SearchService = Depends(get_search_service),
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> EquityScreenResponse:
    """
    Screen for stocks and other financial instruments based on complex filtering criteria.
    
    This endpoint allows you to find instruments that match specific financial metrics,
    fundamental data, and other criteria using a flexible query language.
    
    **Pagination:**
    - Use `page` parameter to navigate through results (starts at 1)
    - Use `page_size` to control how many results per page (max 100)
    - Response includes `total`, `total_pages`, and current `page` information
    """
    try:
        # Convert the query dict to an EquityQuery object for validation
        equity_query = EquityQuery(**query)
        
        # Perform the screening with pagination
        result = search_service.screen_equities(equity_query, page, page_size)
        
        return EquityScreenResponse(
            total=result['total'],
            count=result['count'],
            page=result['page'],
            page_size=result['page_size'],
            total_pages=result['total_pages'],
            results=result['results'],
            query=result['query'],
            screener=result.get('screener')
        )
        
    except Exception as e:
        logger.error(f"Error in screen_equities: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to screen equities", "detail": str(e)}
        )

@router.get(
    "/screen/predefined/{screener_name}",
    response_model=EquityScreenResponse,
    summary="Use predefined equity screeners",
    description="""Use Yahoo Finance's predefined screeners to find stocks.
    
    Available screeners:
    - **aggressive_small_caps**: Small cap stocks with high growth potential
    - **day_gainers**: Stocks with the highest percentage gains today
    - **day_losers**: Stocks with the highest percentage losses today
    - **growth_technology_stocks**: Technology stocks with strong growth metrics
    - **most_actives**: Most actively traded stocks by volume
    - **most_shorted_stocks**: Stocks with the highest short interest
    - **small_cap_gainers**: Small cap stocks with recent gains
    - **undervalued_growth_stocks**: Growth stocks trading below their intrinsic value
    - **undervalued_large_caps**: Large cap stocks trading below their intrinsic value
    - **conservative_foreign_funds**: Conservative international mutual funds
    - **high_yield_bond**: High yield bond funds
    - **portfolio_anchors**: Stable, dividend-paying stocks
    - **solid_large_growth_funds**: Large cap growth mutual funds
    - **solid_midcap_growth_funds**: Mid cap growth mutual funds
    - **top_mutual_funds**: Top performing mutual funds
    """,
    responses={
        200: {"description": "Screening results"},
        400: {"model": ErrorResponse, "description": "Invalid screener name"},
        500: {"model": ErrorResponse, "description": "Screening service error"}
    }
)
async def screen_predefined(
    screener_name: PredefinedScreener,
    page: int = Query(1, description="Page number (1-indexed)", ge=1),
    page_size: int = Query(20, description="Number of results per page", ge=1, le=100),
    search_service: SearchService = Depends(get_search_service),
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> EquityScreenResponse:
    """
    Use predefined screeners to find stocks based on common criteria.
    
    **Pagination:**
    - Use `page` parameter to navigate through results (starts at 1)
    - Use `page_size` to control how many results per page (max 100)
    - Response includes `total`, `total_pages`, and current `page` information
    """
    try:
        # Perform the screening with predefined screener
        result = search_service.screen_equities(
            query=None, 
            page=page, 
            page_size=page_size,
            predefined_screener=screener_name.value
        )
        
        return EquityScreenResponse(
            total=result['total'],
            count=result['count'],
            page=result['page'],
            page_size=result['page_size'],
            total_pages=result['total_pages'],
            results=result['results'],
            query=result.get('query'),
            screener=result.get('screener')
        )
        
    except Exception as e:
        logger.error(f"Error in screen_predefined: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to execute predefined screener", "detail": str(e)}
        )

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
    current_client: Dict[str, Any] = Depends(get_current_client)
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
    current_client: Dict[str, Any] = Depends(get_current_client)
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
    current_client: Dict[str, Any] = Depends(get_current_client)
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

 