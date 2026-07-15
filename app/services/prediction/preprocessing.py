"""
Data preprocessing and feature engineering for stock price prediction
"""

import pandas as pd
import numpy as np
from typing import Tuple, List, Optional
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.model_selection import train_test_split
import logging

logger = logging.getLogger(__name__)


class DataPreprocessor:
    """
    Preprocess stock data for LSTM model training and prediction
    """
    
    def __init__(self, sequence_length: int = 60):
        self.sequence_length = sequence_length
        self.price_scaler = MinMaxScaler(feature_range=(0, 1))
        self.feature_scaler = StandardScaler()
        self.is_fitted = False
        
    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators for feature engineering
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with additional technical indicators
        """
        data = df.copy()
        
        # Simple Moving Averages
        data['SMA_5'] = data['Close'].rolling(window=5).mean()
        data['SMA_10'] = data['Close'].rolling(window=10).mean()
        data['SMA_20'] = data['Close'].rolling(window=20).mean()
        data['SMA_50'] = data['Close'].rolling(window=50).mean()
        
        # Exponential Moving Averages
        data['EMA_12'] = data['Close'].ewm(span=12).mean()
        data['EMA_26'] = data['Close'].ewm(span=26).mean()
        
        # MACD
        data['MACD'] = data['EMA_12'] - data['EMA_26']
        data['MACD_Signal'] = data['MACD'].ewm(span=9).mean()
        data['MACD_Histogram'] = data['MACD'] - data['MACD_Signal']
        
        # RSI (Relative Strength Index)
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))
        
        # Bollinger Bands
        sma_20 = data['Close'].rolling(window=20).mean()
        std_20 = data['Close'].rolling(window=20).std()
        data['BB_Upper'] = sma_20 + (std_20 * 2)
        data['BB_Lower'] = sma_20 - (std_20 * 2)
        data['BB_Width'] = data['BB_Upper'] - data['BB_Lower']
        
        # Price changes
        data['Price_Change_1d'] = data['Close'].pct_change(1)
        data['Price_Change_5d'] = data['Close'].pct_change(5)
        data['Price_Change_10d'] = data['Close'].pct_change(10)
        
        # Volume indicators
        data['Volume_SMA'] = data['Volume'].rolling(window=10).mean()
        data['Volume_Ratio'] = data['Volume'] / data['Volume_SMA']
        
        # Volatility (ATR-like)
        high_low = data['High'] - data['Low']
        high_close = np.abs(data['High'] - data['Close'].shift())
        low_close = np.abs(data['Low'] - data['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        data['ATR'] = true_range.rolling(window=14).mean()
        
        # Price position relative to moving averages
        data['Price_vs_SMA20'] = (data['Close'] - data['SMA_20']) / data['SMA_20']
        data['Price_vs_SMA50'] = (data['Close'] - data['SMA_50']) / data['SMA_50']
        
        return data
    
    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create feature matrix for LSTM model
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with engineered features
        """
        # Calculate technical indicators
        data = self.calculate_technical_indicators(df)
        
        # Select features for the model
        feature_columns = [
            'Open', 'High', 'Low', 'Close', 'Volume',
            'SMA_5', 'SMA_10', 'SMA_20', 'SMA_50',
            'EMA_12', 'EMA_26', 'MACD', 'MACD_Signal', 'MACD_Histogram',
            'RSI', 'BB_Upper', 'BB_Lower', 'BB_Width',
            'Price_Change_1d', 'Price_Change_5d', 'Price_Change_10d',
            'Volume_Ratio', 'ATR', 'Price_vs_SMA20', 'Price_vs_SMA50'
        ]
        
        # Remove rows with NaN values (due to rolling windows)
        data = data.dropna()
        
        return data[feature_columns]
    
    def prepare_sequences(
        self, 
        data: np.ndarray, 
        target_column: int = 3  # Close price index
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create sequences for LSTM training
        
        Args:
            data: Feature array
            target_column: Index of target column (Close price)
            
        Returns:
            Tuple of (X, y) where X is sequences and y is targets
        """
        X, y = [], []
        
        for i in range(self.sequence_length, len(data)):
            # Input sequence (all features)
            X.append(data[i-self.sequence_length:i, :])
            
            # Target (next day's close price)
            y.append(data[i, target_column])
        
        return np.array(X), np.array(y)
    
    def fit_transform(
        self, 
        df: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Fit scalers and transform data for training
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Tuple of (X, y) sequences
        """
        # Create features
        features_df = self.create_features(df)
        
        # Convert to numpy array
        data = features_df.values
        
        # Fit scalers
        self.price_scaler.fit(data[:, 3:4])  # Close price column
        self.feature_scaler.fit(data)
        
        # Transform data
        scaled_data = self.feature_scaler.transform(data)
        
        # Create sequences
        X, y = self.prepare_sequences(scaled_data)
        
        # Scale target variable
        y = self.price_scaler.transform(y.reshape(-1, 1)).flatten()
        
        self.is_fitted = True
        
        return X, y
    
    def transform_for_prediction(self, df: pd.DataFrame) -> np.ndarray:
        """
        Transform new data for prediction
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Scaled sequences for prediction
        """
        if not self.is_fitted:
            raise ValueError("Preprocessor must be fitted before transforming data")
        
        # Create features
        features_df = self.create_features(df)
        
        # Convert to numpy array and transform
        data = features_df.values
        scaled_data = self.feature_scaler.transform(data)
        
        # Create sequences
        X, _ = self.prepare_sequences(scaled_data)
        
        return X
    
    def inverse_transform_predictions(self, predictions: np.ndarray) -> np.ndarray:
        """
        Inverse transform predictions back to original scale
        
        Args:
            predictions: Scaled predictions
            
        Returns:
            Predictions in original price scale
        """
        return self.price_scaler.inverse_transform(predictions.reshape(-1, 1)).flatten()
    
    def split_data(
        self, 
        X: np.ndarray, 
        y: np.ndarray, 
        test_size: float = 0.2,
        val_size: float = 0.1
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Split data into train, validation, and test sets
        
        Args:
            X: Feature sequences
            y: Target values
            test_size: Proportion for test set
            val_size: Proportion for validation set (from remaining data)
            
        Returns:
            Tuple of (X_train, X_val, X_test, y_train, y_val, y_test)
        """
        # First split: separate test set
        X_temp, X_test, y_temp, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, shuffle=False
        )
        
        # Second split: separate validation set from remaining data
        val_size_adjusted = val_size / (1 - test_size)
        X_train, X_val, y_train, y_val = train_test_split(
            X_temp, y_temp, test_size=val_size_adjusted, random_state=42, shuffle=False
        )
        
        return X_train, X_val, X_test, y_train, y_val, y_test
