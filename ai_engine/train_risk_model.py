import os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

def generate_ground_risk_dataset(n_samples=2500, random_state=42):
    np.random.seed(random_state)
    
    # Features:
    # 0: ac_type (0=Narrow, 1=Wide, 2=Regional)
    # 1: passengers (50-350)
    # 2: load_factor (0.5-1.0)
    # 3: staff_count (1-8)
    # 4: baggage_count (40-300)
    # 5: weather_severity (0-3)
    # 6: flight_delay_minutes (0-120)
    # 7: is_international (0/1)
    
    ac_type = np.random.choice([0, 1, 2], p=[0.65, 0.25, 0.10], size=n_samples)
    capacity = np.where(ac_type == 1, 300, np.where(ac_type == 0, 180, 80))
    load_factor = np.random.uniform(0.65, 0.98, n_samples)
    passengers = (capacity * load_factor).astype(int)
    
    staff_count = np.random.choice([1, 2, 3, 4, 5, 6, 7, 8], p=[0.05, 0.10, 0.25, 0.35, 0.15, 0.05, 0.03, 0.02], size=n_samples)
    baggage_count = (passengers * np.random.uniform(0.7, 1.2, n_samples)).astype(int)
    weather_severity = np.random.choice([0, 1, 2, 3], p=[0.65, 0.20, 0.10, 0.05], size=n_samples)
    flight_delay = np.random.exponential(scale=15, size=n_samples).astype(int)
    is_intl = np.random.choice([0, 1], p=[0.75, 0.25], size=n_samples)
    
    # Calculate ground risk index (0 to 100)
    # Risk factors: staff shortage vs passenger volume, weather, existing delay, wide-body turnaround complexity
    workload_per_staff = (baggage_count + passengers) / (staff_count + 0.1)
    
    raw_risk = (
        (workload_per_staff / 60.0) * 35.0 +
        weather_severity * 18.0 +
        np.clip(flight_delay * 0.35, 0, 30) +
        (ac_type * 10.0) +
        (is_intl * 8.0) +
        np.random.normal(0, 5, n_samples)
    )
    
    risk_score = np.clip(raw_risk, 0.0, 100.0)
    
    # Classes: 0=LOW (<30), 1=MEDIUM (30-60), 2=HIGH (60-80), 3=CRITICAL (>80)
    risk_class = np.where(risk_score < 30, 0,
                 np.where(risk_score < 60, 1,
                 np.where(risk_score < 80, 2, 3)))
    
    X = np.column_stack([
        ac_type, passengers, load_factor, staff_count,
        baggage_count, weather_severity, flight_delay, is_intl
    ])
    
    return X, risk_score, risk_class

def train_and_save_ground_risk_model(save_dir=None):
    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saved_models')
    os.makedirs(save_dir, exist_ok=True)
    
    X, y_score, y_class = generate_ground_risk_dataset(2500)
    
    X_train, X_test, y_score_train, y_score_test, y_class_train, y_class_test = train_test_split(
        X, y_score, y_class, test_size=0.2, random_state=42
    )
    
    reg = GradientBoostingRegressor(n_estimators=100, max_depth=5, random_state=42)
    reg.fit(X_train, y_score_train)
    
    clf = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42)
    clf.fit(X_train, y_class_train)
    
    acc = accuracy_score(y_class_test, clf.predict(X_test))
    print(f"Ground Risk Model Accuracy: {acc * 100:.2f}%")
    
    bundle = {
        'score_regressor': reg,
        'class_classifier': clf,
        'class_labels': ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
        'feature_names': [
            'aircraft_type', 'passengers', 'load_factor', 'staff_count',
            'baggage_count', 'weather_severity', 'flight_delay', 'is_international'
        ]
    }
    
    save_path = os.path.join(save_dir, 'ground_risk_model.joblib')
    joblib.dump(bundle, save_path)
    print(f"Saved ground risk model bundle to {save_path}")
    return save_path

if __name__ == '__main__':
    train_and_save_ground_risk_model()
