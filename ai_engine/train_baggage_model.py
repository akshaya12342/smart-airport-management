import os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

def generate_baggage_risk_dataset(n_samples=2500, random_state=42):
    np.random.seed(random_state)
    
    # Features:
    # 0: weight_kg (5.0 - 45.0)
    # 1: special_handling (0/1)
    # 2: flight_delay (0-120 min)
    # 3: terminal_load (1-10)
    # 4: staff_ratio (0.3 - 2.0)
    # 5: is_international (0/1)
    
    weight = np.random.uniform(8.0, 38.0, n_samples)
    special = np.random.choice([0, 1], p=[0.85, 0.15], size=n_samples)
    flight_delay = np.random.exponential(scale=12, size=n_samples)
    terminal_load = np.random.randint(1, 11, n_samples)
    staff_ratio = np.random.uniform(0.4, 1.8, n_samples)
    is_intl = np.random.choice([0, 1], p=[0.75, 0.25], size=n_samples)
    
    # Mishandling/delay risk formula
    risk_score_raw = (
        (np.maximum(0, weight - 25.0) * 1.5) +
        (special * 8.0) +
        (flight_delay * 0.45) +
        (terminal_load * 4.0) +
        ((1.5 - staff_ratio) * 20.0) +
        (is_intl * 10.0) +
        np.random.normal(0, 6, n_samples)
    )
    
    risk_score = np.clip(risk_score_raw, 0.0, 100.0)
    
    # Classification: 0=LOW (<30), 1=MEDIUM (30-65), 2=HIGH (>65)
    risk_class = np.where(risk_score < 30, 0, np.where(risk_score < 65, 1, 2))
    
    X = np.column_stack([
        weight, special, flight_delay, terminal_load, staff_ratio, is_intl
    ])
    
    return X, risk_score, risk_class

def train_and_save_baggage_model(save_dir=None):
    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saved_models')
    os.makedirs(save_dir, exist_ok=True)
    
    X, y_score, y_class = generate_baggage_risk_dataset(2500)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_class, test_size=0.2, random_state=42
    )
    
    clf = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42)
    clf.fit(X_train, y_train)
    
    acc = accuracy_score(y_test, clf.predict(X_test))
    print(f"Baggage Risk Classifier Accuracy: {acc * 100:.2f}%")
    
    bundle = {
        'classifier': clf,
        'class_labels': ['LOW', 'MEDIUM', 'HIGH'],
        'feature_names': [
            'weight_kg', 'special_handling', 'flight_delay',
            'terminal_load', 'staff_ratio', 'is_international'
        ]
    }
    
    save_path = os.path.join(save_dir, 'baggage_risk_model.joblib')
    joblib.dump(bundle, save_path)
    print(f"Saved baggage risk model bundle to {save_path}")
    return save_path

if __name__ == '__main__':
    train_and_save_baggage_model()
