from datetime import timedelta
from django.utils import timezone
from operations.models import Gate, GateCompatibility, GateStatus, FlightStatus

def evaluate_gate_for_flight(gate, flight):
    """
    Evaluates suitability of a Gate for a Flight.
    Returns:
    {
        'gate_id': gate.id,
        'gate_number': gate.gate_number,
        'terminal': gate.terminal,
        'gate_type': gate.get_gate_type_display(),
        'score': float (0-100),
        'is_compatible': bool,
        'has_conflict': bool,
        'reasons': list of str,
        'warnings': list of str
    }
    """
    score = 100.0
    reasons = []
    warnings = []
    has_conflict = False
    is_compatible = True
    
    # 1. Physical Aircraft Compatibility Check
    ac = flight.aircraft
    ac_type = ac.aircraft_type if ac else 'NARROW_BODY'
    
    if ac_type == 'WIDE_BODY':
        if gate.compatibility != GateCompatibility.WIDE_BODY_COMPATIBLE and gate.compatibility != GateCompatibility.ALL:
            score -= 60.0
            is_compatible = False
            warnings.append("Gate cannot accommodate Wide-Body aircraft dimensions")
        else:
            reasons.append("Wide-Body aircraft compatible")
    elif ac_type == 'NARROW_BODY':
        reasons.append("Aircraft dimensions fully compatible")
    else:
        reasons.append("Regional jet compatible")
        
    # 2. Terminal & Flight Type (Domestic vs International)
    if flight.flight_type == 'INTERNATIONAL':
        if gate.gate_type == 'DOMESTIC':
            score -= 40.0
            is_compatible = False
            warnings.append("Domestic gate lacks international customs/immigration corridor")
        elif gate.gate_type == 'INTERNATIONAL':
            score += 5.0
            reasons.append("Dedicated International Terminal facility")
        elif gate.gate_type == 'FLEXIBLE':
            reasons.append("Flexible swing gate with customs isolation")
    else: # Domestic flight
        if gate.gate_type == 'INTERNATIONAL':
            score -= 20.0
            warnings.append("International gate requires extra transfer clearance for domestic passengers")
        else:
            reasons.append("Direct domestic boarding area")

    # 3. Schedule Conflict & Buffer Analysis
    flight_start = flight.scheduled_departure - timedelta(minutes=60)
    flight_end = flight.scheduled_departure + timedelta(minutes=30)
    
    # Check overlapping flights assigned to this gate
    overlapping_flights = gate.flights.exclude(id=flight.id).filter(
        status__in=[FlightStatus.SCHEDULED, FlightStatus.CONFIRMED, FlightStatus.ARRIVED, FlightStatus.BOARDING, FlightStatus.DELAYED],
        scheduled_departure__gte=flight_start - timedelta(minutes=45),
        scheduled_departure__lte=flight_end + timedelta(minutes=45)
    )
    
    if overlapping_flights.exists():
        has_conflict = True
        conflicting_flight = overlapping_flights.first()
        score -= 50.0
        warnings.append(f"Schedule conflict with flight {conflicting_flight.flight_number} (dep: {conflicting_flight.scheduled_departure.strftime('%H:%M')})")
    else:
        reasons.append("No schedule conflict (Clear 90-minute operational window)")
        
    # 4. Gate Physical Status
    if gate.status == GateStatus.MAINTENANCE:
        score = 0.0
        is_compatible = False
        warnings.append("Gate currently under maintenance")
    elif gate.status == GateStatus.OCCUPIED and not has_conflict:
        score -= 15.0
        warnings.append("Gate currently occupied by another turnaround")
    elif gate.status == GateStatus.AVAILABLE:
        score += 5.0
        reasons.append("Gate is currently vacant and ready")

    # 5. Passenger Volume & Turnaround Suitability
    pax_count = flight.booked_seats_count
    if pax_count > 200:
        if 'Terminal 1' in gate.terminal or 'Terminal 3' in gate.terminal:
            score += 5.0
            reasons.append("High-throughput jetbridge suitable for high passenger volume")
    else:
        reasons.append("Low congestion terminal area")

    # Bound score between 5 and 99 (or 0 if totally incompatible)
    if not is_compatible and score > 30:
        score = 25.0
    if has_conflict and score > 40:
        score = 35.0
        
    final_score = max(0.0, min(99.0, score))
    
    return {
        'gate_id': gate.id,
        'gate_number': gate.gate_number,
        'terminal': gate.terminal,
        'gate_type': gate.get_gate_type_display(),
        'compatibility': gate.get_compatibility_display(),
        'status': gate.get_status_display(),
        'score': round(final_score, 1),
        'is_compatible': is_compatible,
        'has_conflict': has_conflict,
        'reasons': reasons[:4],
        'warnings': warnings
    }

def recommend_gates_for_flight(flight, limit=5):
    """
    Ranks all airport gates for a given flight.
    """
    gates = Gate.objects.all()
    evaluations = []
    
    for gate in gates:
        eval_result = evaluate_gate_for_flight(gate, flight)
        evaluations.append(eval_result)
        
    evaluations.sort(key=lambda x: x['score'], reverse=True)
    return evaluations[:limit]
