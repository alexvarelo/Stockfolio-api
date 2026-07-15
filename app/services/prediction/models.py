"""
LSTM model definitions for stock price prediction
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Tuple, Optional


class LSTMModel(nn.Module):
    """
    LSTM neural network for stock price prediction
    """
    
    def __init__(
        self,
        input_size: int = 10,  # Number of features (OHLCV + technical indicators)
        hidden_size: int = 50,
        num_layers: int = 2,
        dropout: float = 0.2,
        output_size: int = 1  # Predict next day's closing price
    ):
        super(LSTMModel, self).__init__()
        
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            batch_first=True
        )
        
        # Dropout layer
        self.dropout = nn.Dropout(dropout)
        
        # Fully connected layers
        self.fc1 = nn.Linear(hidden_size, hidden_size // 2)
        self.fc2 = nn.Linear(hidden_size // 2, output_size)
        
        # Activation functions
        self.relu = nn.ReLU()
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network
        
        Args:
            x: Input tensor of shape (batch_size, sequence_length, input_size)
            
        Returns:
            Output tensor of shape (batch_size, output_size)
        """
        # Initialize hidden state
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        
        # LSTM forward pass
        out, _ = self.lstm(x, (h0, c0))
        
        # Take the last output
        out = out[:, -1, :]
        
        # Apply dropout
        out = self.dropout(out)
        
        # Fully connected layers
        out = self.fc1(out)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        
        return out
    
    def predict_with_uncertainty(
        self, 
        x: torch.Tensor, 
        n_samples: int = 100
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Make predictions with uncertainty estimation using Monte Carlo dropout
        
        Args:
            x: Input tensor
            n_samples: Number of samples for uncertainty estimation
            
        Returns:
            Tuple of (mean_prediction, std_prediction)
        """
        self.train()  # Enable dropout for uncertainty estimation
        
        predictions = []
        with torch.no_grad():
            for _ in range(n_samples):
                pred = self.forward(x)
                predictions.append(pred)
        
        predictions = torch.stack(predictions)
        mean_pred = predictions.mean(dim=0)
        std_pred = predictions.std(dim=0)
        
        self.eval()  # Return to evaluation mode
        
        return mean_pred, std_pred


class EnsembleModel:
    """
    Ensemble of LSTM models for better prediction accuracy
    """
    
    def __init__(self, models: list):
        self.models = models
        
    def predict(self, x: torch.Tensor) -> torch.Tensor:
        """
        Make ensemble prediction
        """
        predictions = []
        for model in self.models:
            model.eval()
            with torch.no_grad():
                pred = model(x)
                predictions.append(pred)
        
        # Average predictions
        return torch.stack(predictions).mean(dim=0)
    
    def predict_with_uncertainty(
        self, 
        x: torch.Tensor, 
        n_samples: int = 50
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Make ensemble prediction with uncertainty estimation
        """
        all_predictions = []
        
        for model in self.models:
            mean_pred, std_pred = model.predict_with_uncertainty(x, n_samples)
            all_predictions.append(mean_pred)
        
        predictions = torch.stack(all_predictions)
        mean_pred = predictions.mean(dim=0)
        std_pred = predictions.std(dim=0)
        
        return mean_pred, std_pred
