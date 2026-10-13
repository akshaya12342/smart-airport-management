import os
import joblib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SAVED_MODELS_DIR = BASE_DIR / 'saved_models'

_MODELS_CACHE = {}

def get_model(model_name):
    """
    Safely retrieves a loaded ML model bundle from memory or loads from disk.
    If the model is not found on disk, automatically triggers training.
    """
    if model_name in _MODELS_CACHE:
        return _MODELS_CACHE[model_name]
    
    os.makedirs(SAVED_MODELS_DIR, exist_ok=True)
    file_path = SAVED_MODELS_DIR / f"{model_name}.joblib"
    
    if not file_path.exists():
        print(f"Model file {file_path} not found. Training model automatically...")
        train_missing_model(model_name)
    
    if file_path.exists():
        try:
            bundle = joblib.load(file_path)
            _MODELS_CACHE[model_name] = bundle
            return bundle
        except Exception as e:
            print(f"Error loading model {model_name}: {e}")
            return None
    return None

def train_missing_model(model_name):
    from .train_delay_model import train_and_save_delay_model
    from .train_risk_model import train_and_save_ground_risk_model
    from .train_baggage_model import train_and_save_baggage_model
    from .train_turnaround_model import train_and_save_turnaround_model
    
    if model_name == 'flight_delay_model':
        train_and_save_delay_model(str(SAVED_MODELS_DIR))
    elif model_name == 'ground_risk_model':
        train_and_save_ground_risk_model(str(SAVED_MODELS_DIR))
    elif model_name == 'baggage_risk_model':
        train_and_save_baggage_model(str(SAVED_MODELS_DIR))
    elif model_name == 'turnaround_model':
        train_and_save_turnaround_model(str(SAVED_MODELS_DIR))

def preload_all_models():
    """Pre-trains and caches all ML models."""
    for m in ['flight_delay_model', 'ground_risk_model', 'baggage_risk_model', 'turnaround_model']:
        get_model(m)
