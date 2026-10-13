import numpy as np
from datetime import datetime, timedelta
from django.utils import timezone
from .model_loader import get_model
from .data_preprocessing import (
    extract_flight_features,
    extract_ground_risk_features,
    extract_baggage_features,
    extract_turnaround_features
)
from .gate_recommender import recommend_gates_for_flight

def predict_flight_delay(flight, weather_severity=0, congestion_level=3, inbound_delay=0):
    """
    Predicts delay duration (minutes), probability (0.0-1.0), and key risk factors for a flight.
    """
    bundle = get_model('flight_delay_model')
    features = extract_flight_features(flight, weather_severity, congestion_level, inbound_delay)
    
    if bundle:
        reg_model = bundle['regressor']
        clf_model = bundle['classifier']
        
        predicted_delay = float(reg_model.predict(features)[0])
        # Probability of delay > 15m
        prob_delay = float(clf_model.predict_proba(features)[0][1])
    else:
        # Heuristic fallback
        predicted_delay = max(0.0, float(flight.delay_minutes))
        prob_delay = 0.2 if predicted_delay < 15 else 0.8
        
    predicted_delay = max(0.0, round(predicted_delay, 1))
    prob_delay = max(0.0, min(1.0, round(prob_delay, 2)))
    
    # Generate explainable AI factor breakdown
    factors = []
    if flight.delay_minutes > 0:
        factors.append(f"Recorded departure delay (+{flight.delay_minutes} min)")
    if flight.flight_type == 'INTERNATIONAL':
        factors.append("International customs and passport control buffer required")
    if flight.booked_seats_count > 150:
        factors.append("High passenger volume extending boarding cycle")
    if flight.aircraft and flight.aircraft.aircraft_type == 'WIDE_BODY':
        factors.append("Wide-body aircraft turnaround complexity")
    if flight.scheduled_departure.hour in [8, 9, 18, 19, 20]:
        factors.append("Peak departure window airport air traffic congestion")
    if len(factors) == 0:
        factors.append("Optimal atmospheric and operational turnaround conditions")
        
    # Risk categorization
    if predicted_delay >= 45 or prob_delay >= 0.75:
        risk_level = 'CRITICAL'
    elif predicted_delay >= 25 or prob_delay >= 0.50:
        risk_level = 'HIGH'
    elif predicted_delay >= 10 or prob_delay >= 0.25:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'LOW'
        
    return {
        'delay_minutes': predicted_delay,
        'probability': prob_delay,
        'risk_level': risk_level,
        'factors': factors
    }

def predict_ground_risk(flight, staff_count=4, weather_severity=0):
    """
    Predicts ground turnaround operational risk score (0-100) and actionable mitigation recommendations.
    """
    bundle = get_model('ground_risk_model')
    baggage_count = flight.baggage_items.count() if hasattr(flight, 'baggage_items') else int(flight.booked_seats_count * 0.9)
    features = extract_ground_risk_features(flight, staff_count, weather_severity, baggage_count)
    
    if bundle:
        reg_model = bundle['score_regressor']
        clf_model = bundle['class_classifier']
        
        risk_score = float(reg_model.predict(features)[0])
        risk_class_idx = int(clf_model.predict(features)[0])
        risk_level = bundle['class_labels'][risk_class_idx]
    else:
        risk_score = 15.0
        risk_level = 'LOW'
        
    risk_score = max(0.0, min(100.0, round(risk_score, 1)))
    
    recommendations = []
    if risk_score > 60:
        recommendations.append("Deploy 2 additional ramp staff for baggage handling")
        recommendations.append("Pre-position fuel bowser and pushback tug at gate")
    if flight.booked_seats_count > 160:
        recommendations.append("Initiate zone-based boarding 35 minutes prior to departure")
    if flight.delay_minutes > 15:
        recommendations.append("Notify inbound connecting flights and update transit baggage priority")
    if len(recommendations) == 0:
        recommendations.append("Standard turnaround protocol recommended")
        
    return {
        'risk_score': risk_score,
        'risk_level': risk_level,
        'recommendations': recommendations
    }

def predict_baggage_risk(baggage, flight_delay=0, terminal_load=4, staff_ratio=1.0):
    """
    Predicts risk score and level for a baggage item.
    """
    bundle = get_model('baggage_risk_model')
    features = extract_baggage_features(baggage, flight_delay, terminal_load, staff_ratio)
    
    if bundle:
        clf_model = bundle['classifier']
        probs = clf_model.predict_proba(features)[0] # [P(Low), P(Med), P(High)]
        risk_score = round(float(probs[1] * 50.0 + probs[2] * 100.0), 1)
        pred_idx = int(np.argmax(probs))
        risk_level = bundle['class_labels'][pred_idx]
    else:
        risk_score = 10.0
        risk_level = 'LOW'
        
    reasons = []
    if float(baggage.weight_kg) > 23.0:
        reasons.append("Heavy bag (>23kg) requires dual handling")
    if baggage.special_handling:
        reasons.append("Special handling / Fragile item requires priority belt")
    if flight_delay > 20:
        reasons.append(f"Flight delay (+{flight_delay}m) compresses ramp loading window")
    if not reasons:
        reasons.append("Normal processing flow")
        
    reason_str = "; ".join(reasons)
    
    return {
        'risk_score': risk_score,
        'risk_level': risk_level,
        'reason': reason_str
    }

def predict_turnaround_time(flight, staff_count=4):
    """
    Predicts total turnaround duration in minutes.
    """
    bundle = get_model('turnaround_model')
    baggage_count = flight.baggage_items.count() if hasattr(flight, 'baggage_items') else int(flight.booked_seats_count * 0.9)
    features = extract_turnaround_features(flight, staff_count, baggage_count)
    
    if bundle:
        model = bundle['model']
        pred_minutes = float(model.predict(features)[0])
    else:
        pred_minutes = 45.0
        
    pred_minutes = max(25.0, round(pred_minutes, 1))
    target_minutes = 45.0 if (not flight.aircraft or flight.aircraft.aircraft_type == 'NARROW_BODY') else 75.0
    
    return {
        'predicted_minutes': pred_minutes,
        'target_minutes': target_minutes,
        'is_at_risk': pred_minutes > target_minutes + 10
    }

def recommend_gates(flight, limit=5):
    """
    Wrapper for AI gate recommendation.
    """
    return recommend_gates_for_flight(flight, limit=limit)

def update_flight_ai_prediction(flight):
    """
    Computes all AI predictions and updates or creates the AIFlightPrediction database record.
    """
    from operations.models import AIFlightPrediction
    
    staff_count = flight.staff_assignments.filter(status='ACTIVE').count() or 4
    delay_info = predict_flight_delay(flight)
    ground_info = predict_ground_risk(flight, staff_count=staff_count)
    turnaround_info = predict_turnaround_time(flight, staff_count=staff_count)
    
    obj, created = AIFlightPrediction.objects.update_or_create(
        flight=flight,
        defaults={
            'predicted_delay_minutes': delay_info['delay_minutes'],
            'delay_probability': delay_info['probability'],
            'risk_level': ground_info['risk_level'],
            'predicted_turnaround_minutes': turnaround_info['predicted_minutes'],
            'ground_risk_score': ground_info['risk_score'],
            'key_factors': delay_info['factors'],
            'recommendations': ground_info['recommendations'],
        }
    )
    return obj

def update_all_flight_predictions():
    """
    Refreshes AI predictions for all active/upcoming flights.
    """
    from operations.models import Flight, FlightStatus
    active_flights = Flight.objects.exclude(status__in=[FlightStatus.DEPARTED, FlightStatus.CANCELLED])
    for f in active_flights:
        try:
            update_flight_ai_prediction(f)
        except Exception as e:
            print(f"Error updating AI prediction for flight {f.flight_number}: {e}")
