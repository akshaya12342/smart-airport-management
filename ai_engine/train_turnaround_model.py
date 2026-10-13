import os
import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score

def generate_turnaround_dataset(n_samples=2500, random_state=42):
    np.random.seed(random_state)
    
    # Features:
    # 0: ac_type (0=Narrow, 1=Wide, 2=Regional)
    # 1: capacity (70 - 360)
    # 2: passengers (40 - 350)
    # 3: baggage_count (30 - 350)
    # 4: staff_count (1 - 8)
    # 5: is_international (0/1)
    # 6: hour (5 - 23)
    
    ac_type = np.random.choice([0, 1, 2], p=[0.65, 0.25, 0.10], size=n_samples)
    capacity = np.where(ac_type == 1, np.random.randint(280, 360, n_samples),
               np.where(ac_type == 0, np.random.randint(160, 190, n_samples),
                                      np.random.randint(70, 90, n_samples)))
    
    load_factor = np.random.uniform(0.65, 0.98, n_samples)
    passengers = (capacity * load_factor).astype(int)
    baggage_count = (passengers * np.random.uniform(0.8, 1.2, n_samples)).astype(int)
    staff_count = np.random.choice([2, 3, 4, 5, 6, 7], p=[0.10, 0.25, 0.35, 0.18, 0.08, 0.04], size=n_samples)
    is_intl = np.random.choice([0, 1], p=[0.75, 0.25], size=n_samples)
    hour = np.random.randint(5, 24, n_samples)
    
    # Realistic turnaround physics calculation in minutes:
    # Base turnaround: Regional ~30m, Narrow-body ~45m, Wide-body ~75m
    base_min = np.where(ac_type == 1, 75.0, np.where(ac_type == 0, 45.0, 30.0))
    
    # Boarding/deplaning time: ~0.08 min per passenger, divided by staff efficiency
    pax_time = (passengers * 0.07) * (4.0 / staff_count)
    
    # Baggage loading/unloading: ~0.05 min per bag / staff
    bag_time = (baggage_count * 0.05) * (4.0 / staff_count)
    
    # International customs & security overhead
    intl_time = is_intl * 15.0
    
    # Congestion peak penalty
    peak_penalty = np.where(((hour >= 8) & (hour <= 10)) | ((hour >= 18) & (hour <= 21)), 8.0, 0.0)
    
    noise = np.random.normal(0, 3.5, n_samples)
    
    total_turnaround_minutes = np.maximum(25.0, base_min + (pax_time * 0.4) + (bag_time * 0.4) + intl_time + peak_penalty + noise)
    
    X = np.column_stack([
        ac_type, capacity, passengers, baggage_count,
        staff_count, is_intl, hour
    ])
    
    return X, total_turnaround_minutes

def train_and_save_turnaround_model(save_dir=None):
    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saved_models')
    os.makedirs(save_dir, exist_ok=True)
    
    X, y = generate_turnaround_dataset(2500)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    model = GradientBoostingRegressor(n_estimators=100, max_depth=5, random_state=42)
    model.fit(X_train, y_train)
    
    score = r2_score(y_test, model.predict(X_test))
    rmse = np.sqrt(mean_squared_error(y_test, model.predict(X_test)))
    print(f"Turnaround Regressor R2: {score:.3f}, RMSE: {rmse:.2f} mins")
    
    bundle = {
        'model': model,
        'feature_names': [
            'aircraft_type', 'capacity', 'passengers',
            'baggage_count', 'staff_count', 'is_international', 'hour'
        ]
    }
    
    save_path = os.path.join(save_dir, 'turnaround_model.joblib')
    joblib.dump(bundle, save_path)
    print(f"Saved turnaround model bundle to {save_path}")
    return save_path

if __name__ == '__main__':
    train_and_save_turnaround_model()
