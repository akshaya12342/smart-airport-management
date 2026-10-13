import os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, accuracy_score

def generate_flight_delay_dataset(n_samples=2500, random_state=42):
    np.random.seed(random_state)
    
    # Features:
    # 0: airline_code (0-5)
    # 1: ac_type (0=Narrow, 1=Wide, 2=Regional)
    # 2: fl_type (0=Domestic, 1=International)
    # 3: hour (0-23)
    # 4: day_of_week (0-6)
    # 5: month (1-12)
    # 6: booked_seats (50-350)
    # 7: capacity (70-350)
    # 8: load_factor (0.5-1.0)
    # 9: weather_severity (0=Clear, 1=Rain, 2=Fog, 3=Storm)
    # 10: congestion_level (1-10)
    # 11: inbound_delay (0-120)
    
    airline = np.random.randint(0, 6, n_samples)
    ac_type = np.random.choice([0, 1, 2], p=[0.65, 0.25, 0.10], size=n_samples)
    fl_type = np.random.choice([0, 1], p=[0.75, 0.25], size=n_samples)
    hour = np.random.randint(5, 24, n_samples)
    day_of_week = np.random.randint(0, 7, n_samples)
    month = np.random.randint(1, 13, n_samples)
    
    capacity = np.where(ac_type == 1, np.random.randint(280, 360, n_samples),
               np.where(ac_type == 0, np.random.randint(160, 190, n_samples),
                                      np.random.randint(70, 90, n_samples)))
    
    load_factor = np.random.uniform(0.60, 0.98, n_samples)
    booked_seats = (capacity * load_factor).astype(int)
    
    weather_severity = np.random.choice([0, 1, 2, 3], p=[0.65, 0.20, 0.10, 0.05], size=n_samples)
    
    # Peak hours: 8-10 AM, 17-21 PM
    peak_factor = np.where(((hour >= 8) & (hour <= 10)) | ((hour >= 17) & (hour <= 21)), 1.5, 0.8)
    congestion_level = np.clip(np.random.normal(4 * peak_factor, 1.5), 1, 10).astype(int)
    
    inbound_delay = np.random.exponential(scale=10, size=n_samples).astype(int)
    inbound_delay = np.clip(inbound_delay, 0, 120)
    
    # True delay calculation with realistic noise
    base_delay = (
        weather_severity * 22.0 +
        congestion_level * 3.5 +
        (inbound_delay * 0.45) +
        (ac_type * 6.0) +
        (load_factor * 12.0) +
        np.where((hour >= 18) & (hour <= 22), 10.0, 0.0) +
        np.random.normal(0, 8, n_samples)
    )
    
    # Clean zero delays for on-time operations
    delay_minutes = np.where(base_delay < 5, 0.0, np.maximum(0.0, base_delay))
    is_delayed = (delay_minutes >= 15).astype(int)
    
    X = np.column_stack([
        airline, ac_type, fl_type, hour, day_of_week, month,
        booked_seats, capacity, load_factor, weather_severity,
        congestion_level, inbound_delay
    ])
    
    return X, delay_minutes, is_delayed

def train_and_save_delay_model(save_dir=None):
    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saved_models')
    os.makedirs(save_dir, exist_ok=True)
    
    X, y_reg, y_clf = generate_flight_delay_dataset(3000)
    
    X_train, X_test, y_reg_train, y_reg_test, y_clf_train, y_clf_test = train_test_split(
        X, y_reg, y_clf, test_size=0.2, random_state=42
    )
    
    reg_model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42)
    reg_model.fit(X_train, y_reg_train)
    
    clf_model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
    clf_model.fit(X_train, y_clf_train)
    
    reg_score = reg_model.score(X_test, y_reg_test)
    clf_score = accuracy_score(y_clf_test, clf_model.predict(X_test))
    
    print(f"Delay Regressor R2: {reg_score:.3f}")
    print(f"Delay Classifier Accuracy: {clf_score * 100:.2f}%")
    
    bundle = {
        'regressor': reg_model,
        'classifier': clf_model,
        'feature_names': [
            'airline', 'aircraft_type', 'flight_type', 'hour', 'day_of_week', 'month',
            'booked_seats', 'capacity', 'load_factor', 'weather_severity',
            'congestion_level', 'inbound_delay'
        ]
    }
    
    save_path = os.path.join(save_dir, 'flight_delay_model.joblib')
    joblib.dump(bundle, save_path)
    print(f"Saved flight delay model bundle to {save_path}")
    return save_path

if __name__ == '__main__':
    train_and_save_delay_model()
