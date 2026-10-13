import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q

logger = logging.getLogger(__name__)

# Module-level variable to throttle automatic scanning during web requests
_LAST_AUTO_SYNC_TIMESTAMP = None


def determine_flight_status(flight, now=None):
    """
    Evaluates the automatic flight status based on scheduled/effective departure vs current time.
    
    Rules:
    1. CANCELLED flights are never altered.
    2. If current time >= effective departure (time has crossed / passed):
       -> FlightStatus.DEPARTED
    3. If time to departure <= 2 hours (0 < delta <= 120 mins):
       -> FlightStatus.READY_FOR_DEPARTURE
    4. If time to departure is between 2 hours and 4 hours (120 mins < delta <= 240 mins):
       -> FlightStatus.BOARDING ("Boarding Started")
    5. If time to departure > 4 hours:
       -> FlightStatus.SCHEDULED (or retains DELAYED if delay_minutes > 0, or CONFIRMED)
    """
    from operations.models import FlightStatus

    if flight.status == FlightStatus.CANCELLED:
        return flight.status, False

    if now is None:
        now = timezone.now()

    dep_time = flight.effective_departure or flight.scheduled_departure
    if not dep_time:
        return flight.status, False

    time_diff_seconds = (dep_time - now).total_seconds()
    time_diff_hours = time_diff_seconds / 3600.0

    old_status = flight.status

    if time_diff_seconds <= 0:
        target_status = FlightStatus.DEPARTED
    elif time_diff_hours <= 2.0:
        target_status = FlightStatus.READY_FOR_DEPARTURE
    elif time_diff_hours <= 4.0:
        target_status = FlightStatus.BOARDING
    else:
        # More than 4 hours ahead
        if flight.delay_minutes > 0 and old_status == FlightStatus.DELAYED:
            target_status = FlightStatus.DELAYED
        elif old_status in [
            FlightStatus.BOARDING,
            FlightStatus.BOARDING_COMPLETED,
            FlightStatus.READY_FOR_DEPARTURE,
            FlightStatus.DEPARTED
        ]:
            target_status = FlightStatus.SCHEDULED
        else:
            target_status = old_status if old_status in [FlightStatus.SCHEDULED, FlightStatus.CONFIRMED] else FlightStatus.SCHEDULED

    status_changed = (target_status != old_status)
    return target_status, status_changed


def update_single_flight_status(flight, now=None, notify=True, save=True):
    """
    Updates a single Flight instance's status, synchronized departure timestamp,
    ground operations, and dispatches notifications if status changed.
    """
    from operations.models import FlightStatus, TurnaroundOverallStatus, BookingStatus
    from core.models import User, Notification, NotificationCategory

    if now is None:
        now = timezone.now()

    if flight.status == FlightStatus.CANCELLED:
        return False

    old_status = flight.status
    target_status, status_changed = determine_flight_status(flight, now)

    if not status_changed:
        return False

    flight.status = target_status

    # Synchronize departure timestamp when departed
    if target_status == FlightStatus.DEPARTED and not flight.actual_departure:
        flight.actual_departure = flight.effective_departure or now

    if save:
        flight.save(update_fields=['status', 'actual_departure', 'updated_at'])

    # Sync GroundOperation turnaround milestones if present
    try:
        if hasattr(flight, 'ground_operation') and flight.ground_operation:
            go = flight.ground_operation
            go_changed = False

            if target_status == FlightStatus.BOARDING:
                if not go.boarding_started:
                    go.boarding_started = now
                    go_changed = True
                if go.overall_status == TurnaroundOverallStatus.SCHEDULED:
                    go.overall_status = TurnaroundOverallStatus.IN_PROGRESS
                    go_changed = True

            elif target_status == FlightStatus.READY_FOR_DEPARTURE:
                if not go.boarding_completed:
                    go.boarding_completed = now
                    go_changed = True
                if not go.ready_for_departure:
                    go.ready_for_departure = now
                    go_changed = True
                if go.overall_status != TurnaroundOverallStatus.COMPLETED:
                    go.overall_status = TurnaroundOverallStatus.IN_PROGRESS
                    go_changed = True

            elif target_status == FlightStatus.DEPARTED:
                dep_ts = flight.actual_departure or now
                if not go.ready_for_departure:
                    go.ready_for_departure = dep_ts
                    go_changed = True
                if not go.boarding_completed:
                    go.boarding_completed = dep_ts - timedelta(minutes=15)
                    go_changed = True
                if not go.boarding_started:
                    go.boarding_started = dep_ts - timedelta(minutes=45)
                    go_changed = True
                if go.overall_status != TurnaroundOverallStatus.COMPLETED:
                    go.overall_status = TurnaroundOverallStatus.COMPLETED
                    go_changed = True

            if go_changed:
                go.save()
    except Exception as e:
        logger.warning(f"Error updating ground operation for {flight.flight_number}: {e}")

    # Dispatch notifications on milestone status transitions
    if notify:
        try:
            gate_info = f"Gate {flight.gate.gate_number}" if flight.gate else "Departure Gate (TBD)"
            dest_info = f"{flight.destination_airport.city} ({flight.destination_airport.iata_code})"

            notif_title = None
            notif_msg = None
            notif_cat = NotificationCategory.BOARDING

            if target_status == FlightStatus.BOARDING:
                notif_title = f"Boarding Started: {flight.flight_number}"
                notif_msg = f"Boarding has started for flight {flight.flight_number} to {dest_info}. Please proceed to {gate_info}."
                notif_cat = NotificationCategory.BOARDING
            elif target_status == FlightStatus.READY_FOR_DEPARTURE:
                notif_title = f"Boarding Closed / Ready for Departure: {flight.flight_number}"
                notif_msg = f"Flight {flight.flight_number} to {dest_info} is at {gate_info}. Boarding is closed and flight is ready for departure."
                notif_cat = NotificationCategory.OPERATIONAL_ALERT
            elif target_status == FlightStatus.DEPARTED:
                dep_time_str = flight.actual_departure.strftime('%I:%M %p') if flight.actual_departure else "now"
                notif_title = f"Flight Departed: {flight.flight_number}"
                notif_msg = f"Flight {flight.flight_number} to {dest_info} has departed ({dep_time_str}). Thank you for flying with us!"
                notif_cat = NotificationCategory.GENERAL

            if notif_title and notif_msg:
                # 1. Notify booked passengers
                booked_users = User.objects.filter(
                    bookings__flight=flight,
                    bookings__status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]
                ).distinct()

                notifications_to_create = []
                for pax in booked_users:
                    notifications_to_create.append(
                        Notification(
                            recipient=pax,
                            title=notif_title,
                            message=notif_msg,
                            category=notif_cat,
                            flight_number=flight.flight_number
                        )
                    )

                # 2. Notify assigned staff
                assigned_staff = User.objects.filter(
                    flight_assignments__flight=flight,
                    flight_assignments__status='ACTIVE'
                ).distinct()

                for stf in assigned_staff:
                    notifications_to_create.append(
                        Notification(
                            recipient=stf,
                            title=f"Flight Milestone: {flight.flight_number}",
                            message=f"Flight {flight.flight_number} automatically transitioned from {old_status} to {target_status}.",
                            category=NotificationCategory.OPERATIONAL_ALERT,
                            flight_number=flight.flight_number
                        )
                    )

                if notifications_to_create:
                    Notification.objects.bulk_create(notifications_to_create)
        except Exception as e:
            logger.warning(f"Error dispatching notifications for {flight.flight_number}: {e}")

    # Recalculate AI Prediction if prediction service is loaded
    try:
        from ai_engine.prediction_service import update_flight_ai_prediction
        update_flight_ai_prediction(flight)
    except Exception:
        pass

    return True


def auto_update_all_flight_statuses(now=None, notify=True):
    """
    Scans all non-cancelled flights in the database and automatically updates their status
    based on current date and time compared against scheduled/effective departure.
    """
    from operations.models import Flight, FlightStatus

    if now is None:
        now = timezone.now()

    flights = Flight.objects.exclude(status=FlightStatus.CANCELLED).select_related(
        'airline', 'source_airport', 'destination_airport', 'gate'
    )

    updated_flights = []
    for flight in flights:
        changed = update_single_flight_status(flight, now=now, notify=notify, save=True)
        if changed:
            updated_flights.append({
                'id': flight.id,
                'flight_number': flight.flight_number,
                'new_status': flight.status,
                'effective_departure': str(flight.effective_departure),
            })

    return {
        'total_scanned': flights.count(),
        'updated_count': len(updated_flights),
        'updated_flights': updated_flights,
        'timestamp': now.isoformat(),
    }


def run_auto_status_sync_if_needed(interval_seconds=3):
    """
    Helper for middleware to avoid updating database multiple times in a single second.
    Runs at most once every `interval_seconds`.
    """
    global _LAST_AUTO_SYNC_TIMESTAMP
    now = timezone.now()
    if _LAST_AUTO_SYNC_TIMESTAMP is None or (now - _LAST_AUTO_SYNC_TIMESTAMP).total_seconds() >= interval_seconds:
        _LAST_AUTO_SYNC_TIMESTAMP = now
        return auto_update_all_flight_statuses(now=now, notify=True)
    return None
