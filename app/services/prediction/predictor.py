"""
Stock price prediction service
"""

import torch
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

from .models import LSTMModel, EnsembleModel
from .preprocessing import DataPreprocessor
from .training import ModelTrainer
from app.services.yfinance_service import YFinanceService
from app.core.exceptions import PredictionError

logger = logging.getLogger(__name__)


class StockPredictor:
    """
    Main service for stock price prediction
    """
    
    def __init__(self, model_path: Optional[str] = None):
        self.yfinance_service = YFinanceService()
        self.model_path = model_path
        self.model = None
        self.preprocessor = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        if model_path:
            self.load_model(model_path)
    
    def load_model(self, model_path: str):
        """
        Load a pre-trained model
        """
        try:
            trainer, model = ModelTrainer.load_model(model_path)
            self.model = model
            self.preprocessor = trainer.preprocessor
            logger.info(f"Model loaded from {model_path}")
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            raise PredictionError("load_model", str(e))
    
    def prepare_data(self, symbol: str, period: str = "2y") -> pd.DataFrame:
        """
        Prepare historical data for prediction
        """
        try:
            # Get historical data
            df = self.yfinance_service.get_historical_data(symbol, period)
            
            if df.empty:
                raise PredictionError("prepare_data", f"No historical data found for {symbol}")
            
            # Ensure we have enough data
            min_required_days = 200  # Need at least 200 days for technical indicators
            if len(df) < min_required_days:
                raise PredictionError(
                    "prepare_data", 
                    f"Insufficient data: need at least {min_required_days} days, got {len(df)}"
                )
            
            return df
            
        except Exception as e:
            logger.error(f"Error preparing data for {symbol}: {str(e)}")
            raise PredictionError("prepare_data", str(e))
    
    def predict_single_day(
        self, 
        symbol: str, 
        days_ahead: int = 1,
        include_uncertainty: bool = True
    ) -> Dict:
        """
        Predict stock price for a specific number of days ahead
        
        Args:
            symbol: Stock ticker symbol
            days_ahead: Number of days to predict ahead
            include_uncertainty: Whether to include uncertainty estimates
            
        Returns:
            Dictionary with prediction results
        """
        if self.model is None:
            raise PredictionError("predict_single_day", "No model loaded")
        
        try:
            # Prepare data
            df = self.prepare_data(symbol)
            
            # Transform data for prediction
            X = self.preprocessor.transform_for_prediction(df)
            
            if len(X) == 0:
                raise PredictionError("predict_single_day", "No valid sequences for prediction")
            
            # Get the last sequence for prediction
            last_sequence = torch.FloatTensor(X[-1:]).to(self.model.device)
            
            # Make prediction
            self.model.eval()
            with torch.no_grad():
                if include_uncertainty:
                    mean_pred, std_pred = self.model.predict_with_uncertainty(
                        last_sequence, n_samples=100
                    )
                    mean_pred = mean_pred.cpu().numpy()
                    std_pred = std_pred.cpu().numpy()
                else:
                    mean_pred = self.model(last_sequence).cpu().numpy()
                    std_pred = None
            
            # Inverse transform to get actual price
            predicted_price = self.preprocessor.inverse_transform_predictions(mean_pred.flatten())[0]
            
            # Calculate confidence intervals
            confidence_interval = None
            if include_uncertainty and std_pred is not None:
                std_price = std_pred.flatten()[0]
                confidence_interval = {
                    'lower_95': predicted_price - 1.96 * std_price,
                    'upper_95': predicted_price + 1.96 * std_price,
                    'lower_68': predicted_price - std_price,
                    'upper_68': predicted_price + std_price
                }
            
            # Get current price for reference
            current_price = df['Close'].iloc[-1]
            
            # Calculate expected return
            expected_return = ((predicted_price - current_price) / current_price) * 100
            
            result = {
                'symbol': symbol.upper(),
                'current_price': float(current_price),
                'predicted_price': float(predicted_price),
                'days_ahead': days_ahead,
                'expected_return_pct': float(expected_return),
                'prediction_date': (datetime.now() + timedelta(days=days_ahead)).isoformat(),
                'confidence_interval': confidence_interval,
                'model_info': {
                    'model_type': 'LSTM',
                    'features_used': len(self.preprocessor.create_features(df).columns),
                    'sequence_length': self.preprocessor.sequence_length
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error predicting {symbol}: {str(e)}")
            raise PredictionError("predict_single_day", str(e))
    
    def predict_multi_day(
        self, 
        symbol: str, 
        days_ahead: int = 5,
        include_uncertainty: bool = True
    ) -> Dict:
        """
        Predict stock prices for multiple days ahead using recursive prediction
        
        Args:
            symbol: Stock ticker symbol
            days_ahead: Number of days to predict ahead
            include_uncertainty: Whether to include uncertainty estimates
            
        Returns:
            Dictionary with multi-day prediction results
        """
        if self.model is None:
            raise PredictionError("predict_multi_day", "No model loaded")
        
        try:
            # Prepare data
            df = self.prepare_data(symbol)
            
            predictions = []
            uncertainties = []
            current_data = df.copy()
            
            for day in range(days_ahead):
                # Transform current data
                X = self.preprocessor.transform_for_prediction(current_data)
                
                if len(X) == 0:
                    break
                
                # Get the last sequence
                last_sequence = torch.FloatTensor(X[-1:]).to(self.model.device)
                
                # Make prediction
                self.model.eval()
                with torch.no_grad():
                    if include_uncertainty:
                        mean_pred, std_pred = self.model.predict_with_uncertainty(
                            last_sequence, n_samples=50
                        )
                        mean_pred = mean_pred.cpu().numpy()
                        std_pred = std_pred.cpu().numpy()
                    else:
                        mean_pred = self.model(last_sequence).cpu().numpy()
                        std_pred = None
                
                # Inverse transform
                predicted_price = self.preprocessor.inverse_transform_predictions(
                    mean_pred.flatten()
                )[0]
                
                predictions.append(predicted_price)
                if include_uncertainty and std_pred is not None:
                    uncertainties.append(std_pred.flatten()[0])
                else:
                    uncertainties.append(0.0)
                
                # Update data for next prediction (recursive approach)
                # Create a new row with predicted data
                last_row = current_data.iloc[-1].copy()
                last_row['Close'] = predicted_price
                # Estimate other OHLC values based on typical price movements
                price_change_pct = (predicted_price - last_row['Close']) / last_row['Close']
                last_row['High'] = last_row['High'] * (1 + price_change_pct * 0.7)
                last_row['Low'] = last_row['Low'] * (1 + price_change_pct * 0.7)
                last_row['Open'] = predicted_price  # Assume open equals predicted close
                last_row['Volume'] = last_row['Volume'] * 0.95  # Slightly decrease volume
                
                # Append to current_data
                new_row_df = pd.DataFrame([last_row])
                current_data = pd.concat([current_data, new_row_df], ignore_index=True)
            
            # Get current price
            current_price = df['Close'].iloc[-1]
            
            # Create result
            prediction_dates = [
                (datetime.now() + timedelta(days=i+1)).isoformat() 
                for i in range(len(predictions))
            ]
            
            daily_returns = [
                ((pred - current_price) / current_price) * 100 
                for pred in predictions
            ]
            
            result = {
                'symbol': symbol.upper(),
                'current_price': float(current_price),
                'predictions': [
                    {
                        'date': prediction_dates[i],
                        'predicted_price': float(predictions[i]),
                        'uncertainty': float(uncertainties[i]),
                        'expected_return_pct': float(daily_returns[i])
                    }
                    for i in range(len(predictions))
                ],
                'summary': {
                    'total_return_pct': float(daily_returns[-1]) if daily_returns else 0.0,
                    'avg_daily_return_pct': float(np.mean(daily_returns)) if daily_returns else 0.0,
                    'volatility_estimate': float(np.std(uncertainties)) if uncertainties else 0.0
                },
                'model_info': {
                    'model_type': 'LSTM',
                    'prediction_method': 'recursive',
                    'days_predicted': len(predictions)
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error in multi-day prediction for {symbol}: {str(e)}")
            raise PredictionError("predict_multi_day", str(e))
    
    def predict_batch(
        self, 
        symbols: List[str], 
        prediction_type: str = "single",
        days_ahead: int = 1
    ) -> List[Dict]:
        """
        Make predictions for multiple stocks
        
        Args:
            symbols: List of stock ticker symbols
            prediction_type: "single" or "multi" day prediction
            days_ahead: Number of days to predict ahead
            
        Returns:
            List of prediction results
        """
        predictions = []
        
        # Use ThreadPoolExecutor for parallel predictions
        futures = []
        
        for symbol in symbols:
            if prediction_type == "single":
                future = self.executor.submit(
                    self.predict_single_day, 
                    symbol, 
                    days_ahead=days_ahead
                )
            else:
                future = self.executor.submit(
                    self.predict_multi_day, 
                    symbol, 
                    days_ahead=days_ahead
                )
            futures.append((symbol, future))
        
        # Collect results
        for symbol, future in futures:
            try:
                result = future.result(timeout=30)  # 30 second timeout
                predictions.append(result)
            except Exception as e:
                logger.error(f"Error predicting {symbol}: {str(e)}")
                predictions.append({
                    'symbol': symbol.upper(),
                    'error': str(e),
                    'status': 'failed'
                })
        
        return predictions
    
    def get_model_info(self) -> Dict:
        """
        Get information about the loaded model
        """
        if self.model is None:
            return {'status': 'no_model_loaded'}
        
        return {
            'model_type': 'LSTM',
            'model_params': {
                'input_size': self.model.input_size,
                'hidden_size': self.model.hidden_size,
                'num_layers': self.model.num_layers,
                'dropout': self.model.dropout,
                'output_size': self.model.output_size
            },
            'preprocessor_info': {
                'sequence_length': self.preprocessor.sequence_length,
                'is_fitted': self.preprocessor.is_fitted
            },
            'device': str(self.model.device),
            'model_path': self.model_path
        }
    
    async def predict_async(
        self, 
        symbol: str, 
        prediction_type: str = "single",
        days_ahead: int = 1
    ) -> Dict:
        """
        Async prediction method
        """
        loop = asyncio.get_event_loop()
        
        if prediction_type == "single":
            return await loop.run_in_executor(
                self.executor, 
                self.predict_single_day, 
                symbol, 
                days_ahead
            )
        else:
            return await loop.run_in_executor(
                self.executor, 
                self.predict_multi_day, 
                symbol, 
                days_ahead
            )
