#!/usr/bin/env python3
"""
Example script demonstrating stock price prediction usage
"""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.prediction.predictor import StockPredictor
from app.services.prediction.training import ModelTrainer
from app.services.yfinance_service import YFinanceService


async def example_predictions():
    """
    Example of how to use the prediction service
    """
    print("Stock Price Prediction Example")
    print("=" * 40)
    
    # Initialize predictor
    predictor = StockPredictor()
    
    # Check if model is loaded
    model_info = predictor.get_model_info()
    print(f"Model status: {model_info}")
    
    if model_info.get('status') == 'no_model_loaded':
        print("\nNo model loaded. You need to train a model first.")
        print("Run: python train_model.py --symbols AAPL GOOGL MSFT")
        return
    
    # Example 1: Single day prediction
    print("\n1. Single Day Prediction for AAPL:")
    try:
        result = predictor.predict_single_day("AAPL", days_ahead=1, include_uncertainty=True)
        print(f"   Current Price: ${result['current_price']:.2f}")
        print(f"   Predicted Price: ${result['predicted_price']:.2f}")
        print(f"   Expected Return: {result['expected_return_pct']:.2f}%")
        if result['confidence_interval']:
            ci = result['confidence_interval']
            print(f"   95% Confidence Interval: ${ci['lower_95']:.2f} - ${ci['upper_95']:.2f}")
    except Exception as e:
        print(f"   Error: {str(e)}")
    
    # Example 2: Multi-day prediction
    print("\n2. Multi-Day Prediction for GOOGL (5 days):")
    try:
        result = predictor.predict_multi_day("GOOGL", days_ahead=5, include_uncertainty=True)
        print(f"   Current Price: ${result['current_price']:.2f}")
        print(f"   Predictions:")
        for pred in result['predictions']:
            print(f"     Day {pred['date'][:10]}: ${pred['predicted_price']:.2f} "
                  f"({pred['expected_return_pct']:+.2f}%)")
        print(f"   Summary:")
        summary = result['summary']
        print(f"     Total Return: {summary['total_return_pct']:+.2f}%")
        print(f"     Avg Daily Return: {summary['avg_daily_return_pct']:+.2f}%")
    except Exception as e:
        print(f"   Error: {str(e)}")
    
    # Example 3: Batch prediction
    print("\n3. Batch Prediction for Multiple Stocks:")
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN"]
    try:
        results = predictor.predict_batch(symbols, prediction_type="single", days_ahead=1)
        for result in results:
            if 'error' not in result:
                print(f"   {result['symbol']}: ${result['predicted_price']:.2f} "
                      f"({result['expected_return_pct']:+.2f}%)")
            else:
                print(f"   {result['symbol']}: Error - {result['error']}")
    except Exception as e:
        print(f"   Error: {str(e)}")


def example_training():
    """
    Example of how to train a model
    """
    print("\nModel Training Example")
    print("=" * 40)
    
    # Note: This is just for demonstration. In practice, you'd use the train_model.py script
    print("To train a model, run:")
    print("python train_model.py --symbols AAPL GOOGL MSFT --model-name my_model")
    print("\nThis will:")
    print("1. Fetch historical data for the specified symbols")
    print("2. Preprocess the data with technical indicators")
    print("3. Train an LSTM model")
    print("4. Evaluate and save the model")


async def main():
    """
    Main example function
    """
    print("Stockfolio Prediction API Examples")
    print("=" * 50)
    
    # Show prediction examples
    await example_predictions()
    
    # Show training information
    example_training()
    
    print("\nAPI Usage Examples:")
    print("=" * 30)
    print("Once you have a trained model, you can use these API endpoints:")
    print()
    print("1. Single day prediction:")
    print("   POST /api/v1/predictions/predict/single")
    print("   Body: {\"symbol\": \"AAPL\", \"days_ahead\": 1}")
    print()
    print("2. Multi-day prediction:")
    print("   POST /api/v1/predictions/predict/multi-day")
    print("   Body: {\"symbol\": \"AAPL\", \"days_ahead\": 5}")
    print()
    print("3. Quick prediction (GET):")
    print("   GET /api/v1/predictions/predict/AAPL?days_ahead=1")
    print()
    print("4. Batch prediction:")
    print("   POST /api/v1/predictions/predict/batch")
    print("   Body: {\"symbols\": [\"AAPL\", \"GOOGL\"], \"prediction_type\": \"single\"}")
    print()
    print("5. Load model:")
    print("   POST /api/v1/predictions/model/load?model_path=models/your_model_name")
    print()
    print("6. Model info:")
    print("   GET /api/v1/predictions/model/info")


if __name__ == "__main__":
    asyncio.run(main())
