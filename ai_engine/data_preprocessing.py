import numpy as np
import pandas as pd
from datetime import datetime

AIRLINE_MAP = {'AI': 0, '6E': 1, 'UK': 2, 'SG': 3, 'EK': 4, 'BA': 5, 'OTHER': 6}
AIRCRAFT_MAP = {'NARROW_BODY': 0, 'WIDE_BODY': 1, 'REGIONAL': 2}
FLIGHT_TYPE_MAP = {'DOMESTIC': 0, 'INTERNATIONAL': 1}
WEATHER_MAP = {'CLEAR': 0, 'RAIN': 1, 'FOG': 2, 'STORM': 3}

def encode_airline(iata_code):
    return AIRLINE_MAP.get(iata_code.upper() if iata_code else 'OTHER', 6)

def encode_aircraft_type(ac_type):
    return AIRCRAFT_MAP.get(ac_type, 0)

def encode_flight_type(fl_type):
    return FLIGHT_TYPE_MAP.get(fl_type, 0)

def extract_flight_features(flight, weather_severity=0, congestion_level=3, inbound_delay=0):
    """
    Extracts numerical features array for flight delay prediction:
    [airline_code, aircraft_type, flight_type, hour_of_departure, day_of_week, 
     month, booked_seats, capacity, load_factor, weather_severity, congestion_level, inbound_delay]
    """
    airline_code = encode_airline(flight.airline.iata_code if flight.airline else 'AI')
    ac_type = encode_aircraft_type(flight.aircraft.aircraft_type if flight.aircraft else 'NARROW_BODY')
    fl_type = encode_flight_type(flight.flight_type)
    
    dep_time = flight.scheduled_departure
    hour = dep_time.hour
    day_of_week = dep_time.weekday()
    month = dep_time.month
    
    capacity = flight.total_capacity
    booked = flight.booked_seats_count
    load_factor = (booked / capacity) if capacity > 0 else 0.8
    
    return np.array([[
        airline_code,
        ac_type,
        fl_type,
        hour,
        day_of_week,
        month,
        booked,
        capacity,
        load_factor,
        weather_severity,
        congestion_level,
        inbound_delay
    ]], dtype=float)

def extract_ground_risk_features(flight, staff_count=4, weather_severity=0, baggage_count=120):
    """
    Features for ground risk:
    [aircraft_type, passenger_count, load_factor, staff_count, baggage_count, 
     weather_severity, flight_delay_minutes, is_international]
    """
    ac_type = encode_aircraft_type(flight.aircraft.aircraft_type if flight.aircraft else 'NARROW_BODY')
    passengers = flight.booked_seats_count
    capacity = flight.total_capacity
    load_factor = (passengers / capacity) if capacity > 0 else 0.8
    is_intl = 1 if flight.flight_type == 'INTERNATIONAL' else 0
    delay_min = flight.delay_minutes
    
    return np.array([[
        ac_type,
        passengers,
        load_factor,
        staff_count,
        baggage_count,
        weather_severity,
        delay_min,
        is_intl
    ]], dtype=float)

def extract_baggage_features(baggage, flight_delay=0, terminal_load=4, staff_ratio=1.0):
    """
    Features for baggage delay risk:
    [weight_kg, special_handling (0/1), flight_delay_minutes, terminal_load (1-10), 
     staff_ratio, is_international]
    """
    weight = float(baggage.weight_kg)
    special = 1 if baggage.special_handling else 0
    is_intl = 1 if (baggage.flight and baggage.flight.flight_type == 'INTERNATIONAL') else 0
    
    return np.array([[
        weight,
        special,
        flight_delay,
        terminal_load,
        staff_ratio,
        is_intl
    ]], dtype=float)

def extract_turnaround_features(flight, staff_count=4, baggage_count=120):
    """
    Features for turnaround duration estimation:
    [aircraft_type, seating_capacity, passenger_count, baggage_count, 
     staff_count, is_international, hour_of_departure]
    """
    ac_type = encode_aircraft_type(flight.aircraft.aircraft_type if flight.aircraft else 'NARROW_BODY')
    capacity = flight.total_capacity
    passengers = flight.booked_seats_count
    is_intl = 1 if flight.flight_type == 'INTERNATIONAL' else 0
    hour = flight.scheduled_departure.hour if flight.scheduled_departure else 12
    
    return np.array([[
        ac_type,
        capacity,
        passengers,
        baggage_count,
        staff_count,
        is_intl,
        hour
    ]], dtype=float)
