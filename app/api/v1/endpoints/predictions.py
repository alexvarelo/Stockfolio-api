"""
Prediction API endpoints for stock price forecasting
"""

from fastapi import APIRouter, HTTPException, Depends, Path, Query, BackgroundTasks
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import logging
from datetime import datetime

from app.services.prediction.predictor import StockPredictor
from app.core.dependencies import get_current_client
from app.core.exceptions import PredictionError

logger = logging.getLogger(__name__)

router = APIRouter()

# Pydantic models for request/response
class PredictionRequest(BaseModel):
    symbol: str = Field(..., description="Stock ticker symbol")
    days_ahead: int = Field(default=1, ge=1, le=30, description="Number of days to predict ahead")
    include_uncertainty: bool = Field(default=True, description="Include uncertainty estimates")

class MultiDayPredictionRequest(BaseModel):
    symbol: str = Field(..., description="Stock ticker symbol")
    days_ahead: int = Field(default=5, ge=1, le=30, description="Number of days to predict ahead")
    include_uncertainty: bool = Field(default=True, description="Include uncertainty estimates")

class BatchPredictionRequest(BaseModel):
    symbols: List[str] = Field(..., description="List of stock ticker symbols")
    prediction_type: str = Field(default="single", regex="^(single|multi)$", description="Type of prediction")
    days_ahead: int = Field(default=1, ge=1, le=30, description="Number of days to predict ahead")

class PredictionResponse(BaseModel):
    symbol: str
    current_price: float
    predicted_price: float
    days_ahead: int
    expected_return_pct: float
    prediction_date: str
    confidence_interval: Optional[Dict[str, float]] = None
    model_info: Dict[str, Any]
    timestamp: str

class MultiDayPredictionResponse(BaseModel):
    symbol: str
    current_price: float
    predictions: List[Dict[str, Any]]
    summary: Dict[str, float]
    model_info: Dict[str, Any]
    timestamp: str

class ModelInfoResponse(BaseModel):
    model_type: str
    model_params: Dict[str, Any]
    preprocessor_info: Dict[str, Any]
    device: str
    model_path: Optional[str] = None

# Global predictor instance
predictor = StockPredictor()

@router.post(
    "/predict/single",
    response_model=PredictionResponse,
    summary="Predict stock price for single day",
    description="Predict stock price for a specific number of days ahead with uncertainty estimates",
    responses={
        200: {"model": PredictionResponse, "description": "Prediction successful"},
        400: {"model": Dict, "description": "Invalid request"},
        404: {"model": Dict, "description": "Model not loaded"},
        500: {"model": Dict, "description": "Prediction error"}
    }
)
async def predict_single_day(
    request: PredictionRequest,
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> PredictionResponse:
    """
    Predict stock price for a single day ahead.
    
    - **symbol**: Stock ticker symbol (e.g., AAPL, GOOGL)
    - **days_ahead**: Number of days to predict ahead (1-30)
    - **include_uncertainty**: Whether to include confidence intervals
    
    Returns predicted price with uncertainty estimates and expected return.
    """
    try:
        logger.info(f"Single day prediction request for {request.symbol} by client {current_client.get('client_id')}")
        
        if predictor.model is None:
            raise HTTPException(
                status_code=404, 
                detail="No prediction model loaded. Please train or load a model first."
            )
        
        result = predictor.predict_single_day(
            symbol=request.symbol,
            days_ahead=request.days_ahead,
            include_uncertainty=request.include_uncertainty
        )
        
        # Add timestamp
        result['timestamp'] = datetime.now().isoformat()
        
        return PredictionResponse(**result)
        
    except PredictionError as e:
        logger.error(f"Prediction error for {request.symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in single day prediction: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post(
    "/predict/multi-day",
    response_model=MultiDayPredictionResponse,
    summary="Predict stock prices for multiple days",
    description="Predict stock prices for multiple days ahead using recursive prediction",
    responses={
        200: {"model": MultiDayPredictionResponse, "description": "Multi-day prediction successful"},
        400: {"model": Dict, "description": "Invalid request"},
        404: {"model": Dict, "description": "Model not loaded"},
        500: {"model": Dict, "description": "Prediction error"}
    }
)
async def predict_multi_day(
    request: MultiDayPredictionRequest,
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> MultiDayPredictionResponse:
    """
    Predict stock prices for multiple days ahead.
    
    - **symbol**: Stock ticker symbol (e.g., AAPL, GOOGL)
    - **days_ahead**: Number of days to predict ahead (1-30)
    - **include_uncertainty**: Whether to include uncertainty estimates
    
    Returns daily predictions with summary statistics.
    """
    try:
        logger.info(f"Multi-day prediction request for {request.symbol} by client {current_client.get('client_id')}")
        
        if predictor.model is None:
            raise HTTPException(
                status_code=404, 
                detail="No prediction model loaded. Please train or load a model first."
            )
        
        result = predictor.predict_multi_day(
            symbol=request.symbol,
            days_ahead=request.days_ahead,
            include_uncertainty=request.include_uncertainty
        )
        
        # Add timestamp
        result['timestamp'] = datetime.now().isoformat()
        
        return MultiDayPredictionResponse(**result)
        
    except PredictionError as e:
        logger.error(f"Multi-day prediction error for {request.symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in multi-day prediction: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post(
    "/predict/batch",
    summary="Predict prices for multiple stocks",
    description="Make predictions for multiple stocks in parallel",
    responses={
        200: {"description": "Batch prediction successful"},
        400: {"model": Dict, "description": "Invalid request"},
        404: {"model": Dict, "description": "Model not loaded"},
        500: {"model": Dict, "description": "Prediction error"}
    }
)
async def predict_batch(
    request: BatchPredictionRequest,
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> List[Dict[str, Any]]:
    """
    Make predictions for multiple stocks.
    
    - **symbols**: List of stock ticker symbols
    - **prediction_type**: "single" for single day, "multi" for multi-day
    - **days_ahead**: Number of days to predict ahead
    
    Returns list of prediction results for each symbol.
    """
    try:
        logger.info(f"Batch prediction request for {len(request.symbols)} symbols by client {current_client.get('client_id')}")
        
        if predictor.model is None:
            raise HTTPException(
                status_code=404, 
                detail="No prediction model loaded. Please train or load a model first."
            )
        
        if len(request.symbols) > 50:
            raise HTTPException(
                status_code=400,
                detail="Too many symbols. Maximum allowed is 50 per batch request."
            )
        
        results = predictor.predict_batch(
            symbols=request.symbols,
            prediction_type=request.prediction_type,
            days_ahead=request.days_ahead
        )
        
        # Add timestamp to each result
        for result in results:
            if 'error' not in result:
                result['timestamp'] = datetime.now().isoformat()
        
        return results
        
    except PredictionError as e:
        logger.error(f"Batch prediction error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Batch prediction failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in batch prediction: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/model/info",
    response_model=ModelInfoResponse,
    summary="Get model information",
    description="Get information about the loaded prediction model",
    responses={
        200: {"model": ModelInfoResponse, "description": "Model information"},
        404: {"model": Dict, "description": "No model loaded"}
    }
)
async def get_model_info(
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> ModelInfoResponse:
    """
    Get information about the currently loaded prediction model.
    
    Returns model architecture, parameters, and configuration details.
    """
    try:
        logger.info(f"Model info request by client {current_client.get('client_id')}")
        
        info = predictor.get_model_info()
        
        if info.get('status') == 'no_model_loaded':
            raise HTTPException(
                status_code=404,
                detail="No prediction model is currently loaded"
            )
        
        return ModelInfoResponse(**info)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model info: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post(
    "/model/load",
    summary="Load a trained model",
    description="Load a pre-trained prediction model from storage",
    responses={
        200: {"description": "Model loaded successfully"},
        400: {"model": Dict, "description": "Invalid model path"},
        500: {"model": Dict, "description": "Error loading model"}
    }
)
async def load_model(
    model_path: str = Query(..., description="Path to the trained model directory"),
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> Dict[str, str]:
    """
    Load a pre-trained prediction model.
    
    - **model_path**: Path to the directory containing the trained model files
    
    Returns confirmation of successful model loading.
    """
    try:
        logger.info(f"Model load request from {model_path} by client {current_client.get('client_id')}")
        
        predictor.load_model(model_path)
        
        return {
            "status": "success",
            "message": f"Model loaded successfully from {model_path}",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error loading model from {model_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")

@router.get(
    "/predict/{symbol}",
    response_model=PredictionResponse,
    summary="Quick prediction for a stock",
    description="Quick single-day prediction for a stock using path parameter",
    responses={
        200: {"model": PredictionResponse, "description": "Prediction successful"},
        404: {"model": Dict, "description": "Model not loaded or symbol not found"},
        500: {"model": Dict, "description": "Prediction error"}
    }
)
async def quick_predict(
    symbol: str = Path(..., description="Stock ticker symbol"),
    days_ahead: int = Query(default=1, ge=1, le=30, description="Number of days to predict ahead"),
    include_uncertainty: bool = Query(default=True, description="Include uncertainty estimates"),
    current_client: Dict[str, Any] = Depends(get_current_client)
) -> PredictionResponse:
    """
    Quick prediction endpoint using path parameter for symbol.
    
    - **symbol**: Stock ticker symbol in the URL path
    - **days_ahead**: Number of days to predict ahead (query parameter)
    - **include_uncertainty**: Include confidence intervals (query parameter)
    
    Returns prediction for the specified stock.
    """
    request = PredictionRequest(
        symbol=symbol,
        days_ahead=days_ahead,
        include_uncertainty=include_uncertainty
    )
    
    return await predict_single_day(request, current_client)
