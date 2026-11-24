from fastapi import APIRouter

from app.api.v1.endpoints import search, stock, auth, stream, portfolio, analysis, technicals

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, tags=["authentication"])
api_router.include_router(search.router, tags=["search"])
api_router.include_router(stock.router, tags=["stock"])
api_router.include_router(stream.router, tags=["stream"])
api_router.include_router(portfolio.router, tags=["risk"])
api_router.include_router(analysis.router, tags=["analysis"])
api_router.include_router(technicals.router, tags=["technicals"])
