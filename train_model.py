#!/usr/bin/env python3
"""
Training script for stock price prediction models
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

# Add app directory to path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.prediction.training import ModelTrainer
from app.services.yfinance_service import YFinanceService
from app.core.exceptions import YFinanceError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('training.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def prepare_training_data(symbols: list, period: str = "5y") -> pd.DataFrame:
    """
    Prepare training data from multiple stocks
    """
    yfinance_service = YFinanceService()
    all_data = []
    
    for symbol in symbols:
        try:
            logger.info(f"Fetching data for {symbol}")
            df = yfinance_service.get_historical_data(symbol, period)
            
            if not df.empty:
                # Add symbol column for identification
                df = df.copy()
                df['Symbol'] = symbol
                all_data.append(df)
                logger.info(f"Successfully fetched {len(df)} rows for {symbol}")
            else:
                logger.warning(f"No data found for {symbol}")
                
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {str(e)}")
            continue
    
    if not all_data:
        raise ValueError("No valid data found for any symbols")
    
    # Combine all data
    combined_data = pd.concat(all_data, ignore_index=True)
    logger.info(f"Combined dataset: {len(combined_data)} rows from {len(all_data)} symbols")
    
    return combined_data


def train_single_model(
    symbols: list,
    model_name: str,
    period: str = "5y",
    sequence_length: int = 60,
    test_size: float = 0.2,
    val_size: float = 0.1
):
    """
    Train a single LSTM model
    """
    logger.info(f"Starting training for model: {model_name}")
    
    # Prepare data
    df = prepare_training_data(symbols, period)
    
    # Create trainer
    trainer = ModelTrainer(
        model_params={
            'input_size': 28,  # Number of features after preprocessing
            'hidden_size': 50,
            'num_layers': 2,
            'dropout': 0.2,
            'output_size': 1
        },
        training_params={
            'batch_size': 32,
            'learning_rate': 0.001,
            'num_epochs': 100,
            'patience': 10,
            'weight_decay': 1e-5
        }
    )
    
    # Set sequence length
    trainer.preprocessor.sequence_length = sequence_length
    
    # Prepare data
    logger.info("Preprocessing data...")
    X, y = trainer.preprocessor.fit_transform(df)
    
    # Split data
    X_train, X_val, X_test, y_train, y_val, y_test = trainer.preprocessor.split_data(
        X, y, test_size=test_size, val_size=val_size
    )
    
    logger.info(f"Data split - Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
    
    # Create data loaders
    train_loader, val_loader, test_loader = trainer.create_data_loaders(
        X_train, y_train, X_val, y_val, X_test, y_test
    )
    
    # Train model
    logger.info("Starting model training...")
    training_history = trainer.train_model(train_loader, val_loader)
    
    # Evaluate model
    logger.info("Evaluating model...")
    metrics = trainer.evaluate_model(test_loader)
    
    # Save model
    model_path = f"models/{model_name}"
    trainer.save_model(model_path, {
        'training_symbols': symbols,
        'training_period': period,
        'sequence_length': sequence_length,
        'data_size': len(df),
        'test_metrics': {
            'rmse': metrics['rmse'],
            'mae': metrics['mae'],
            'mape': metrics['mape']
        }
    })
    
    logger.info(f"Model saved to {model_path}")
    logger.info(f"Final metrics - RMSE: {metrics['rmse']:.4f}, MAE: {metrics['mae']:.4f}, MAPE: {metrics['mape']:.2f}%")
    
    return trainer, metrics


def train_ensemble_model(
    symbols: list,
    model_name: str,
    period: str = "5y",
    n_models: int = 5,
    sequence_length: int = 60
):
    """
    Train an ensemble of models
    """
    logger.info(f"Starting ensemble training for model: {model_name} with {n_models} models")
    
    # Prepare data
    df = prepare_training_data(symbols, period)
    
    # Create trainer
    trainer = ModelTrainer()
    trainer.preprocessor.sequence_length = sequence_length
    
    # Train ensemble
    ensemble_model = trainer.train_ensemble(df, n_models=n_models)
    
    # Save ensemble
    model_path = f"models/{model_name}_ensemble"
    trainer.save_model(model_path, {
        'model_type': 'ensemble',
        'n_models': n_models,
        'training_symbols': symbols,
        'training_period': period,
        'sequence_length': sequence_length,
        'data_size': len(df)
    })
    
    logger.info(f"Ensemble model saved to {model_path}")
    
    return trainer, ensemble_model


def main():
    parser = argparse.ArgumentParser(description="Train stock price prediction models")
    
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
        help="Stock symbols to train on"
    )
    
    parser.add_argument(
        "--model-name",
        type=str,
        default=f"stock_predictor_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="Name for the trained model"
    )
    
    parser.add_argument(
        "--period",
        type=str,
        default="5y",
        help="Historical data period (1y, 2y, 5y, 10y, max)"
    )
    
    parser.add_argument(
        "--sequence-length",
        type=int,
        default=60,
        help="Sequence length for LSTM (default: 60)"
    )
    
    parser.add_argument(
        "--ensemble",
        action="store_true",
        help="Train ensemble of models"
    )
    
    parser.add_argument(
        "--n-models",
        type=int,
        default=5,
        help="Number of models in ensemble (default: 5)"
    )
    
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Test set proportion (default: 0.2)"
    )
    
    parser.add_argument(
        "--val-size",
        type=float,
        default=0.1,
        help="Validation set proportion (default: 0.1)"
    )
    
    args = parser.parse_args()
    
    # Create models directory
    Path("models").mkdir(exist_ok=True)
    
    try:
        if args.ensemble:
            trainer, model = train_ensemble_model(
                symbols=args.symbols,
                model_name=args.model_name,
                period=args.period,
                n_models=args.n_models,
                sequence_length=args.sequence_length
            )
        else:
            trainer, metrics = train_single_model(
                symbols=args.symbols,
                model_name=args.model_name,
                period=args.period,
                sequence_length=args.sequence_length,
                test_size=args.test_size,
                val_size=args.val_size
            )
        
        logger.info("Training completed successfully!")
        
    except Exception as e:
        logger.error(f"Training failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
