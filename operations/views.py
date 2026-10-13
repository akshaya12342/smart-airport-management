import json
import random
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Count, Q, Avg, Sum
from core.models import (
    User, UserRole, Notification, NotificationCategory, GroundStaffProfile,
    PassengerProfile, OperationsManagerProfile, GroundStaffDepartment,
    StaffShift, StaffAvailability
)
from core.decorators import passenger_required, ground_staff_required, operations_manager_required, staff_or_manager_required
from .models import (
    Airport, Airline, Aircraft, Gate, Flight, Seat, Booking, BoardingRecord, 
    Baggage, BaggageScan, StaffAssignment, GroundOperation, OperationalIssue,
    DelayRecord, GateAllocation, AIFlightPrediction,
    FlightStatus, BookingStatus, BoardingStatus, BaggageStatus,
    GateStatus, IssueStatus, TurnaroundOverallStatus, SeatClass, BookingChannel,
    DelayReason, OperationalIssueType, IssuePriority, AircraftType, AircraftStatus,
    GateType, GateCompatibility, FlightType, BaggageRiskLevel, AIRiskLevel
)
from .forms import (
    FlightSearchForm, PassengerBookingForm, FlightForm, FlightStatusUpdateForm,
    AircraftForm, GateForm, StaffAssignmentForm, OperationalIssueForm,
    BaggageScanForm, DelayRecordForm
)
from ai_engine.prediction_service import (
    predict_flight_delay, predict_ground_risk, predict_baggage_risk,
    predict_turnaround_time, recommend_gates, update_flight_ai_prediction,
    update_all_flight_predictions
)
from .status_updater import auto_update_all_flight_statuses

# ==========================================
# 0. PUBLIC HOMEPAGE & DISCOVERY (No Login Required)
# ==========================================

def home_view(request):
    """
    Public Home Page with enhanced UI in pastel color aesthetic:
    - Displays live flight schedules (Departures & Arrivals) viewable WITHOUT login
    - Search & filter flights by Route, Airline, Flight Number, Status
    - Shows on-time rate, weather telemetry, gate status, airline partners
    - Direct CTAs to Login / Register / Persona switcher
    """
    auto_update_all_flight_statuses()
    q = request.GET.get('q', '').strip()
    tab = request.GET.get('tab', 'all')
    status_filter = request.GET.get('status', '').strip()
    
    def _clean_airport_query(val):
        if not val:
            return []
        val = val.strip()
        if '(' in val and ')' in val:
            iata = val[val.find('(')+1 : val.find(')')].strip()
            city = val[:val.find('(')].strip()
            return [t for t in [iata, city] if t]
        return [val]

    flights_qs = Flight.objects.select_related(
        'airline', 'source_airport', 'destination_airport', 'aircraft', 'gate'
    ).order_by('scheduled_departure')
    
    if q:
        tokens = _clean_airport_query(q)
        q_filter = Q(flight_number__icontains=q) | Q(airline__name__icontains=q)
        for tok in tokens:
            q_filter |= (
                Q(source_airport__city__icontains=tok) |
                Q(source_airport__iata_code__icontains=tok) |
                Q(source_airport__name__icontains=tok) |
                Q(destination_airport__city__icontains=tok) |
                Q(destination_airport__iata_code__icontains=tok) |
                Q(destination_airport__name__icontains=tok)
            )
        flights_qs = flights_qs.filter(q_filter)
        
    if status_filter:
        flights_qs = flights_qs.filter(status=status_filter)
        
    departures = flights_qs.filter(source_airport__iata_code='COK')
    if not departures.exists():
        departures = flights_qs
        
    arrivals = flights_qs.filter(destination_airport__iata_code='COK')
    if not arrivals.exists():
        arrivals = flights_qs
        
    all_flights = flights_qs
    
    total_flights_count = Flight.objects.count()
    active_count = Flight.objects.exclude(status__in=[FlightStatus.DEPARTED, FlightStatus.CANCELLED]).count()
    delayed_count = Flight.objects.filter(Q(status=FlightStatus.DELAYED) | Q(delay_minutes__gt=0)).count()
    on_time_pct = round(((total_flights_count - delayed_count) / total_flights_count * 100), 1) if total_flights_count > 0 else 92.5
    
    context = {
        'departures': departures,
        'arrivals': arrivals,
        'all_flights': all_flights,
        'active_tab': tab,
        'search_query': q,
        'status_filter': status_filter,
        'status_choices': FlightStatus.choices,
        'total_flights_count': total_flights_count,
        'active_count': active_count,
        'delayed_count': delayed_count,
        'on_time_pct': on_time_pct,
        'airlines': Airline.objects.filter(active=True),
        'airports': Airport.objects.all(),
        'gates': Gate.objects.all(),
        'now': timezone.now()
    }
    return render(request, 'home.html', context)

def public_flight_details(request, flight_id):
    """
    When unauthenticated user clicks 'View Details' or 'Book Flight':
    Requires login, redirecting with a helpful notification.
    """
    flight = get_object_or_404(Flight, pk=flight_id)
    flight.auto_sync_status()
    
    if flight.status == FlightStatus.CANCELLED:
        messages.error(request, f"❌ Flight {flight.flight_number} is cancelled. Bookings are unavailable.")
        return redirect('flight_search')
        
    if flight.is_departed or flight.status == FlightStatus.DEPARTED:
        messages.warning(request, f"ℹ️ Flight {flight.flight_number} has already departed. Bookings are closed.")
        if request.user.is_authenticated and request.user.is_passenger:
            return redirect('flight_search')
        return redirect('home')
        
    if not request.user.is_authenticated:
        messages.info(request, f"Please sign in to view detailed operational telemetry, seat layout, and book tickets for Flight {flight.flight_number}.")
        return redirect(f"/login/?next=/passenger/book/{flight.id}/")
    
    if request.user.is_passenger:
        return redirect('flight_book', flight_id=flight.id)
    elif request.user.is_ground_staff:
        if StaffAssignment.objects.filter(staff=request.user, flight=flight, status='ACTIVE').exists():
            return redirect('assigned_flight_detail', flight_id=flight.id)
        else:
            return redirect('ground_staff_dashboard')
    elif request.user.is_operations_manager:
        return redirect('manager_update_flight_status', pk=flight.id)
    
    return redirect('dashboard_redirect')

# ==========================================
# 1. PASSENGER VIEWS & WORKFLOWS
# ==========================================

@login_required
@passenger_required
def passenger_dashboard(request):
    """
    Passenger Dashboard:
    - Separates My Booked Flights (Upcoming vs Completed)
    - Verifies existing bookings against live Flight records in the database
    - Shows empty state if user has no bookings
    - Provides Book a New Flight option
    """
    all_bookings = Booking.objects.filter(passenger=request.user).select_related(
        'flight', 'flight__airline', 'flight__source_airport', 'flight__destination_airport', 'flight__gate', 'seat'
    ).order_by('-flight__scheduled_departure')
    
    # Process bookings and verify flight data integrity
    upcoming_bookings = []
    completed_bookings = []
    
    for booking in all_bookings:
        # Check if flight still exists and is valid
        flight_valid = False
        flight_status = 'UNAVAILABLE'
        is_cancelled = False
        cancellation_reason = ''
        delay_info = None
        
        if booking.flight is not None:
            flight_valid = True
            flight = booking.flight
            flight_status = flight.status
            is_cancelled = (flight.status == FlightStatus.CANCELLED)
            cancellation_reason = flight.cancellation_reason
            
            if flight.delay_minutes > 0:
                delay_info = {
                    'delay_minutes': flight.delay_minutes,
                    'reason': flight.get_delay_reason_display() if flight.delay_reason else 'Operational adjustment',
                    'original_departure': flight.scheduled_departure,
                    'expected_departure': flight.effective_departure
                }
                
            # Get latest boarding and baggage status for this booking
            boarding_rec = getattr(booking, 'boarding_record', None)
            baggage_item = booking.baggage_items.first()
            
            booking_card_data = {
                'booking': booking,
                'flight': flight,
                'flight_valid': flight_valid,
                'flight_status': flight_status,
                'is_cancelled': is_cancelled,
                'cancellation_reason': cancellation_reason,
                'delay_info': delay_info,
                'boarding_status': boarding_rec.get_boarding_status_display() if boarding_rec else 'Not Started',
                'baggage_status': baggage_item.get_status_display() if baggage_item else 'No Checked Baggage',
            }
            
            if flight.status == FlightStatus.DEPARTED or booking.status in [BookingStatus.COMPLETED, BookingStatus.CANCELLED]:
                completed_bookings.append(booking_card_data)
            else:
                upcoming_bookings.append(booking_card_data)
        else:
            # Flight record deleted or unavailable
            invalid_card = {
                'booking': booking,
                'flight': None,
                'flight_valid': False,
                'flight_status': 'UNAVAILABLE',
                'is_cancelled': False,
                'boarding_status': 'Unavailable',
                'baggage_status': 'Unavailable',
            }
            upcoming_bookings.append(invalid_card)

    search_form = FlightSearchForm()
    
    context = {
        'upcoming_bookings': upcoming_bookings,
        'completed_bookings': completed_bookings,
        'total_bookings_count': all_bookings.count(),
        'has_bookings': all_bookings.exists(),
        'search_form': search_form,
    }
    return render(request, 'passenger/dashboard.html', context)


def flight_search(request):
    """
    Search available flights from Flight database.
    Shows scheduled, boarding, ready for departure, and recently departed flights with live status badges.
    """
    auto_update_all_flight_statuses()
    form = FlightSearchForm(request.GET or None)
    flights = Flight.objects.select_related(
        'airline', 'source_airport', 'destination_airport', 'aircraft', 'gate'
    ).order_by('scheduled_departure')
    
    has_filter = any([
        request.GET.get('source'),
        request.GET.get('destination'),
        request.GET.get('travel_date'),
        request.GET.get('airline'),
        request.GET.get('flight_number'),
    ])
    
    if not has_filter:
        flights = flights.filter(
            scheduled_departure__gte=timezone.now() - timedelta(hours=6)
        )
    
    if form.is_valid():
        source = form.cleaned_data.get('source')
        dest = form.cleaned_data.get('destination')
        travel_date = form.cleaned_data.get('travel_date')
        airline = form.cleaned_data.get('airline')
        fl_num = form.cleaned_data.get('flight_number')
        
        def _clean_airport_query(val):
            if not val:
                return []
            val = val.strip()
            if '(' in val and ')' in val:
                iata = val[val.find('(')+1 : val.find(')')].strip()
                city = val[:val.find('(')].strip()
                return [t for t in [iata, city] if t]
            return [val]

        if source:
            tokens = _clean_airport_query(source)
            sq = Q()
            for tok in tokens:
                sq |= Q(source_airport__city__icontains=tok) | Q(source_airport__iata_code__icontains=tok) | Q(source_airport__name__icontains=tok)
            flights = flights.filter(sq)
        if dest:
            tokens = _clean_airport_query(dest)
            dq = Q()
            for tok in tokens:
                dq |= Q(destination_airport__city__icontains=tok) | Q(destination_airport__iata_code__icontains=tok) | Q(destination_airport__name__icontains=tok)
            flights = flights.filter(dq)
        if travel_date:
            flights = flights.filter(scheduled_departure__date=travel_date)
        if airline:
            flights = flights.filter(Q(airline__name__icontains=airline) | Q(airline__iata_code__icontains=airline))
        if fl_num:
            flights = flights.filter(flight_number__icontains=fl_num)
            
    context = {
        'form': form,
        'flights': flights,
        'now': timezone.now()
    }
    return render(request, 'passenger/flight_search.html', context)


@login_required
@passenger_required
def flight_book(request, flight_id):
    """
    Pre-booking validation and interactive seat selection grid.
    Validations:
    1. Flight exists in DB
    2. Flight is not cancelled
    3. Flight is not departed (departure time not crossed)
    4. Seats available > 0
    """
    flight = get_object_or_404(Flight, pk=flight_id)
    flight.auto_sync_status()
    
    # 1. Validation Checks
    if flight.status == FlightStatus.CANCELLED:
        messages.error(request, f"❌ Booking Unavailable: Flight {flight.flight_number} has been cancelled and cannot be booked.")
        return redirect('flight_search')
        
    if flight.is_departed or flight.status == FlightStatus.DEPARTED or flight.effective_departure <= timezone.now():
        messages.error(request, f"❌ Booking Unavailable: Flight {flight.flight_number} has already departed.")
        return redirect('flight_search')

    if flight.is_boarding_closed or (flight.effective_departure - timezone.now()).total_seconds() <= 2 * 3600 or flight.status in [FlightStatus.READY_FOR_DEPARTURE, FlightStatus.BOARDING_COMPLETED]:
        messages.error(request, f"❌ Booking Closed: Flight {flight.flight_number} is within 2 hours of departure (Boarding Closed).")
        return redirect('flight_search')
        
    if not flight.is_bookable or flight.available_seats_count <= 0:
        messages.error(request, f"❌ Flight Full: No seats are currently available for Flight {flight.flight_number}.")
        return redirect('flight_search')
        
    # Get all seats for the aircraft
    if not flight.aircraft:
        messages.error(request, "Aircraft not assigned yet for this flight. Please check back shortly.")
        return redirect('flight_search')
        
    aircraft_seats = Seat.objects.filter(aircraft=flight.aircraft).order_by('row', 'column')
    
    # Query booked seat numbers for this flight
    booked_seat_numbers = set(
        flight.bookings.filter(
            status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]
        ).values_list('seat_number', flat=True)
    )
    
    # Structure seats by rows for easy template rendering
    seat_rows = {}
    for seat in aircraft_seats:
        if seat.row not in seat_rows:
            seat_rows[seat.row] = []
        is_booked = seat.seat_number in booked_seat_numbers
        seat_rows[seat.row].append({
            'seat': seat,
            'is_booked': is_booked,
            'seat_number': seat.seat_number,
            'seat_class': seat.seat_class,
            'is_window': seat.is_window,
            'is_aisle': seat.is_aisle,
            'is_emergency': seat.is_emergency_exit
        })
        
    initial_data = {
        'passenger_name': request.user.get_full_name() or request.user.username,
        'passenger_email': request.user.email,
        'passenger_phone': request.user.phone or '',
        'baggage_weight': 15.0
    }
    
    # Attach passport if profile exists
    if hasattr(request.user, 'passenger_profile'):
        initial_data['passenger_id_passport'] = request.user.passenger_profile.passport_number or ''
        
    form = PassengerBookingForm(initial=initial_data)
    
    context = {
        'flight': flight,
        'seat_rows': seat_rows,
        'form': form,
        'total_seats': aircraft_seats.count(),
        'available_seats': flight.available_seats_count,
    }
    return render(request, 'passenger/flight_book.html', context)


@login_required
@passenger_required
def confirm_booking(request, flight_id):
    """
    POST booking confirmation with immediate atomic seat re-check and departed validation.
    """
    if request.method != 'POST':
        return redirect('flight_book', flight_id=flight_id)
        
    flight = get_object_or_404(Flight, pk=flight_id)
    flight.auto_sync_status()
    form = PassengerBookingForm(request.POST)
    
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not form.is_valid():
        err_msg = "Please fill in all required passenger details."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('flight_book', flight_id=flight_id)
        
    # Re-verify flight status
    if flight.status == FlightStatus.CANCELLED:
        err_msg = f"❌ Booking Unavailable: Flight {flight.flight_number} has been cancelled."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('flight_search')
        
    if flight.is_departed or flight.status == FlightStatus.DEPARTED or flight.effective_departure <= timezone.now():
        err_msg = f"❌ Booking Unavailable: Flight {flight.flight_number} has already departed."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('flight_search')

    if flight.is_boarding_closed or (flight.effective_departure - timezone.now()).total_seconds() <= 2 * 3600 or flight.status in [FlightStatus.READY_FOR_DEPARTURE, FlightStatus.BOARDING_COMPLETED]:
        err_msg = f"❌ Booking Closed: Flight {flight.flight_number} is within 2 hours of departure (Boarding Closed)."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('flight_search')
        
    if not flight.is_bookable or flight.available_seats_count <= 0:
        err_msg = f"❌ Flight Full: No seats are currently available for Flight {flight.flight_number}."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('flight_search')
        
    seat_number = form.cleaned_data['seat_number'].strip().upper()
    if not seat_number:
        err_msg = "Please select an available seat from the aircraft seat map."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('flight_book', flight_id=flight_id)
        
    # Find seat model
    seat_obj = Seat.objects.filter(aircraft=flight.aircraft, seat_number=seat_number).first()
    if not seat_obj:
        err_msg = f"Seat {seat_number} is invalid for this aircraft."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('flight_book', flight_id=flight_id)
        
    # IMMEDIATE RE-CHECK: verify seat is still free right now
    already_taken = flight.bookings.filter(
        seat_number=seat_number,
        status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]
    ).exists()
    
    if already_taken:
        err_msg = f"❌ Seat {seat_number} was just booked by another passenger. Please choose another seat."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('flight_book', flight_id=flight_id)
        
    payment_method = form.cleaned_data.get('payment_method') or request.POST.get('payment_method') or 'UPI'
    txn_id = form.cleaned_data.get('transaction_id') or request.POST.get('transaction_id') or f"TXN_{timezone.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"

    # Create Booking
    booking_ref = Booking.generate_reference()
    booking = Booking.objects.create(
        booking_reference=booking_ref,
        passenger=request.user,
        passenger_name=form.cleaned_data['passenger_name'],
        passenger_email=form.cleaned_data['passenger_email'],
        passenger_phone=form.cleaned_data['passenger_phone'],
        passenger_id_passport=form.cleaned_data.get('passenger_id_passport', ''),
        flight=flight,
        seat=seat_obj,
        seat_number=seat_number,
        status=BookingStatus.CONFIRMED,
        booking_channel=BookingChannel.ONLINE_PASSENGER,
        ticket_price=flight.base_price
    )
    
    # Create Boarding Record
    seq = flight.boarding_records.count() + 1
    BoardingRecord.objects.create(
        booking=booking,
        flight=flight,
        passenger=request.user,
        boarding_status=BoardingStatus.NOT_STARTED,
        gate=flight.gate,
        sequence_number=seq
    )
    
    # Create Baggage Item if baggage specified
    bag_weight = form.cleaned_data.get('baggage_weight', 15.0)
    special_handling = form.cleaned_data.get('special_handling', False)
    
    bag_tag = Baggage.generate_tag(flight.flight_number)
    bag = Baggage.objects.create(
        tag_number=bag_tag,
        booking=booking,
        passenger=request.user,
        flight=flight,
        weight_kg=bag_weight,
        status=BaggageStatus.CHECKED_IN,
        special_handling=special_handling
    )
    # Calculate AI risk score for baggage
    bag_risk = predict_baggage_risk(bag, flight_delay=flight.delay_minutes)
    bag.risk_score = bag_risk['risk_score']
    bag.risk_level = bag_risk['risk_level']
    bag.risk_reason = bag_risk['reason']
    bag.save()
    
    BaggageScan.objects.create(
        baggage=bag,
        location='Online Self Check-in Hub',
        status_at_scan='Checked In',
        notes=f'Payment verified via {payment_method} & E-Tag generated'
    )
    
    # Create Confirmation Notification
    Notification.objects.create(
        recipient=request.user,
        title=f"Payment Received & Flight Confirmed: {flight.flight_number}",
        message=f"Payment of ₹{flight.base_price} received via {payment_method} (Txn: {txn_id}). Flight {flight.flight_number} to {flight.destination_airport.city} on {flight.scheduled_departure.strftime('%d %b %Y')} is confirmed! Booking Reference: {booking_ref}. Seat: {seat_number}.",
        category=NotificationCategory.GENERAL,
        flight_number=flight.flight_number
    )
    
    # Update AI Predictions for flight
    update_flight_ai_prediction(flight)
    
    if is_ajax:
        return JsonResponse({
            'status': 'success',
            'booking_id': booking.id,
            'booking_reference': booking_ref,
            'transaction_id': txn_id,
            'passenger_name': booking.passenger_name,
            'seat_number': booking.seat_number,
            'amount': f"{flight.base_price:.2f}",
            'payment_method': payment_method,
            'redirect_url': reverse('booking_ticket', kwargs={'booking_id': booking.id}),
            'message': f"✓ Payment of ₹{flight.base_price} successful via {payment_method}! Booking Reference: {booking_ref}"
        })

    messages.success(request, f"✓ Payment of ₹{flight.base_price} successful via {payment_method}! Booking Reference: {booking_ref}")
    return redirect('booking_ticket', booking_id=booking.id)


@login_required
def booking_ticket(request, booking_id):
    """
    Printable & Digital Boarding Pass / Ticket view.
    Accessible by passenger (owner) or Operations Manager.
    """
    booking = get_object_or_404(Booking, pk=booking_id)
    if not (request.user == booking.passenger or request.user.is_operations_manager):
        messages.error(request, "Unauthorized access to this booking.")
        return redirect('dashboard_redirect')
        
    flight = booking.flight
    boarding_rec = getattr(booking, 'boarding_record', None)
    baggage_items = booking.baggage_items.all()
    
    context = {
        'booking': booking,
        'flight': flight,
        'boarding_rec': boarding_rec,
        'baggage_items': baggage_items,
        'now': timezone.now()
    }
    return render(request, 'passenger/booking_ticket.html', context)


@login_required
@passenger_required
def passenger_flight_details(request, booking_id):
    """
    Complete Passenger Journey View:
    - Live flight status (retrieved directly from Flight model)
    - Departure scheduled vs expected
    - Gate, Seat
    - Boarding status & sequence
    - Baggage lifecycle timeline tracking
    - Delay explanation & AI advisory
    """
    booking = get_object_or_404(Booking, pk=booking_id, passenger=request.user)
    flight = booking.flight
    
    boarding_rec = getattr(booking, 'boarding_record', None)
    baggage_items = booking.baggage_items.all()
    
    # Baggage scan logs for timeline
    baggage_scans = BaggageScan.objects.filter(baggage__in=baggage_items).order_by('timestamp')
    
    context = {
        'booking': booking,
        'flight': flight,
        'boarding_rec': boarding_rec,
        'baggage_items': baggage_items,
        'baggage_scans': baggage_scans,
    }
    return render(request, 'passenger/flight_details.html', context)


@login_required
def passenger_cancel_booking(request, booking_id):
    """
    Cancel booking with confirmation:
    - Verifies user ownership (passenger) or manager authorization.
    - Sets Booking.status = BookingStatus.CANCELLED.
    - Re-releases seat availability immediately back to flight pool.
    - Updates/removes boarding record and marks baggage as cancelled.
    - Logs notification and updates AI flight predictions.
    - Supports GET (renders confirmation page) and POST (processes cancellation with optional AJAX support).
    """
    booking = get_object_or_404(Booking, pk=booking_id)
    
    # Ownership/Permission check
    if not (request.user == booking.passenger or request.user.is_operations_manager or request.user.is_superuser):
        messages.error(request, "Unauthorized access to this booking.")
        return redirect('dashboard_redirect')
        
    flight = booking.flight
    
    # Check if already cancelled
    if booking.status == BookingStatus.CANCELLED:
        messages.warning(request, f"Booking {booking.booking_reference} is already cancelled.")
        if request.user.is_passenger:
            return redirect('passenger_dashboard')
        return redirect('manager_passengers')
        
    # Check if flight already departed
    if flight and flight.status == FlightStatus.DEPARTED:
        messages.error(request, "❌ Cannot cancel booking for a flight that has already departed.")
        if request.user.is_passenger:
            return redirect('passenger_dashboard')
        return redirect('manager_passengers')
        
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        seat_num = booking.seat_number
        booking_ref = booking.booking_reference
        
        # 1. Update Booking Status to CANCELLED
        booking.status = BookingStatus.CANCELLED
        booking.save()
        
        # 2. Clean up Boarding Record
        if hasattr(booking, 'boarding_record'):
            try:
                booking.boarding_record.delete()
            except Exception:
                pass
                
        # 3. Clean up Baggage status & add scan
        for bag in booking.baggage_items.all():
            bag.status = BaggageStatus.DELIVERED
            bag.save()
            BaggageScan.objects.create(
                baggage=bag,
                location='Passenger Services / Cancellation Desk',
                status_at_scan='Cancelled',
                scanned_by=request.user if request.user.is_authenticated else None,
                notes='Booking cancelled by passenger. Luggage release requested.'
            )
            
        # 4. Create Notification
        Notification.objects.create(
            recipient=booking.passenger,
            title=f"Booking Cancelled: {flight.flight_number if flight else 'Flight'}",
            message=f"Your booking {booking_ref} for Flight {flight.flight_number if flight else ''} (Seat {seat_num}) has been successfully cancelled. Seat {seat_num} is now available for new bookings. A full refund of ₹{booking.ticket_price} has been processed.",
            category=NotificationCategory.GENERAL,
            flight_number=flight.flight_number if flight else ''
        )
        
        # 5. Recalculate AI Flight Predictions
        if flight:
            update_flight_ai_prediction(flight)
            
        success_msg = f"✓ Booking {booking_ref} cancelled successfully! Seat {seat_num} has been released and is now available for other passengers."
        
        if is_ajax:
            return JsonResponse({
                'status': 'success',
                'message': success_msg,
                'booking_reference': booking_ref,
                'seat_number': seat_num,
                'redirect_url': reverse('passenger_dashboard') if request.user.is_passenger else reverse('manager_passengers')
            })
            
        messages.success(request, success_msg)
        if request.user.is_passenger:
            return redirect('passenger_dashboard')
        return redirect('manager_passengers')
        
    # If GET request, render confirmation page
    context = {
        'booking': booking,
        'flight': flight,
    }
    return render(request, 'passenger/booking_cancel_confirm.html', context)


# ==========================================
# 2. GROUND STAFF VIEWS & WORKFLOWS
# ==========================================

@login_required
@staff_or_manager_required
def ground_staff_dashboard(request):
    """
    Ground Staff Dashboard:
    - Comprehensive airport-wide ground operations view (all active & scheduled flights)
    - Full telemetry: Gates, passenger loads, boarding progress, baggage status, turnarounds, alerts
    """
    # Fetch all active & upcoming flights across the airport
    flights_qs = Flight.objects.exclude(
        status__in=[FlightStatus.DEPARTED, FlightStatus.CANCELLED]
    ).select_related(
        'airline', 'source_airport', 'destination_airport', 'aircraft', 'gate'
    ).order_by('scheduled_departure')
    
    # Check if staff has any specific assignments (optional indicator)
    my_assigned_flight_ids = set(
        StaffAssignment.objects.filter(staff=request.user, status='ACTIVE').values_list('flight_id', flat=True)
    )
    
    # Collect operational metrics across all active flights
    flight_cards = []
    total_active_passengers = 0
    total_active_baggage = 0
    active_turnarounds = 0
    
    for f in flights_qs:
        total_pax = f.booked_seats_count
        boarded_pax = f.boarded_passengers_count
        baggage_count = f.baggage_items.count()
        loaded_baggage = f.baggage_items.filter(status=BaggageStatus.LOADED).count()
        
        total_active_passengers += total_pax
        total_active_baggage += baggage_count
        
        ground_op = getattr(f, 'ground_operation', None)
        turnaround_pct = ground_op.calculate_progress_percentage() if ground_op else 0.0
        if ground_op and ground_op.overall_status == TurnaroundOverallStatus.IN_PROGRESS:
            active_turnarounds += 1
            
        flight_cards.append({
            'flight': f,
            'is_my_assignment': f.id in my_assigned_flight_ids,
            'total_passengers': total_pax,
            'boarded_passengers': boarded_pax,
            'pending_passengers': max(0, total_pax - boarded_pax),
            'boarding_pct': f.boarding_progress_percentage,
            'baggage_count': baggage_count,
            'baggage_loaded_count': loaded_baggage,
            'ground_operation': ground_op,
            'turnaround_pct': turnaround_pct
        })
        
    # Recent operational alerts/issues across all flights
    operational_issues = OperationalIssue.objects.all().order_by('-created_at')[:6]
    
    context = {
        'flight_cards': flight_cards,
        'total_flights_count': flights_qs.count(),
        'total_assigned_passengers': total_active_passengers,
        'total_assigned_baggage': total_active_baggage,
        'active_turnarounds': active_turnarounds,
        'operational_issues': operational_issues,
    }
    return render(request, 'staff/dashboard.html', context)


@login_required
@staff_or_manager_required
def assigned_flight_detail(request, flight_id):
    """
    Detailed ground operations view for any flight in the airport.
    """
    flight = get_object_or_404(Flight.objects.select_related('airline', 'aircraft', 'source_airport', 'destination_airport', 'gate'), pk=flight_id)
    ground_op, _ = GroundOperation.objects.get_or_create(flight=flight)
    my_assignment = StaffAssignment.objects.filter(staff=request.user, flight=flight, status='ACTIVE').first()
    
    context = {
        'flight': flight,
        'ground_op': ground_op,
        'assignment': my_assignment,
        'total_passengers': flight.booked_seats_count,
        'boarded_passengers': flight.boarded_passengers_count,
        'pending_passengers': flight.pending_passengers_count,
        'boarding_pct': flight.boarding_progress_percentage,
        'baggage_count': flight.baggage_items.count(),
    }
    return render(request, 'staff/flight_detail.html', context)


@login_required
@staff_or_manager_required
def staff_boarding_manager(request, flight_id):
    """
    Boarding manager for any flight:
    - View passenger boarding manifest
    - 1-click Mark as Boarded
    - Boarding progress counters
    """
    flight = get_object_or_404(Flight.objects.select_related('airline', 'gate', 'source_airport', 'destination_airport'), pk=flight_id)
    q = request.GET.get('q', '').strip()
    boarding_records = flight.boarding_records.select_related('booking', 'passenger').all()
    
    if q:
        boarding_records = boarding_records.filter(
            Q(booking__passenger_name__icontains=q) |
            Q(booking__seat_number__icontains=q) |
            Q(booking__booking_reference__icontains=q)
        )
        
    context = {
        'flight': flight,
        'boarding_records': boarding_records,
        'total_passengers': flight.booked_seats_count,
        'boarded_passengers': flight.boarded_passengers_count,
        'pending_passengers': flight.pending_passengers_count,
        'boarding_pct': flight.boarding_progress_percentage,
        'search_query': q
    }
    return render(request, 'staff/boarding_manager.html', context)


@login_required
@staff_or_manager_required
def staff_mark_boarded(request, flight_id, boarding_id):
    """
    Mark passenger as boarded on any flight.
    """
    flight = get_object_or_404(Flight, pk=flight_id)
    rec = get_object_or_404(BoardingRecord, pk=boarding_id, flight=flight)
    rec.boarding_status = BoardingStatus.BOARDED
    rec.boarding_time = timezone.now()
    rec.scanned_by_staff = request.user
    rec.save()
    
    # Also update booking status
    booking = rec.booking
    booking.status = BookingStatus.BOARDED
    booking.save()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'boarded_count': flight.boarded_passengers_count,
            'pending_count': flight.pending_passengers_count,
            'boarding_pct': flight.boarding_progress_percentage,
            'passenger_name': booking.passenger_name,
            'seat_number': booking.seat_number
        })
        
    messages.success(request, f"✓ Marked {booking.passenger_name} (Seat {booking.seat_number}) as Boarded.")
    return redirect('staff_boarding_manager', flight_id=flight.id)


@login_required
@staff_or_manager_required
def staff_baggage_manager(request, flight_id):
    """
    Baggage operations for any flight:
    - View baggage items
    - Update baggage status
    - Log scans
    """
    flight = get_object_or_404(Flight.objects.select_related('airline', 'gate', 'source_airport', 'destination_airport'), pk=flight_id)
    baggage_items = flight.baggage_items.select_related('booking', 'passenger').all()
    scan_form = BaggageScanForm()
    
    context = {
        'flight': flight,
        'baggage_items': baggage_items,
        'scan_form': scan_form,
        'baggage_status_choices': BaggageStatus.choices
    }
    return render(request, 'staff/baggage_manager.html', context)


@login_required
@staff_or_manager_required
def staff_update_baggage(request, baggage_id):
    """
    Updates single baggage status and logs scan for any flight.
    """
    bag = get_object_or_404(Baggage.objects.select_related('flight', 'flight__gate', 'passenger'), pk=baggage_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        location = request.POST.get('location', f"Gate {bag.flight.gate.gate_number if bag.flight.gate else 'Ramp'}")
        notes = request.POST.get('notes', '')
        
        if new_status in dict(BaggageStatus.choices):
            bag.status = new_status
            bag.save()
            
            # Log scan
            BaggageScan.objects.create(
                baggage=bag,
                location=location,
                status_at_scan=new_status,
                scanned_by=request.user,
                notes=notes
            )
            
            # Send notification to passenger if delayed
            if new_status == BaggageStatus.DELAYED and bag.passenger:
                Notification.objects.create(
                    recipient=bag.passenger,
                    title="Baggage Update Notice",
                    message=f"Baggage {bag.tag_number} is currently experiencing a handling delay at {location}. Our baggage team is prioritizing your item.",
                    category=NotificationCategory.BAGGAGE,
                    flight_number=bag.flight.flight_number
                )
                
            messages.success(request, f"✓ Baggage {bag.tag_number} status updated to {bag.get_status_display()}.")
            
    return redirect('staff_baggage_manager', flight_id=bag.flight.id)


@login_required
@staff_or_manager_required
def staff_turnaround_tracker(request, flight_id):
    """
    Aircraft Turnaround Management for any flight:
    - View and update 9 distinct turnaround milestones
    - Progress indicator
    """
    flight = get_object_or_404(Flight.objects.select_related('airline', 'gate', 'source_airport', 'destination_airport'), pk=flight_id)
    ground_op, _ = GroundOperation.objects.get_or_create(flight=flight)
    
    if request.method == 'POST':
        milestone = request.POST.get('milestone')
        action_type = request.POST.get('action_type', 'complete') # 'start' or 'complete'
        now = timezone.now()
        
        if milestone == 'aircraft_arrived':
            ground_op.aircraft_arrived = now
        elif milestone == 'cleaning':
            if action_type == 'start':
                ground_op.cleaning_started = now
            else:
                ground_op.cleaning_completed = now
        elif milestone == 'fueling':
            if action_type == 'start':
                ground_op.fueling_started = now
            else:
                ground_op.fueling_completed = now
        elif milestone == 'catering':
            ground_op.catering_completed = now
        elif milestone == 'baggage_unloading':
            if action_type == 'start':
                ground_op.baggage_unloading_started = now
            else:
                ground_op.baggage_unloading_completed = now
        elif milestone == 'baggage_loading':
            if action_type == 'start':
                ground_op.baggage_loading_started = now
            else:
                ground_op.baggage_loading_completed = now
        elif milestone == 'cabin_prep':
            ground_op.cabin_prep_completed = now
        elif milestone == 'boarding':
            if action_type == 'start':
                ground_op.boarding_started = now
                flight.status = FlightStatus.BOARDING
                flight.save()
            else:
                ground_op.boarding_completed = now
                flight.status = FlightStatus.BOARDING_COMPLETED
                flight.save()
        elif milestone == 'ready_for_departure':
            ground_op.ready_for_departure = now
            ground_op.overall_status = TurnaroundOverallStatus.COMPLETED
            flight.status = FlightStatus.READY_FOR_DEPARTURE
            flight.save()
            
        ground_op.updated_by = request.user
        ground_op.save()
        
        # Recalculate AI Predictions
        update_flight_ai_prediction(flight)
        messages.success(request, f"✓ Turnaround milestone '{milestone.replace('_', ' ').title()}' updated!")
        return redirect('staff_turnaround_tracker', flight_id=flight.id)
        
    context = {
        'flight': flight,
        'ground_op': ground_op,
        'progress_pct': ground_op.calculate_progress_percentage()
    }
    return render(request, 'staff/turnaround_tracker.html', context)


@login_required
@staff_or_manager_required
def staff_report_issue(request):
    """
    Ground staff operational problem reporter for any active flight in the airport.
    """
    all_active_flights = Flight.objects.exclude(status__in=[FlightStatus.DEPARTED, FlightStatus.CANCELLED]).order_by('-scheduled_departure')
    
    if request.method == 'POST':
        form = OperationalIssueForm(request.POST)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.reported_by = request.user
            issue.save()
            
            # Notify Operations Managers
            managers = User.objects.filter(role=UserRole.OPERATIONS_MANAGER)
            for m in managers:
                Notification.objects.create(
                    recipient=m,
                    title=f"🚨 Ground Issue: {issue.title}",
                    message=f"Reported by {request.user.get_full_name() or request.user.username} ({request.user.staff_profile.get_department_display() if hasattr(request.user, 'staff_profile') else 'Staff'}). Priority: {issue.get_priority_display()}. Flight: {issue.flight.flight_number if issue.flight else 'Airport General'}.",
                    category=NotificationCategory.OPERATIONAL_ALERT,
                    flight_number=issue.flight.flight_number if issue.flight else None
                )
                
            messages.success(request, "✓ Operational issue logged and forwarded to Operations Control.")
            return redirect('ground_staff_dashboard')
    else:
        form = OperationalIssueForm()
        form.fields['flight'].queryset = all_active_flights
        
    return render(request, 'staff/report_issue.html', {'form': form})


# ==========================================
# 2B. ENHANCED STAFF SUITE (Seat Map, Booking, Weight, Gate Telemetry, Ticket Verification)
# ==========================================

@login_required
@staff_or_manager_required
def staff_flights(request):
    """
    Ground Staff Flight Operations & Telemetry Board:
    - View all flights, gate allocations, delay & on-time statuses
    - Passenger capacity, booked seats, and baggage weight totals
    - Direct access to Seat Allocation maps, Boarding Consoles, and Counter Booking
    """
    flights_qs = Flight.objects.select_related(
        'airline', 'aircraft', 'source_airport', 'destination_airport', 'gate'
    ).prefetch_related('bookings', 'baggage_items').all().order_by('scheduled_departure')

    # Optional filter by status
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        flights_qs = flights_qs.filter(status=status_filter)

    search_q = request.GET.get('q', '').strip()
    if search_q:
        flights_qs = flights_qs.filter(
            Q(flight_number__icontains=search_q) |
            Q(airline__name__icontains=search_q) |
            Q(source_airport__city__icontains=search_q) |
            Q(destination_airport__city__icontains=search_q) |
            Q(gate__gate_number__icontains=search_q)
        )

    flights_data = []
    my_assigned_flight_ids = set(
        StaffAssignment.objects.filter(staff=request.user, status='ACTIVE').values_list('flight_id', flat=True)
    )

    for fl in flights_qs:
        total_pax = fl.booked_seats_count
        capacity = fl.total_capacity
        total_bag_weight = sum(float(b.weight_kg) for b in fl.baggage_items.all() if b.weight_kg)
        
        flights_data.append({
            'flight': fl,
            'is_my_assignment': fl.id in my_assigned_flight_ids,
            'total_passengers': total_pax,
            'capacity': capacity,
            'available_seats': max(0, capacity - total_pax),
            'boarded_count': fl.boarded_passengers_count,
            'boarding_pct': fl.boarding_progress_percentage,
            'baggage_count': fl.baggage_items.count(),
            'total_baggage_weight': round(total_bag_weight, 1),
        })

    context = {
        'flights_data': flights_data,
        'status_filter': status_filter,
        'search_query': search_q,
        'total_flights_count': flights_qs.count(),
        'delayed_flights_count': Flight.objects.filter(status=FlightStatus.DELAYED).count(),
        'boarding_flights_count': Flight.objects.filter(status__in=[FlightStatus.BOARDING, FlightStatus.BOARDING_COMPLETED]).count(),
        'on_time_flights_count': Flight.objects.filter(status__in=[FlightStatus.SCHEDULED, FlightStatus.CONFIRMED], delay_minutes=0).count(),
    }
    return render(request, 'staff/flight_list.html', context)


@login_required
@staff_or_manager_required
def staff_flight_seats(request, flight_id):
    """
    Live 2D Seat Allocation Map for Ground Staff:
    - View every seat on the flight (booked vs available)
    - Passenger names, booking references, and baggage weight on each seat
    - Direct action to book available seats for walk-in passengers
    """
    flight = get_object_or_404(Flight.objects.select_related('airline', 'aircraft', 'source_airport', 'destination_airport', 'gate'), pk=flight_id)
    
    # Get all aircraft seats
    if not flight.aircraft:
        messages.error(request, "This flight has no aircraft configuration assigned.")
        return redirect('staff_flights')

    seats = flight.aircraft.seats.all().order_by('row', 'column')
    
    # Active bookings on this flight
    active_bookings = flight.bookings.filter(
        status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]
    ).select_related('passenger', 'boarding_record').prefetch_related('baggage_items')
    
    booking_by_seat = {b.seat_number: b for b in active_bookings}
    
    # Group seats into rows
    seat_rows = {}
    total_baggage_weight = 0.0
    heavy_baggage_count = 0

    for s in seats:
        if s.row not in seat_rows:
            seat_rows[s.row] = []
            
        b = booking_by_seat.get(s.seat_number)
        bag_weight = 0.0
        bag_tag = ""
        is_heavy = False
        boarding_stat = "NOT_BOOKED"

        if b:
            bags = b.baggage_items.all()
            if bags:
                bag_weight = sum(float(bag.weight_kg) for bag in bags if bag.weight_kg)
                bag_tag = bags[0].tag_number
                if bag_weight > 15.0:
                    is_heavy = True
                    heavy_baggage_count += 1
            total_baggage_weight += bag_weight
            
            if hasattr(b, 'boarding_record'):
                boarding_stat = b.boarding_record.boarding_status
            else:
                boarding_stat = "NOT_STARTED"

        seat_rows[s.row].append({
            'seat_number': s.seat_number,
            'column': s.column,
            'row': s.row,
            'seat_class': s.seat_class,
            'is_window': s.is_window,
            'is_aisle': s.is_aisle,
            'is_emergency_exit': s.is_emergency_exit,
            'is_booked': b is not None,
            'booking': b,
            'passenger_name': b.passenger_name if b else None,
            'passenger_email': b.passenger_email if b else None,
            'booking_reference': b.booking_reference if b else None,
            'baggage_weight': round(bag_weight, 1),
            'baggage_tag': bag_tag,
            'is_heavy_baggage': is_heavy,
            'boarding_status': boarding_stat,
        })

    context = {
        'flight': flight,
        'seat_rows': seat_rows,
        'total_seats': seats.count(),
        'booked_seats_count': active_bookings.count(),
        'available_seats_count': max(0, seats.count() - active_bookings.count()),
        'occupancy_pct': round((active_bookings.count() / seats.count()) * 100, 1) if seats.count() > 0 else 0,
        'total_baggage_weight': round(total_baggage_weight, 1),
        'heavy_baggage_count': heavy_baggage_count,
        'active_bookings': active_bookings,
    }
    return render(request, 'staff/seat_allocation.html', context)


@login_required
@staff_or_manager_required
def staff_counter_booking(request):
    """
    Staff Passenger Seat Booking & Baggage Check-In Desk:
    - Books seats for passengers directly at airport terminal desks
    - Captures passenger passport/ID, contact, seat number, and baggage weight
    - Issues verified booking and digital ticket
    """
    available_flights = Flight.objects.filter(
        status__in=[FlightStatus.SCHEDULED, FlightStatus.CONFIRMED, FlightStatus.BOARDING, FlightStatus.DELAYED]
    ).select_related('airline', 'source_airport', 'destination_airport', 'aircraft', 'gate').order_by('scheduled_departure')
    
    selected_flight_id = request.GET.get('flight_id') or request.POST.get('flight_id')
    selected_flight = None
    seat_rows = {}
    preselected_seat = request.GET.get('seat_number', '')

    if selected_flight_id:
        selected_flight = get_object_or_404(Flight, pk=selected_flight_id)
        if selected_flight.aircraft:
            all_seats = selected_flight.aircraft.seats.all().order_by('row', 'column')
            booked_seat_numbers = set(
                selected_flight.bookings.filter(
                    status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]
                ).values_list('seat_number', flat=True)
            )
            for s in all_seats:
                if s.row not in seat_rows:
                    seat_rows[s.row] = []
                seat_rows[s.row].append({
                    'seat_number': s.seat_number,
                    'seat_class': s.seat_class,
                    'is_booked': s.seat_number in booked_seat_numbers,
                    'is_window': s.is_window,
                    'is_aisle': s.is_aisle,
                })

    if request.method == 'POST':
        fl_id = request.POST.get('flight_id')
        pax_name = request.POST.get('passenger_name', '').strip()
        pax_email = request.POST.get('passenger_email', '').strip()
        pax_phone = request.POST.get('passenger_phone', '').strip()
        pax_passport = request.POST.get('passenger_id_passport', '').strip()
        seat_num = request.POST.get('seat_number', '').strip().upper()
        
        try:
            bag_weight = float(request.POST.get('baggage_weight', 15.0))
        except (ValueError, TypeError):
            bag_weight = 15.0

        fl = get_object_or_404(Flight, pk=fl_id)
        
        # Double check seat availability
        already_taken = Booking.objects.filter(
            flight=fl, seat_number=seat_num, 
            status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]
        ).exists()
        
        if already_taken:
            messages.error(request, f"Seat {seat_num} is already occupied on flight {fl.flight_number}. Please select another seat.")
            return redirect(f"{request.path}?flight_id={fl.id}")
            
        # Find or create User for passenger
        pax_user = User.objects.filter(email__iexact=pax_email).first()
        if not pax_user:
            uname = pax_email.split('@')[0] + str(random.randint(100, 999))
            pax_user = User.objects.create_user(
                username=uname,
                email=pax_email,
                password='pass123',
                first_name=pax_name.split()[0],
                last_name=' '.join(pax_name.split()[1:]) if len(pax_name.split()) > 1 else '',
                phone=pax_phone,
                role=UserRole.PASSENGER
            )
            PassengerProfile.objects.create(user=pax_user, passport_number=pax_passport)
            
        seat_obj = Seat.objects.filter(aircraft=fl.aircraft, seat_number=seat_num).first()
        booking_ref = Booking.generate_reference()
        
        booking = Booking.objects.create(
            booking_reference=booking_ref,
            passenger=pax_user,
            passenger_name=pax_name,
            passenger_email=pax_email,
            passenger_phone=pax_phone,
            passenger_id_passport=pax_passport,
            flight=fl,
            seat=seat_obj,
            seat_number=seat_num,
            status=BookingStatus.CONFIRMED,
            booking_channel=BookingChannel.OPERATIONS_COUNTER,
            ticket_price=fl.base_price
        )
        
        # Create Baggage item with exact recorded weight
        bag_tag = Baggage.generate_tag(fl.flight_number)
        bag_item = Baggage.objects.create(
            tag_number=bag_tag,
            booking=booking,
            passenger=pax_user,
            flight=fl,
            weight_kg=bag_weight,
            status=BaggageStatus.CHECKED_IN,
            special_handling=(bag_weight > 15.0 or request.POST.get('special_handling') == 'on')
        )
        BaggageScan.objects.create(
            baggage=bag_item,
            location=f"{fl.source_airport.iata_code} Counter Desk",
            status_at_scan="CHECKED_IN",
            scanned_by=request.user,
            notes=f"Staff Counter Check-in & Baggage Weighed: {bag_weight} kg"
        )
        
        # Create Boarding Record
        BoardingRecord.objects.create(
            booking=booking,
            flight=fl,
            passenger=pax_user,
            boarding_status=BoardingStatus.NOT_STARTED,
            gate=fl.gate,
            sequence_number=fl.boarding_records.count() + 1
        )
        
        # Send Passenger Notification
        Notification.objects.create(
            recipient=pax_user,
            title=f"Booking & Ticket Confirmed: {fl.flight_number}",
            message=f"Your ticket on flight {fl.flight_number} (Seat {seat_num}) has been issued at the Airport Operations Counter. Baggage {bag_tag} ({bag_weight} kg) registered.",
            category=NotificationCategory.GENERAL,
            flight_number=fl.flight_number
        )

        messages.success(
            request, 
            f"✓ Seat {seat_num} booked for {pax_name}! PNR: {booking_ref} &bull; Baggage {bag_tag} ({bag_weight} kg) logged."
        )
        return redirect('booking_ticket', booking_id=booking.id)
        
    context = {
        'available_flights': available_flights,
        'selected_flight': selected_flight,
        'seat_rows': seat_rows,
        'preselected_seat': preselected_seat,
    }
    return render(request, 'staff/counter_booking.html', context)


@login_required
@staff_or_manager_required
def staff_ticket_verification(request):
    """
    Staff Passenger Ticket Verification & Level-Advancement Desk:
    - Verifies passenger booking, ticket validity, flight status, and passport identity
    - Checks registered baggage weight
    - Step-by-step advance: Ticket Checked -> Security Verified -> Boarded
    """
    search_q = request.GET.get('q', '').strip() or request.POST.get('q', '').strip()
    found_booking = None
    flight_valid = False
    baggage_info = None

    if search_q:
        found_booking = Booking.objects.filter(
            Q(booking_reference__iexact=search_q) |
            Q(passenger_name__icontains=search_q) |
            Q(passenger_email__iexact=search_q) |
            Q(seat_number__iexact=search_q) |
            Q(baggage_items__tag_number__iexact=search_q)
        ).select_related('flight', 'passenger', 'seat', 'flight__airline', 'flight__gate', 'flight__source_airport', 'flight__destination_airport').prefetch_related('baggage_items', 'boarding_record').first()

        if found_booking:
            flight_valid = Flight.objects.filter(id=found_booking.flight_id).exists()
            baggage_info = found_booking.baggage_items.first()

    # Handle advancement POST
    if request.method == 'POST' and found_booking:
        action = request.POST.get('action')
        
        if action == 'advance_boarded':
            rec, _ = BoardingRecord.objects.get_or_create(
                booking=found_booking,
                defaults={
                    'flight': found_booking.flight,
                    'passenger': found_booking.passenger,
                    'gate': found_booking.flight.gate
                }
            )
            rec.boarding_status = BoardingStatus.BOARDED
            rec.boarding_time = timezone.now()
            rec.scanned_by_staff = request.user
            rec.save()

            found_booking.status = BookingStatus.BOARDED
            found_booking.save()

            Notification.objects.create(
                recipient=found_booking.passenger,
                title=f"Boarding Pass Scanned: {found_booking.flight.flight_number}",
                message=f"Your boarding pass has been verified by staff at Gate {found_booking.flight.gate.gate_number if found_booking.flight.gate else 'Desk'}. Have a pleasant flight!",
                category=NotificationCategory.BOARDING,
                flight_number=found_booking.flight.flight_number
            )
            messages.success(request, f"✓ Passenger {found_booking.passenger_name} verified and marked as BOARDED on flight {found_booking.flight.flight_number}!")

        elif action == 'update_baggage_weight':
            try:
                new_weight = float(request.POST.get('baggage_weight', 15.0))
                if baggage_info:
                    baggage_info.weight_kg = new_weight
                    baggage_info.special_handling = (new_weight > 15.0)
                    baggage_info.save()
                    BaggageScan.objects.create(
                        baggage=baggage_info,
                        location="Gate Verification Scale",
                        status_at_scan=baggage_info.status,
                        scanned_by=request.user,
                        notes=f"Weight updated at gate inspection: {new_weight} kg"
                    )
                    messages.success(request, f"✓ Baggage weight updated to {new_weight} kg for {found_booking.passenger_name}.")
            except (ValueError, TypeError):
                messages.error(request, "Invalid baggage weight value.")

        return redirect(f"{request.path}?q={found_booking.booking_reference}")

    # Recent Boarded Passengers
    recent_boardings = BoardingRecord.objects.filter(
        boarding_status=BoardingStatus.BOARDED
    ).select_related('booking', 'flight').order_by('-boarding_time')[:8]

    context = {
        'search_query': search_q,
        'booking': found_booking,
        'flight_valid': flight_valid,
        'baggage_info': baggage_info,
        'recent_boardings': recent_boardings,
    }
    return render(request, 'staff/ticket_verification.html', context)


@login_required
@staff_or_manager_required
def staff_advance_passenger_level(request, boarding_id):
    """
    Advances passenger boarding verification level (AJAX or Form POST).
    """
    rec = get_object_or_404(BoardingRecord.objects.select_related('booking', 'flight'), pk=boarding_id)
    rec.boarding_status = BoardingStatus.BOARDED
    rec.boarding_time = timezone.now()
    rec.scanned_by_staff = request.user
    rec.save()

    rec.booking.status = BookingStatus.BOARDED
    rec.booking.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'boarding_status': rec.boarding_status,
            'boarding_time': rec.boarding_time.strftime('%H:%M:%S'),
            'passenger_name': rec.booking.passenger_name,
            'seat_number': rec.booking.seat_number
        })

    messages.success(request, f"✓ Passenger {rec.booking.passenger_name} (Seat {rec.booking.seat_number}) advanced to BOARDED.")
    return redirect(request.META.get('HTTP_REFERER', 'staff_flights'))


@login_required
@staff_or_manager_required
def staff_all_baggage(request):
    """
    Airport-Wide Baggage Operations Desk for Ground Staff:
    - View and inspect baggage details of EVERY passenger on every flight
    - Search by Tag Number, Passenger Name, Flight Number, Seat, or PNR
    - Filter by Baggage Status (Checked In, Screened, Loaded, Delivered, Delayed, Missing)
    - Quick action to update baggage handling status and location scans
    """
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status')
    flight_filter = request.GET.get('flight_id')
    
    baggage_items = Baggage.objects.select_related(
        'passenger', 'flight', 'flight__airline', 'flight__gate', 'flight__source_airport', 'flight__destination_airport', 'booking'
    ).prefetch_related('scans').all().order_by('-created_at')
    
    if q:
        baggage_items = baggage_items.filter(
            Q(tag_number__icontains=q) |
            Q(passenger__first_name__icontains=q) |
            Q(passenger__last_name__icontains=q) |
            Q(booking__passenger_name__icontains=q) |
            Q(booking__booking_reference__icontains=q) |
            Q(booking__seat_number__icontains=q) |
            Q(flight__flight_number__icontains=q)
        )
    if status_filter:
        baggage_items = baggage_items.filter(status=status_filter)
    if flight_filter:
        baggage_items = baggage_items.filter(flight_id=flight_filter)
        
    total_count = Baggage.objects.count()
    loaded_count = Baggage.objects.filter(status=BaggageStatus.LOADED).count()
    delivered_count = Baggage.objects.filter(status=BaggageStatus.DELIVERED).count()
    delayed_count = Baggage.objects.filter(status=BaggageStatus.DELAYED).count()
    missing_count = Baggage.objects.filter(status=BaggageStatus.MISSING).count()
    total_weight = sum(float(b.weight_kg) for b in Baggage.objects.all() if b.weight_kg)
    
    all_flights = Flight.objects.exclude(status__in=[FlightStatus.DEPARTED, FlightStatus.CANCELLED]).order_by('flight_number')
    
    context = {
        'baggage_items': baggage_items,
        'total_count': total_count,
        'loaded_count': loaded_count,
        'delivered_count': delivered_count,
        'delayed_count': delayed_count,
        'missing_count': missing_count,
        'total_weight': round(total_weight, 1),
        'status_choices': BaggageStatus.choices,
        'search_query': q,
        'status_filter': status_filter,
        'flight_filter': flight_filter,
        'all_flights': all_flights,
    }
    return render(request, 'staff/all_baggage.html', context)


# ==========================================
# 3. AIRPORT OPERATIONS MANAGER VIEWS
# ==========================================

@login_required
@operations_manager_required
def manager_dashboard(request):
    """
    Airport Operations Center (AOC) Master Dashboard:
    - KPIs, Flights, Gates, Passengers, Baggage, Staff
    - Real-time AI Predictive Insights
    - Chart.js visual analytics
    """
    today = timezone.now().date()
    all_flights = Flight.objects.all()
    today_flights = all_flights.filter(scheduled_departure__date=today)
    
    # High-level Metrics
    total_flights_count = all_flights.count()
    active_flights_count = all_flights.exclude(status__in=[FlightStatus.DEPARTED, FlightStatus.CANCELLED]).count()
    delayed_flights_count = all_flights.filter(Q(status=FlightStatus.DELAYED) | Q(delay_minutes__gt=0)).count()
    cancelled_flights_count = all_flights.filter(status=FlightStatus.CANCELLED).count()
    
    # Gate Metrics
    all_gates = Gate.objects.all()
    available_gates_count = all_gates.filter(status=GateStatus.AVAILABLE).count()
    occupied_gates_count = all_gates.filter(status=GateStatus.OCCUPIED).count()
    
    # Passenger & Seat Metrics
    all_bookings = Booking.objects.all()
    total_passengers_count = all_bookings.filter(status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]).count()
    
    # Baggage Metrics
    all_baggage = Baggage.objects.all()
    total_baggage_count = all_baggage.count()
    delayed_baggage_count = all_baggage.filter(status__in=[BaggageStatus.DELAYED, BaggageStatus.MISSING]).count()
    
    # Ground Staff Metrics
    all_staff = GroundStaffProfile.objects.all()
    available_staff_count = all_staff.filter(availability_status=StaffAvailability.AVAILABLE).count()
    assigned_staff_count = all_staff.filter(availability_status__in=[StaffAvailability.ASSIGNED, StaffAvailability.BUSY]).count()
    
    # AI Predictive Insights
    ai_predictions = AIFlightPrediction.objects.select_related('flight', 'flight__airline', 'flight__source_airport', 'flight__destination_airport').order_by('-ground_risk_score')[:6]
    high_risk_flights = [p for p in ai_predictions if p.ground_risk_score > 40 or p.predicted_delay_minutes > 15]
    
    # Active Reported Issues
    open_issues = OperationalIssue.objects.filter(status__in=[IssueStatus.OPEN, IssueStatus.INVESTIGATING]).order_by('-priority', '-created_at')[:5]
    
    # Flight Schedule Feed
    recent_flights = all_flights.select_related('airline', 'source_airport', 'destination_airport', 'gate').order_by('scheduled_departure')[:8]
    
    context = {
        'total_flights_count': total_flights_count,
        'active_flights_count': active_flights_count,
        'delayed_flights_count': delayed_flights_count,
        'cancelled_flights_count': cancelled_flights_count,
        'available_gates_count': available_gates_count,
        'occupied_gates_count': occupied_gates_count,
        'total_passengers_count': total_passengers_count,
        'total_baggage_count': total_baggage_count,
        'delayed_baggage_count': delayed_baggage_count,
        'available_staff_count': available_staff_count,
        'assigned_staff_count': assigned_staff_count,
        'ai_predictions': ai_predictions,
        'high_risk_flights': high_risk_flights,
        'open_issues': open_issues,
        'recent_flights': recent_flights,
    }
    return render(request, 'manager/dashboard.html', context)


@login_required
@operations_manager_required
def manager_flights(request):
    """
    Flight Management Hub: Add, edit, filter, manage flights.
    """
    status_filter = request.GET.get('status')
    q = request.GET.get('q', '').strip()
    
    flights = Flight.objects.select_related('airline', 'aircraft', 'source_airport', 'destination_airport', 'gate').all().order_by('-scheduled_departure')
    
    if status_filter:
        flights = flights.filter(status=status_filter)
    if q:
        flights = flights.filter(
            Q(flight_number__icontains=q) |
            Q(airline__name__icontains=q) |
            Q(source_airport__city__icontains=q) |
            Q(destination_airport__city__icontains=q)
        )
        
    context = {
        'flights': flights,
        'status_filter': status_filter,
        'status_choices': FlightStatus.choices,
        'search_query': q
    }
    return render(request, 'manager/flight_list.html', context)


@login_required
@operations_manager_required
def manager_add_flight(request):
    """
    Add new flight.
    """
    if request.method == 'POST':
        form = FlightForm(request.POST)
        if form.is_valid():
            flight = form.save()
            GroundOperation.objects.create(flight=flight)
            update_flight_ai_prediction(flight)
            messages.success(request, f"✓ Flight {flight.flight_number} created successfully!")
            return redirect('manager_flights')
    else:
        form = FlightForm()
        
    return render(request, 'manager/flight_form.html', {'form': form, 'title': 'Schedule New Flight'})


@login_required
@operations_manager_required
def manager_edit_flight(request, pk):
    """
    Edit flight details.
    """
    flight = get_object_or_404(Flight, pk=pk)
    if request.method == 'POST':
        form = FlightForm(request.POST, instance=flight)
        if form.is_valid():
            flight = form.save()
            update_flight_ai_prediction(flight)
            messages.success(request, f"✓ Flight {flight.flight_number} updated successfully!")
            return redirect('manager_flights')
    else:
        form = FlightForm(instance=flight)
        
    return render(request, 'manager/flight_form.html', {'form': form, 'flight': flight, 'title': f'Edit Flight {flight.flight_number}'})


@login_required
@operations_manager_required
def manager_update_flight_status(request, pk):
    """
    Operational control: update status, record delay, assign gate, or cancel flight.
    Generates automatic notifications to all booked passengers and assigned staff!
    """
    flight = get_object_or_404(Flight, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        gate_id = request.POST.get('gate')
        delay_minutes = int(request.POST.get('delay_minutes') or 0)
        delay_reason = request.POST.get('delay_reason', '')
        cancellation_reason = request.POST.get('cancellation_reason', '')
        
        old_status = flight.status
        old_gate = flight.gate
        
        flight.status = new_status
        if gate_id:
            flight.gate = Gate.objects.filter(pk=gate_id).first()
        else:
            flight.gate = None
            
        flight.delay_minutes = delay_minutes
        flight.delay_reason = delay_reason
        flight.cancellation_reason = cancellation_reason
        
        if new_status == FlightStatus.DEPARTED and not flight.actual_departure:
            flight.actual_departure = timezone.now()
        elif new_status == FlightStatus.ARRIVED and not flight.actual_arrival:
            flight.actual_arrival = timezone.now()
            
        flight.save()
        
        # Record delay log if delayed
        if delay_minutes > 0 and delay_reason:
            DelayRecord.objects.create(
                flight=flight,
                delay_minutes=delay_minutes,
                reason=delay_reason,
                detailed_description=f"Operational update by {request.user.get_full_name() or request.user.username}",
                recorded_by=request.user
            )
            
        # NOTIFICATION DISPATCH
        # 1. To Booked Passengers
        booked_passengers = User.objects.filter(bookings__flight=flight, bookings__status=BookingStatus.CONFIRMED).distinct()
        for p in booked_passengers:
            if delay_minutes > 0 and old_status != FlightStatus.DELAYED:
                Notification.objects.create(
                    recipient=p,
                    title=f"Flight Delay Notice: {flight.flight_number}",
                    message=f"Flight {flight.flight_number} is delayed by {delay_minutes} minutes ({flight.get_delay_reason_display() if flight.delay_reason else 'Operational reason'}). Expected departure: {flight.effective_departure.strftime('%H:%M')}.",
                    category=NotificationCategory.FLIGHT_DELAY,
                    flight_number=flight.flight_number
                )
            if flight.gate != old_gate and flight.gate is not None:
                Notification.objects.create(
                    recipient=p,
                    title=f"Gate Change: {flight.flight_number}",
                    message=f"Your flight {flight.flight_number} has been assigned to Gate {flight.gate.gate_number} ({flight.gate.terminal}).",
                    category=NotificationCategory.GATE_CHANGE,
                    flight_number=flight.flight_number
                )
            if new_status == FlightStatus.CANCELLED:
                Notification.objects.create(
                    recipient=p,
                    title=f"❌ Flight Cancelled: {flight.flight_number}",
                    message=f"We regret to inform you that flight {flight.flight_number} has been cancelled. Reason: {flight.cancellation_reason or 'Operational reasons'}. Please contact airport support.",
                    category=NotificationCategory.FLIGHT_DELAY,
                    flight_number=flight.flight_number
                )
                
        # 2. To Assigned Staff
        assigned_staff = User.objects.filter(flight_assignments__flight=flight, flight_assignments__status='ACTIVE')
        for s in assigned_staff:
            Notification.objects.create(
                recipient=s,
                title=f"Operational Update: {flight.flight_number}",
                message=f"Status changed to {flight.get_status_display()}. Gate: {flight.gate.gate_number if flight.gate else 'Unassigned'}. Delay: {flight.delay_minutes}m.",
                category=NotificationCategory.OPERATIONAL_ALERT,
                flight_number=flight.flight_number
            )
            
        # Recalculate AI Prediction
        update_flight_ai_prediction(flight)
        
        messages.success(request, f"✓ Flight {flight.flight_number} operational status updated successfully!")
        return redirect('manager_flights')
        
    context = {
        'flight': flight,
        'gates': Gate.objects.all(),
        'status_choices': FlightStatus.choices,
        'delay_reasons': DelayReason.choices
    }
    return render(request, 'manager/flight_status_modal.html', context)


@login_required
@operations_manager_required
def manager_aircraft(request):
    """
    Aircraft Fleet Management.
    """
    fleet = Aircraft.objects.select_related('airline').all()
    return render(request, 'manager/aircraft_list.html', {'fleet': fleet})


@login_required
@operations_manager_required
def manager_add_aircraft(request):
    if request.method == 'POST':
        form = AircraftForm(request.POST)
        if form.is_valid():
            ac = form.save()
            # Generate default seat layout
            rows = 30 if ac.aircraft_type == 'NARROW_BODY' else (50 if ac.aircraft_type == 'WIDE_BODY' else 18)
            seats_to_create = []
            for r in range(1, rows + 1):
                for c in ['A', 'B', 'C', 'D', 'E', 'F']:
                    seat_cls = SeatClass.BUSINESS if r <= 3 else SeatClass.ECONOMY
                    seats_to_create.append(Seat(
                        aircraft=ac,
                        seat_number=f"{r}{c}",
                        row=r,
                        column=c,
                        seat_class=seat_cls,
                        is_window=(c in ['A', 'F']),
                        is_aisle=(c in ['C', 'D']),
                        is_emergency_exit=(r in [12, 13])
                    ))
            Seat.objects.bulk_create(seats_to_create)
            messages.success(request, f"✓ Aircraft {ac.registration_number} added with {len(seats_to_create)} seat configuration!")
            return redirect('manager_aircraft')
    else:
        form = AircraftForm()
    return render(request, 'manager/aircraft_form.html', {'form': form, 'title': 'Register New Aircraft'})


@login_required
@operations_manager_required
def manager_gates(request):
    """
    Airport Gate Board & Terminal status.
    """
    gates = Gate.objects.all()
    flights_needing_gates = Flight.objects.filter(
        gate__isnull=True,
        status__in=[FlightStatus.SCHEDULED, FlightStatus.CONFIRMED, FlightStatus.DELAYED]
    ).select_related('airline', 'aircraft', 'source_airport', 'destination_airport')
    
    context = {
        'gates': gates,
        'flights_needing_gates': flights_needing_gates,
    }
    return render(request, 'manager/gate_management.html', context)


@login_required
@operations_manager_required
def manager_allocate_gate(request, flight_id):
    """
    Intelligent AI Gate Allocation Engine:
    - Runs multi-factor scoring (Aircraft compatibility, schedule conflict, domestic/intl terminal, turnaround suitability)
    - Recommends best gates with scores & explanations
    - Allows 1-click allocation or manual selection
    """
    flight = get_object_or_404(Flight, pk=flight_id)
    
    if request.method == 'POST':
        gate_id = request.POST.get('gate_id')
        gate = get_object_or_404(Gate, pk=gate_id)
        
        flight.gate = gate
        flight.save()
        
        # Log gate allocation record
        start = flight.scheduled_departure - timedelta(minutes=45)
        end = flight.scheduled_departure + timedelta(minutes=15)
        GateAllocation.objects.create(
            flight=flight,
            gate=gate,
            allocated_by=request.user,
            start_time=start,
            end_time=end
        )
        
        # Notify passengers
        for b in flight.bookings.filter(status=BookingStatus.CONFIRMED):
            Notification.objects.create(
                recipient=b.passenger,
                title=f"Gate Assigned: {flight.flight_number}",
                message=f"Flight {flight.flight_number} will depart from Gate {gate.gate_number} ({gate.terminal}).",
                category=NotificationCategory.GATE_CHANGE,
                flight_number=flight.flight_number
            )
            
        update_flight_ai_prediction(flight)
        messages.success(request, f"✓ Gate {gate.gate_number} successfully allocated to flight {flight.flight_number}!")
        return redirect('manager_gates')
        
    # Get AI recommendations
    gate_recommendations = recommend_gates(flight, limit=8)
    
    context = {
        'flight': flight,
        'gate_recommendations': gate_recommendations,
        'all_gates': Gate.objects.all(),
    }
    return render(request, 'manager/gate_allocate.html', context)


@login_required
@operations_manager_required
def manager_passengers(request):
    """
    Comprehensive Passenger Manifest & User Telemetry Control Board:
    - Search and filter all passengers across flights
    - Find which user is on which flight, seat number, gate, departure time
    - See exact status: Boarded vs Waiting / Not Started vs Checked-in / Cancelled
    - See baggage count and total weight
    - Explore all registered users (Passengers, Ground Staff, Managers) and their status
    """
    q = request.GET.get('q', '').strip()
    flight_id = request.GET.get('flight_id', '').strip()
    boarding_filter = request.GET.get('boarding_status', '').strip()
    role_filter = request.GET.get('role', '').strip()
    tab = request.GET.get('tab', 'manifest').strip() # 'manifest' or 'users'

    # 1. Base Query for Passenger Bookings & Flight Manifest
    bookings_qs = Booking.objects.select_related(
        'passenger', 'passenger__passenger_profile',
        'flight', 'flight__airline', 'flight__source_airport', 'flight__destination_airport', 'flight__gate',
        'seat'
    ).prefetch_related('baggage_items', 'boarding_record').order_by('-flight__scheduled_departure', 'seat_number')

    if flight_id and flight_id.isdigit():
        bookings_qs = bookings_qs.filter(flight_id=int(flight_id))

    if boarding_filter:
        if boarding_filter == 'BOARDED':
            bookings_qs = bookings_qs.filter(
                Q(status=BookingStatus.BOARDED) | Q(boarding_record__boarding_status=BoardingStatus.BOARDED)
            )
        elif boarding_filter == 'WAITING':
            bookings_qs = bookings_qs.filter(
                status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN]
            ).exclude(boarding_record__boarding_status=BoardingStatus.BOARDED)
        elif boarding_filter == 'CHECKED_IN':
            bookings_qs = bookings_qs.filter(status=BookingStatus.CHECKED_IN)
        elif boarding_filter == 'CANCELLED':
            bookings_qs = bookings_qs.filter(status=BookingStatus.CANCELLED)

    if q and tab != 'users':
        bookings_qs = bookings_qs.filter(
            Q(passenger_name__icontains=q) |
            Q(passenger_email__icontains=q) |
            Q(passenger_phone__icontains=q) |
            Q(passenger__username__icontains=q) |
            Q(booking_reference__icontains=q) |
            Q(flight__flight_number__icontains=q) |
            Q(seat_number__icontains=q) |
            Q(passenger_id_passport__icontains=q)
        ).distinct()

    # Pre-compute metrics on all bookings (for KPI counters)
    all_active_bookings = Booking.objects.select_related('boarding_record', 'flight')
    if flight_id and flight_id.isdigit():
        all_active_bookings = all_active_bookings.filter(flight_id=int(flight_id))

    total_passengers_count = all_active_bookings.count()
    boarded_count = all_active_bookings.filter(
        Q(status=BookingStatus.BOARDED) | Q(boarding_record__boarding_status=BoardingStatus.BOARDED)
    ).count()
    cancelled_count = all_active_bookings.filter(status=BookingStatus.CANCELLED).count()
    waiting_count = max(0, total_passengers_count - boarded_count - cancelled_count)
    checked_in_count = all_active_bookings.filter(status=BookingStatus.CHECKED_IN).count()

    # Total baggage weight across manifest
    total_baggage_items = Baggage.objects.all()
    if flight_id and flight_id.isdigit():
        total_baggage_items = total_baggage_items.filter(flight_id=int(flight_id))
    total_baggage_weight = total_baggage_items.aggregate(Sum('weight_kg'))['weight_kg__sum'] or 0.0

    # 2. Registered Users Query (for Users Directory Tab)
    users_qs = User.objects.select_related('passenger_profile', 'staff_profile', 'manager_profile').prefetch_related('bookings', 'flight_assignments').order_by('-date_joined')
    if role_filter:
        users_qs = users_qs.filter(role=role_filter)
    if q and tab == 'users':
        users_qs = users_qs.filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )

    # 3. Available Flights for selector
    all_flights = Flight.objects.select_related('airline', 'source_airport', 'destination_airport', 'gate').all().order_by('-scheduled_departure')

    # Also for backwards-compatibility / passenger list
    passengers_fallback = User.objects.filter(role=UserRole.PASSENGER).prefetch_related('bookings', 'bookings__flight')

    context = {
        'bookings': bookings_qs,
        'users': users_qs,
        'passengers': passengers_fallback,
        'all_flights': all_flights,
        'selected_flight_id': int(flight_id) if flight_id and flight_id.isdigit() else None,
        'search_query': q,
        'boarding_filter': boarding_filter,
        'role_filter': role_filter,
        'tab': tab,
        'total_passengers_count': total_passengers_count,
        'boarded_count': boarded_count,
        'waiting_count': waiting_count,
        'checked_in_count': checked_in_count,
        'cancelled_count': cancelled_count,
        'total_baggage_count': total_baggage_items.count(),
        'total_baggage_weight': round(float(total_baggage_weight), 1),
        'total_users_count': User.objects.count(),
        'total_staff_users_count': User.objects.filter(role=UserRole.GROUND_STAFF).count(),
        'total_passenger_users_count': User.objects.filter(role=UserRole.PASSENGER).count(),
        'total_manager_users_count': User.objects.filter(role=UserRole.OPERATIONS_MANAGER).count(),
    }
    return render(request, 'manager/passenger_list.html', context)


@login_required
@operations_manager_required
def manager_counter_booking(request):
    """
    Operations Counter Booking:
    Simulates airport walk-in ticket desk booking for unbooked passengers.
    """
    available_flights = Flight.objects.filter(
        status__in=[FlightStatus.SCHEDULED, FlightStatus.CONFIRMED],
        scheduled_departure__gte=timezone.now()
    ).select_related('airline', 'aircraft', 'source_airport', 'destination_airport')
    
    selected_flight_id = request.GET.get('flight_id')
    selected_flight = None
    seat_rows = {}
    
    if selected_flight_id:
        selected_flight = get_object_or_404(Flight, pk=selected_flight_id)
        if selected_flight.aircraft:
            seats = Seat.objects.filter(aircraft=selected_flight.aircraft).order_by('row', 'column')
            booked = set(selected_flight.bookings.filter(status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]).values_list('seat_number', flat=True))
            for s in seats:
                if s.row not in seat_rows:
                    seat_rows[s.row] = []
                seat_rows[s.row].append({
                    'seat': s,
                    'is_booked': s.seat_number in booked,
                    'seat_number': s.seat_number
                })
                
    if request.method == 'POST':
        fl_id = request.POST.get('flight_id')
        fl = get_object_or_404(Flight, pk=fl_id)
        
        pax_name = request.POST.get('passenger_name', '').strip()
        pax_email = request.POST.get('passenger_email', '').strip()
        pax_phone = request.POST.get('passenger_phone', '').strip()
        pax_passport = request.POST.get('passenger_id_passport', '').strip()
        seat_num = request.POST.get('seat_number', '').strip().upper()
        
        # Check or create user for walk-in passenger
        pax_user = User.objects.filter(email=pax_email).first()
        if not pax_user:
            uname = pax_email.split('@')[0] + str(random.randint(100, 999))
            pax_user = User.objects.create_user(
                username=uname,
                email=pax_email,
                password='pass123',
                first_name=pax_name.split()[0],
                last_name=' '.join(pax_name.split()[1:]) if len(pax_name.split()) > 1 else '',
                phone=pax_phone,
                role=UserRole.PASSENGER
            )
            PassengerProfile.objects.create(user=pax_user, passport_number=pax_passport)
            
        seat_obj = Seat.objects.filter(aircraft=fl.aircraft, seat_number=seat_num).first()
        booking_ref = Booking.generate_reference()
        
        booking = Booking.objects.create(
            booking_reference=booking_ref,
            passenger=pax_user,
            passenger_name=pax_name,
            passenger_email=pax_email,
            passenger_phone=pax_phone,
            passenger_id_passport=pax_passport,
            flight=fl,
            seat=seat_obj,
            seat_number=seat_num,
            status=BookingStatus.CONFIRMED,
            booking_channel=BookingChannel.OPERATIONS_COUNTER,
            ticket_price=fl.base_price
        )
        
        BoardingRecord.objects.create(
            booking=booking,
            flight=fl,
            passenger=pax_user,
            boarding_status=BoardingStatus.NOT_STARTED,
            gate=fl.gate,
            sequence_number=fl.boarding_records.count() + 1
        )
        
        messages.success(request, f"✓ Counter Ticket issued! Booking Reference: {booking_ref} for {pax_name}.")
        return redirect('booking_ticket', booking_id=booking.id)
        
    context = {
        'available_flights': available_flights,
        'selected_flight': selected_flight,
        'seat_rows': seat_rows,
    }
    return render(request, 'manager/counter_booking.html', context)


@login_required
@operations_manager_required
def manager_staff(request):
    """
    Ground Staff Workforce & Gate Dispatch Command:
    - Lists all ground staff, their department, shift, approval & availability status
    - Shows which staff is assigned to which flight and which gate
    - Displays operational telemetry: counter bookings done, passenger boardings scanned, baggage scanned
    """
    q = request.GET.get('q', '').strip()
    dept_filter = request.GET.get('department', '').strip()
    avail_filter = request.GET.get('availability', '').strip()
    approval_filter = request.GET.get('approval', '').strip()

    staff_profiles = GroundStaffProfile.objects.select_related('user', 'approved_by').prefetch_related(
        'user__flight_assignments',
        'user__flight_assignments__flight',
        'user__flight_assignments__flight__gate',
        'user__flight_assignments__flight__airline',
        'user__scanned_boardings',
        'user__baggage_items'
    ).order_by('-id')

    if dept_filter:
        staff_profiles = staff_profiles.filter(department=dept_filter)
    if avail_filter:
        staff_profiles = staff_profiles.filter(availability_status=avail_filter)
    if approval_filter:
        if approval_filter == 'APPROVED':
            staff_profiles = staff_profiles.filter(is_approved=True)
        elif approval_filter == 'PENDING':
            staff_profiles = staff_profiles.filter(is_approved=False)

    if q:
        staff_profiles = staff_profiles.filter(
            Q(employee_id__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__username__icontains=q) |
            Q(user__email__icontains=q) |
            Q(station__icontains=q) |
            Q(user__flight_assignments__flight__flight_number__icontains=q) |
            Q(user__flight_assignments__flight__gate__gate_number__icontains=q)
        ).distinct()

    staff_data = []
    for sp in staff_profiles:
        active_assignments = sp.user.flight_assignments.filter(status='ACTIVE').select_related('flight', 'flight__gate', 'flight__airline')
        scanned_boardings_count = BoardingRecord.objects.filter(scanned_by_staff=sp.user).count()
        scanned_baggage_count = BaggageScan.objects.filter(scanned_by=sp.user).count()
        counter_bookings_count = Booking.objects.filter(passenger=sp.user, booking_channel=BookingChannel.OPERATIONS_COUNTER).count()

        staff_data.append({
            'profile': sp,
            'user': sp.user,
            'active_assignments': active_assignments,
            'scanned_boardings_count': scanned_boardings_count,
            'scanned_baggage_count': scanned_baggage_count,
            'counter_bookings_count': counter_bookings_count,
        })

    total_staff = GroundStaffProfile.objects.count()
    approved_count = GroundStaffProfile.objects.filter(is_approved=True).count()
    pending_count = GroundStaffProfile.objects.filter(is_approved=False).count()
    assigned_count = GroundStaffProfile.objects.filter(availability_status=StaffAvailability.ASSIGNED).count()
    available_count = GroundStaffProfile.objects.filter(availability_status=StaffAvailability.AVAILABLE).count()

    context = {
        'staff_members': staff_profiles,
        'staff_data': staff_data,
        'total_staff': total_staff,
        'approved_count': approved_count,
        'pending_count': pending_count,
        'assigned_count': assigned_count,
        'available_count': available_count,
        'search_query': q,
        'dept_filter': dept_filter,
        'avail_filter': avail_filter,
        'approval_filter': approval_filter,
        'departments': GroundStaffDepartment.choices,
        'availabilities': StaffAvailability.choices,
    }
    return render(request, 'manager/staff_list.html', context)


@login_required
@operations_manager_required
def manager_approve_staff(request, staff_id):
    """
    Operations Manager approves or revokes Ground Staff account.
    """
    staff_profile = get_object_or_404(GroundStaffProfile, pk=staff_id)
    if request.method == 'POST':
        action = request.POST.get('action', 'approve')
        if action == 'revoke':
            staff_profile.is_approved = False
            staff_profile.save()
            messages.info(request, f"Ground Staff {staff_profile.user.get_full_name() or staff_profile.user.username} account approval revoked.")
        else:
            staff_profile.is_approved = True
            staff_profile.approved_at = timezone.now()
            staff_profile.approved_by = request.user
            staff_profile.save()

            # Create notification for staff
            Notification.objects.create(
                recipient=staff_profile.user,
                title="Ground Staff Account Approved",
                message="Your Ground Staff account has been approved by Operations Management. You can now access the Ground Staff Portal.",
                category=NotificationCategory.STAFF_ASSIGNMENT
            )
            messages.success(request, f"Ground Staff {staff_profile.user.get_full_name() or staff_profile.user.username} ({staff_profile.employee_id}) has been approved successfully!")
            
    return redirect('manager_staff')


@login_required
@operations_manager_required
def manager_assign_staff(request):
    """
    Assign ground staff to a flight.
    """
    if request.method == 'POST':
        form = StaffAssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save()
            # Update staff availability
            if hasattr(assignment.staff, 'staff_profile'):
                assignment.staff.staff_profile.availability_status = StaffAvailability.ASSIGNED
                assignment.staff.staff_profile.save()
                
            Notification.objects.create(
                recipient=assignment.staff,
                title=f"New Flight Assignment: {assignment.flight.flight_number}",
                message=f"You have been assigned to flight {assignment.flight.flight_number} as {assignment.role_in_flight}.",
                category=NotificationCategory.STAFF_ASSIGNMENT,
                flight_number=assignment.flight.flight_number
            )
            messages.success(request, f"✓ {assignment.staff.get_full_name() or assignment.staff.username} assigned to {assignment.flight.flight_number}!")
            return redirect('manager_staff')
    else:
        form = StaffAssignmentForm()
        form.fields['staff'].queryset = User.objects.filter(role=UserRole.GROUND_STAFF)
        form.fields['flight'].queryset = Flight.objects.exclude(status__in=[FlightStatus.DEPARTED, FlightStatus.CANCELLED])
        
    return render(request, 'manager/staff_assign.html', {'form': form})


@login_required
@operations_manager_required
def manager_baggage(request):
    """
    Airport-wide Baggage Management & Tracking Board.
    """
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status')
    
    baggage_items = Baggage.objects.select_related('passenger', 'flight', 'booking').all().order_by('-created_at')
    
    if q:
        baggage_items = baggage_items.filter(
            Q(tag_number__icontains=q) |
            Q(passenger__first_name__icontains=q) |
            Q(passenger__last_name__icontains=q) |
            Q(flight__flight_number__icontains=q)
        )
    if status_filter:
        baggage_items = baggage_items.filter(status=status_filter)
        
    total_count = Baggage.objects.count()
    loaded_count = Baggage.objects.filter(status=BaggageStatus.LOADED).count()
    delivered_count = Baggage.objects.filter(status=BaggageStatus.DELIVERED).count()
    delayed_count = Baggage.objects.filter(status=BaggageStatus.DELAYED).count()
    missing_count = Baggage.objects.filter(status=BaggageStatus.MISSING).count()
    
    context = {
        'baggage_items': baggage_items,
        'total_count': total_count,
        'loaded_count': loaded_count,
        'delivered_count': delivered_count,
        'delayed_count': delayed_count,
        'missing_count': missing_count,
        'status_choices': BaggageStatus.choices,
        'search_query': q,
        'status_filter': status_filter
    }
    return render(request, 'manager/baggage_operations.html', context)


@login_required
@operations_manager_required
def manager_boarding(request):
    """
    Airport-wide boarding operations monitor with full passenger manifest per flight.
    """
    active_flights = Flight.objects.filter(
        status__in=[
            FlightStatus.SCHEDULED,
            FlightStatus.CONFIRMED,
            FlightStatus.BOARDING,
            FlightStatus.BOARDING_COMPLETED,
            FlightStatus.READY_FOR_DEPARTURE
        ]
    ).select_related('airline', 'source_airport', 'destination_airport', 'gate').order_by('scheduled_departure')
    
    flight_boarding_data = []
    for f in active_flights:
        bookings = f.bookings.select_related('passenger', 'boarding_record').prefetch_related('baggage_items').all().order_by('seat_number')
        flight_boarding_data.append({
            'flight': f,
            'total_passengers': f.booked_seats_count,
            'boarded_passengers': f.boarded_passengers_count,
            'pending_passengers': f.pending_passengers_count,
            'boarding_pct': f.boarding_progress_percentage,
            'bookings': bookings,
        })
        
    return render(request, 'manager/boarding_overview.html', {'flight_boarding_data': flight_boarding_data})


@login_required
@operations_manager_required
def manager_delays(request):
    """
    Delay Management & Chart.js Analytics Hub.
    """
    delay_records = DelayRecord.objects.select_related('flight', 'recorded_by').all().order_by('-recorded_at')
    
    # Delay reasons breakdown for Chart.js
    reasons_counts = DelayRecord.objects.values('reason').annotate(count=Count('id'), avg_delay=Avg('delay_minutes')).order_by('-count')
    
    # Airlines delay breakdown
    airline_delays = Flight.objects.filter(delay_minutes__gt=0).values('airline__name').annotate(
        total_delayed=Count('id'),
        avg_delay=Avg('delay_minutes')
    ).order_by('-total_delayed')
    
    context = {
        'delay_records': delay_records,
        'reasons_counts': list(reasons_counts),
        'airline_delays': list(airline_delays),
        'total_delays_logged': delay_records.count(),
        'avg_delay_duration': delay_records.aggregate(Avg('delay_minutes'))['delay_minutes__avg'] or 0.0
    }
    return render(request, 'manager/delay_analytics.html', context)


@login_required
@operations_manager_required
def manager_ai_insights(request):
    """
    AI & Machine Learning Insights Explorer:
    - Model explainability & feature importances
    - Live risk predictions & mitigation suggestions
    - Interactive "What-If" simulator
    """
    predictions = AIFlightPrediction.objects.select_related(
        'flight', 'flight__airline', 'flight__source_airport', 'flight__destination_airport', 'flight__aircraft', 'flight__gate'
    ).all().order_by('-ground_risk_score')
    
    context = {
        'predictions': predictions,
        'airlines': Airline.objects.all(),
        'airports': Airport.objects.all(),
    }
    return render(request, 'manager/ai_insights.html', context)


@login_required
@operations_manager_required
def manager_issues(request):
    """
    Operational Issues incident desk.
    """
    issues = OperationalIssue.objects.select_related('flight', 'reported_by').all().order_by('-created_at')
    return render(request, 'manager/issues_list.html', {'issues': issues})


@login_required
@operations_manager_required
def manager_resolve_issue(request, pk):
    issue = get_object_or_404(OperationalIssue, pk=pk)
    if request.method == 'POST':
        issue.status = request.POST.get('status', IssueStatus.RESOLVED)
        issue.resolution_notes = request.POST.get('resolution_notes', '')
        if issue.status == IssueStatus.RESOLVED:
            issue.resolved_at = timezone.now()
        issue.save()
        messages.success(request, f"✓ Issue #{issue.id} marked as {issue.get_status_display()}.")
    return redirect('manager_issues')


@login_required
@operations_manager_required
def manager_reports(request):
    """
    Comprehensive Analytics & PDF / Printable Reports Hub:
    - Daily flight report
    - Passenger booking & seat occupancy report
    - Gate utilization report
    - Ground staff assignment report
    - Baggage report
    - Turnaround performance report
    - AI prediction accuracy report
    """
    flights = Flight.objects.select_related('airline', 'aircraft', 'source_airport', 'destination_airport', 'gate').all()
    bookings = Booking.objects.select_related('flight', 'passenger').all()
    gates = Gate.objects.all()
    staff = GroundStaffProfile.objects.select_related('user').all()
    baggage = Baggage.objects.all()
    
    context = {
        'flights': flights,
        'bookings': bookings,
        'gates': gates,
        'staff': staff,
        'baggage': baggage,
        'total_revenue': bookings.filter(status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]).aggregate(Sum('ticket_price'))['ticket_price__sum'] or 0.0,
        'now': timezone.now()
    }
    return render(request, 'manager/reports.html', context)


def api_sync_flight_status(request):
    """
    Public/AJAX endpoint to trigger or query automatic flight status synchronization.
    Compares scheduled departure against current datetime and returns status counts.
    """
    from operations.status_updater import auto_update_all_flight_statuses
    result = auto_update_all_flight_statuses(notify=True)
    return JsonResponse({
        'status': 'success',
        'total_scanned': result['total_scanned'],
        'updated_count': result['updated_count'],
        'updated_flights': result['updated_flights'],
        'server_time': result['timestamp'],
    })

