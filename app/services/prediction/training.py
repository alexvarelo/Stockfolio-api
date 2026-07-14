"""
Model training pipeline for stock price prediction
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
import pandas as pd
from typing import Tuple, List, Dict, Optional
import logging
from pathlib import Path
import json
from datetime import datetime

from .models import LSTMModel, EnsembleModel
from .preprocessing import DataPreprocessor

logger = logging.getLogger(__name__)


class ModelTrainer:
    """
    Training pipeline for LSTM stock prediction models
    """
    
    def __init__(
        self,
        model_params: Optional[Dict] = None,
        training_params: Optional[Dict] = None,
        device: Optional[str] = None
    ):
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Using device: {self.device}")
        
        # Default model parameters
        self.model_params = model_params or {
            'input_size': 28,  # Number of features
            'hidden_size': 50,
            'num_layers': 2,
            'dropout': 0.2,
            'output_size': 1
        }
        
        # Default training parameters
        self.training_params = training_params or {
            'batch_size': 32,
            'learning_rate': 0.001,
            'num_epochs': 100,
            'patience': 10,  # Early stopping patience
            'weight_decay': 1e-5
        }
        
        self.model = None
        self.preprocessor = DataPreprocessor()
        self.training_history = []
        
    def create_data_loaders(
        self, 
        X_train: np.ndarray, 
        y_train: np.ndarray,
        X_val: np.ndarray, 
        y_val: np.ndarray,
        X_test: np.ndarray, 
        y_test: np.ndarray
    ) -> Tuple[DataLoader, DataLoader, DataLoader]:
        """
        Create PyTorch DataLoaders for training, validation, and test sets
        """
        # Convert to PyTorch tensors
        X_train_tensor = torch.FloatTensor(X_train).to(self.device)
        y_train_tensor = torch.FloatTensor(y_train).to(self.device)
        X_val_tensor = torch.FloatTensor(X_val).to(self.device)
        y_val_tensor = torch.FloatTensor(y_val).to(self.device)
        X_test_tensor = torch.FloatTensor(X_test).to(self.device)
        y_test_tensor = torch.FloatTensor(y_test).to(self.device)
        
        # Create datasets
        train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
        val_dataset = TensorDataset(X_val_tensor, y_val_tensor)
        test_dataset = TensorDataset(X_test_tensor, y_test_tensor)
        
        # Create data loaders
        train_loader = DataLoader(
            train_dataset, 
            batch_size=self.training_params['batch_size'],
            shuffle=True
        )
        val_loader = DataLoader(
            val_dataset, 
            batch_size=self.training_params['batch_size'],
            shuffle=False
        )
        test_loader = DataLoader(
            test_dataset, 
            batch_size=self.training_params['batch_size'],
            shuffle=False
        )
        
        return train_loader, val_loader, test_loader
    
    def train_model(
        self, 
        train_loader: DataLoader, 
        val_loader: DataLoader
    ) -> Dict:
        """
        Train the LSTM model
        """
        # Initialize model
        self.model = LSTMModel(**self.model_params).to(self.device)
        
        # Loss function and optimizer
        criterion = nn.MSELoss()
        optimizer = optim.Adam(
            self.model.parameters(),
            lr=self.training_params['learning_rate'],
            weight_decay=self.training_params['weight_decay']
        )
        
        # Learning rate scheduler
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=5, verbose=True
        )
        
        # Training variables
        best_val_loss = float('inf')
        patience_counter = 0
        training_history = {
            'train_loss': [],
            'val_loss': [],
            'epochs': []
        }
        
        logger.info("Starting model training...")
        
        for epoch in range(self.training_params['num_epochs']):
            # Training phase
            self.model.train()
            train_loss = 0.0
            
            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()
                
                # Forward pass
                outputs = self.model(batch_X)
                loss = criterion(outputs.squeeze(), batch_y)
                
                # Backward pass
                loss.backward()
                
                # Gradient clipping to prevent exploding gradients
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                
                optimizer.step()
                train_loss += loss.item()
            
            # Validation phase
            self.model.eval()
            val_loss = 0.0
            
            with torch.no_grad():
                for batch_X, batch_y in val_loader:
                    outputs = self.model(batch_X)
                    loss = criterion(outputs.squeeze(), batch_y)
                    val_loss += loss.item()
            
            # Calculate average losses
            avg_train_loss = train_loss / len(train_loader)
            avg_val_loss = val_loss / len(val_loader)
            
            # Update learning rate
            scheduler.step(avg_val_loss)
            
            # Record history
            training_history['train_loss'].append(avg_train_loss)
            training_history['val_loss'].append(avg_val_loss)
            training_history['epochs'].append(epoch + 1)
            
            # Early stopping
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                patience_counter = 0
                # Save best model
                torch.save(self.model.state_dict(), 'best_model.pth')
            else:
                patience_counter += 1
            
            # Logging
            if (epoch + 1) % 10 == 0:
                logger.info(
                    f"Epoch [{epoch+1}/{self.training_params['num_epochs']}], "
                    f"Train Loss: {avg_train_loss:.6f}, Val Loss: {avg_val_loss:.6f}"
                )
            
            # Early stopping
            if patience_counter >= self.training_params['patience']:
                logger.info(f"Early stopping at epoch {epoch+1}")
                break
        
        # Load best model
        self.model.load_state_dict(torch.load('best_model.pth'))
        
        self.training_history = training_history
        return training_history
    
    def evaluate_model(self, test_loader: DataLoader) -> Dict:
        """
        Evaluate the trained model on test data
        """
        if self.model is None:
            raise ValueError("Model must be trained before evaluation")
        
        self.model.eval()
        test_loss = 0.0
        predictions = []
        actuals = []
        
        criterion = nn.MSELoss()
        
        with torch.no_grad():
            for batch_X, batch_y in test_loader:
                outputs = self.model(batch_X)
                loss = criterion(outputs.squeeze(), batch_y)
                test_loss += loss.item()
                
                predictions.extend(outputs.cpu().numpy())
                actuals.extend(batch_y.cpu().numpy())
        
        avg_test_loss = test_loss / len(test_loader)
        
        # Calculate additional metrics
        predictions = np.array(predictions).flatten()
        actuals = np.array(actuals).flatten()
        
        # Convert back to original scale for interpretable metrics
        predictions_orig = self.preprocessor.inverse_transform_predictions(predictions)
        actuals_orig = self.preprocessor.inverse_transform_predictions(actuals)
        
        # Calculate metrics in original scale
        mae = np.mean(np.abs(predictions_orig - actuals_orig))
        mse = np.mean((predictions_orig - actuals_orig) ** 2)
        rmse = np.sqrt(mse)
        
        # Mean Absolute Percentage Error
        mape = np.mean(np.abs((actuals_orig - predictions_orig) / actuals_orig)) * 100
        
        metrics = {
            'test_loss': avg_test_loss,
            'mae': mae,
            'mse': mse,
            'rmse': rmse,
            'mape': mape,
            'predictions': predictions_orig,
            'actuals': actuals_orig
        }
        
        logger.info(f"Test Results - RMSE: {rmse:.4f}, MAE: {mae:.4f}, MAPE: {mape:.2f}%")
        
        return metrics
    
    def train_ensemble(
        self, 
        df: pd.DataFrame, 
        n_models: int = 5
    ) -> EnsembleModel:
        """
        Train an ensemble of models for better predictions
        """
        models = []
        
        for i in range(n_models):
            logger.info(f"Training model {i+1}/{n_models}")
            
            # Create new trainer for each model
            trainer = ModelTrainer(
                model_params=self.model_params,
                training_params=self.training_params,
                device=self.device
            )
            
            # Prepare data (with different random seed for diversity)
            X, y = self.preprocessor.fit_transform(df)
            X_train, X_val, X_test, y_train, y_val, y_test = self.preprocessor.split_data(X, y)
            
            # Create data loaders
            train_loader, val_loader, test_loader = trainer.create_data_loaders(
                X_train, y_train, X_val, y_val, X_test, y_test
            )
            
            # Train model
            trainer.train_model(train_loader, val_loader)
            models.append(trainer.model)
        
        return EnsembleModel(models)
    
    def save_model(self, path: str, metadata: Optional[Dict] = None):
        """
        Save the trained model and preprocessing pipeline
        """
        if self.model is None:
            raise ValueError("No model to save")
        
        save_path = Path(path)
        save_path.mkdir(exist_ok=True)
        
        # Save model
        torch.save(self.model.state_dict(), save_path / 'model.pth')
        
        # Save preprocessor
        import pickle
        with open(save_path / 'preprocessor.pkl', 'wb') as f:
            pickle.dump(self.preprocessor, f)
        
        # Save metadata
        metadata = metadata or {}
        metadata.update({
            'model_params': self.model_params,
            'training_params': self.training_params,
            'training_history': self.training_history,
            'timestamp': datetime.now().isoformat(),
            'device': self.device
        })
        
        with open(save_path / 'metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Model saved to {save_path}")
    
    @classmethod
    def load_model(cls, path: str) -> Tuple['ModelTrainer', LSTMModel]:
        """
        Load a trained model and preprocessing pipeline
        """
        load_path = Path(path)
        
        # Load metadata
        with open(load_path / 'metadata.json', 'r') as f:
            metadata = json.load(f)
        
        # Create trainer with saved parameters
        trainer = cls(
            model_params=metadata['model_params'],
            training_params=metadata['training_params'],
            device=metadata['device']
        )
        
        # Load preprocessor
        import pickle
        with open(load_path / 'preprocessor.pkl', 'rb') as f:
            trainer.preprocessor = pickle.load(f)
        
        # Load model
        model = LSTMModel(**metadata['model_params'])
        model.load_state_dict(torch.load(load_path / 'model.pth', map_location=trainer.device))
        model.to(trainer.device)
        trainer.model = model
        trainer.training_history = metadata['training_history']
        
        logger.info(f"Model loaded from {load_path}")
        
        return trainer, model
