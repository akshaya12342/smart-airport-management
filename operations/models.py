import random
import string
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class Airport(models.Model):
    iata_code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=150)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    terminals_count = models.IntegerField(default=2)

    class Meta:
        ordering = ['iata_code']

    def __str__(self):
        return f"{self.iata_code} - {self.name} ({self.city})"


class Airline(models.Model):
    iata_code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    color_hex = models.CharField(max_length=10, default='#1e3a8a')
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.iata_code} - {self.name}"


class AircraftType(models.TextChoices):
    NARROW_BODY = 'NARROW_BODY', _('Narrow Body (Single Aisle: A320, B737)')
    WIDE_BODY = 'WIDE_BODY', _('Wide Body (Twin Aisle: B777, A350, B787)')
    REGIONAL = 'REGIONAL', _('Regional Jet (ATR-72, E190)')

class AircraftStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', _('Active / Operational')
    MAINTENANCE = 'MAINTENANCE', _('In Maintenance')
    GROUNDED = 'GROUNDED', _('Grounded')

class Aircraft(models.Model):
    registration_number = models.CharField(max_length=20, unique=True)
    model = models.CharField(max_length=100)
    aircraft_type = models.CharField(
        max_length=30,
        choices=AircraftType.choices,
        default=AircraftType.NARROW_BODY
    )
    seating_capacity = models.IntegerField(default=180)
    airline = models.ForeignKey(Airline, on_delete=models.CASCADE, related_name='fleet')
    status = models.CharField(
        max_length=20,
        choices=AircraftStatus.choices,
        default=AircraftStatus.ACTIVE
    )

    class Meta:
        ordering = ['registration_number']

    def __str__(self):
        return f"{self.registration_number} ({self.model}) - {self.airline.iata_code}"


class GateType(models.TextChoices):
    DOMESTIC = 'DOMESTIC', _('Domestic')
    INTERNATIONAL = 'INTERNATIONAL', _('International')
    FLEXIBLE = 'FLEXIBLE', _('Flexible / Swing Gate')

class GateCompatibility(models.TextChoices):
    ALL = 'ALL', _('All Aircraft Types')
    NARROW_BODY_ONLY = 'NARROW_BODY_ONLY', _('Narrow Body & Regional Only')
    WIDE_BODY_COMPATIBLE = 'WIDE_BODY_COMPATIBLE', _('Wide Body & Heavy Capable')

class GateStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', _('Available')
    OCCUPIED = 'OCCUPIED', _('Occupied')
    MAINTENANCE = 'MAINTENANCE', _('Maintenance')
    RESERVED = 'RESERVED', _('Reserved')

class Gate(models.Model):
    gate_number = models.CharField(max_length=10, unique=True)
    terminal = models.CharField(max_length=50, default='Terminal 1')
    gate_type = models.CharField(
        max_length=20,
        choices=GateType.choices,
        default=GateType.DOMESTIC
    )
    compatibility = models.CharField(
        max_length=30,
        choices=GateCompatibility.choices,
        default=GateCompatibility.ALL
    )
    status = models.CharField(
        max_length=20,
        choices=GateStatus.choices,
        default=GateStatus.AVAILABLE
    )

    class Meta:
        ordering = ['gate_number']

    def __str__(self):
        return f"{self.gate_number} ({self.terminal} - {self.get_gate_type_display()})"


class FlightStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', _('Scheduled')
    CONFIRMED = 'CONFIRMED', _('Confirmed')
    ARRIVED = 'ARRIVED', _('Arrived')
    BOARDING = 'BOARDING', _('Boarding Started')
    BOARDING_COMPLETED = 'BOARDING_COMPLETED', _('Boarding Completed')
    READY_FOR_DEPARTURE = 'READY_FOR_DEPARTURE', _('Ready for Departure')
    DEPARTED = 'DEPARTED', _('Departed')
    DELAYED = 'DELAYED', _('Delayed')
    CANCELLED = 'CANCELLED', _('Cancelled')

class FlightType(models.TextChoices):
    DOMESTIC = 'DOMESTIC', _('Domestic')
    INTERNATIONAL = 'INTERNATIONAL', _('International')

class DelayReason(models.TextChoices):
    WEATHER = 'WEATHER', _('Weather Conditions')
    AIRCRAFT_ISSUE = 'AIRCRAFT_ISSUE', _('Aircraft Technical Issue')
    LATE_ARRIVAL = 'LATE_ARRIVAL', _('Late Aircraft Arrival')
    BAGGAGE_HANDLING = 'BAGGAGE_HANDLING', _('Baggage Handling Delay')
    BOARDING_DELAY = 'BOARDING_DELAY', _('Boarding & Passenger Delay')
    GATE_CONFLICT = 'GATE_CONFLICT', _('Gate Conflict / Ramp Congestion')
    STAFF_SHORTAGE = 'STAFF_SHORTAGE', _('Ground Staff Shortage')
    TECHNICAL_ISSUE = 'TECHNICAL_ISSUE', _('Technical / ATC System Issue')
    OPERATIONAL = 'OPERATIONAL', _('Operational Issue')
    OTHER = 'OTHER', _('Other Operational Cause')

class Flight(models.Model):
    flight_number = models.CharField(max_length=20)
    airline = models.ForeignKey(Airline, on_delete=models.CASCADE, related_name='flights')
    aircraft = models.ForeignKey(Aircraft, on_delete=models.SET_NULL, null=True, blank=True, related_name='flights')
    source_airport = models.ForeignKey(Airport, on_delete=models.CASCADE, related_name='departing_flights')
    destination_airport = models.ForeignKey(Airport, on_delete=models.CASCADE, related_name='arriving_flights')
    flight_type = models.CharField(
        max_length=20,
        choices=FlightType.choices,
        default=FlightType.DOMESTIC
    )
    scheduled_departure = models.DateTimeField()
    scheduled_arrival = models.DateTimeField()
    estimated_departure = models.DateTimeField(null=True, blank=True)
    estimated_arrival = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=FlightStatus.choices,
        default=FlightStatus.SCHEDULED
    )
    gate = models.ForeignKey(Gate, on_delete=models.SET_NULL, null=True, blank=True, related_name='flights')
    delay_minutes = models.IntegerField(default=0)
    delay_reason = models.CharField(
        max_length=50,
        choices=DelayReason.choices,
        blank=True,
        null=True
    )
    cancellation_reason = models.TextField(blank=True, default='')
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=4500.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_departure']

    def __str__(self):
        return f"{self.flight_number}: {self.source_airport.iata_code} → {self.destination_airport.iata_code} ({self.scheduled_departure.strftime('%d %b %H:%M')})"

    @property
    def total_capacity(self):
        if self.aircraft:
            return self.aircraft.seating_capacity
        return 180

    @property
    def booked_seats_count(self):
        return self.bookings.filter(status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.BOARDED]).count()

    @property
    def available_seats_count(self):
        return max(0, self.total_capacity - self.booked_seats_count)

    @property
    def boarded_passengers_count(self):
        return self.boarding_records.filter(boarding_status=BoardingStatus.BOARDED).count()

    @property
    def pending_passengers_count(self):
        return max(0, self.booked_seats_count - self.boarded_passengers_count)

    @property
    def boarding_progress_percentage(self):
        total = self.booked_seats_count
        if total == 0:
            return 0.0
        return round((self.boarded_passengers_count / total) * 100, 1)

    @property
    def effective_departure(self):
        if self.estimated_departure:
            return self.estimated_departure
        if self.delay_minutes > 0:
            return self.scheduled_departure + timezone.timedelta(minutes=self.delay_minutes)
        return self.scheduled_departure

    @property
    def effective_arrival(self):
        if self.estimated_arrival:
            return self.estimated_arrival
        if self.delay_minutes > 0:
            return self.scheduled_arrival + timezone.timedelta(minutes=self.delay_minutes)
        return self.scheduled_arrival

    @property
    def is_delayed(self):
        return self.status == FlightStatus.DELAYED or self.delay_minutes > 0

    @property
    def is_cancelled(self):
        return self.status == FlightStatus.CANCELLED

    @property
    def is_departed(self):
        return self.status == FlightStatus.DEPARTED or self.actual_departure is not None or self.effective_departure <= timezone.now()

    @property
    def is_boarding_closed(self):
        if self.is_departed:
            return True
        if self.status in [FlightStatus.READY_FOR_DEPARTURE, FlightStatus.BOARDING_COMPLETED]:
            return True
        time_to_dep = (self.effective_departure - timezone.now()).total_seconds()
        return 0 < time_to_dep <= 2 * 3600

    @property
    def is_boarding(self):
        return self.status == FlightStatus.BOARDING

    @property
    def is_ready_for_departure(self):
        return self.status == FlightStatus.READY_FOR_DEPARTURE

    @property
    def is_bookable(self):
        if self.status in [FlightStatus.DEPARTED, FlightStatus.CANCELLED, FlightStatus.READY_FOR_DEPARTURE, FlightStatus.BOARDING_COMPLETED]:
            return False
        if self.effective_departure <= timezone.now():
            return False
        if (self.effective_departure - timezone.now()).total_seconds() <= 2 * 3600:
            return False
        return self.available_seats_count > 0

    @property
    def status_css_class(self):
        mapping = {
            FlightStatus.SCHEDULED: 'scheduled',
            FlightStatus.CONFIRMED: 'confirmed',
            FlightStatus.ARRIVED: 'arrived',
            FlightStatus.BOARDING: 'boarding',
            FlightStatus.BOARDING_COMPLETED: 'boarding-completed',
            FlightStatus.READY_FOR_DEPARTURE: 'ready',
            FlightStatus.DEPARTED: 'departed',
            FlightStatus.DELAYED: 'delayed',
            FlightStatus.CANCELLED: 'cancelled',
        }
        return mapping.get(self.status, 'scheduled')

    def auto_sync_status(self, now=None, save=True, notify=True):
        from operations.status_updater import update_single_flight_status
        return update_single_flight_status(self, now=now, notify=notify, save=save)


class SeatClass(models.TextChoices):
    ECONOMY = 'ECONOMY', _('Economy')
    PREMIUM_ECONOMY = 'PREMIUM_ECONOMY', _('Premium Economy')
    BUSINESS = 'BUSINESS', _('Business')
    FIRST = 'FIRST', _('First Class')

class Seat(models.Model):
    aircraft = models.ForeignKey(Aircraft, on_delete=models.CASCADE, related_name='seats')
    seat_number = models.CharField(max_length=10)
    row = models.IntegerField()
    column = models.CharField(max_length=2)
    seat_class = models.CharField(
        max_length=20,
        choices=SeatClass.choices,
        default=SeatClass.ECONOMY
    )
    is_window = models.BooleanField(default=False)
    is_aisle = models.BooleanField(default=False)
    is_emergency_exit = models.BooleanField(default=False)

    class Meta:
        unique_together = ('aircraft', 'seat_number')
        ordering = ['row', 'column']

    def __str__(self):
        return f"{self.seat_number} ({self.get_seat_class_display()}) - {self.aircraft.registration_number}"


class BookingStatus(models.TextChoices):
    CONFIRMED = 'CONFIRMED', _('Confirmed')
    CHECKED_IN = 'CHECKED_IN', _('Checked In')
    BOARDED = 'BOARDED', _('Boarded')
    CANCELLED = 'CANCELLED', _('Cancelled')
    COMPLETED = 'COMPLETED', _('Completed')

class BookingChannel(models.TextChoices):
    ONLINE_PASSENGER = 'ONLINE_PASSENGER', _('Online Passenger Portal')
    OPERATIONS_COUNTER = 'OPERATIONS_COUNTER', _('Airport Operations Counter')

class Booking(models.Model):
    booking_reference = models.CharField(max_length=12, unique=True, db_index=True)
    passenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    passenger_name = models.CharField(max_length=150)
    passenger_email = models.EmailField()
    passenger_phone = models.CharField(max_length=25)
    passenger_id_passport = models.CharField(max_length=50, blank=True, default='')
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name='bookings')
    seat = models.ForeignKey(Seat, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    seat_number = models.CharField(max_length=10)
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.CONFIRMED
    )
    booking_channel = models.CharField(
        max_length=30,
        choices=BookingChannel.choices,
        default=BookingChannel.ONLINE_PASSENGER
    )
    ticket_price = models.DecimalField(max_digits=10, decimal_places=2, default=4500.00)
    booked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-booked_at']

    def __str__(self):
        return f"{self.booking_reference} - {self.passenger_name} ({self.flight.flight_number})"

    @staticmethod
    def generate_reference():
        prefix = "ANV"
        digits = ''.join(random.choices(string.digits, k=5))
        ref = f"{prefix}{digits}"
        while Booking.objects.filter(booking_reference=ref).exists():
            digits = ''.join(random.choices(string.digits, k=5))
            ref = f"{prefix}{digits}"
        return ref


class BoardingStatus(models.TextChoices):
    NOT_STARTED = 'NOT_STARTED', _('Not Started')
    BOARDING = 'BOARDING', _('Boarding in Progress')
    BOARDED = 'BOARDED', _('Boarded')
    NO_SHOW = 'NO_SHOW', _('No Show')
    GATE_CLOSED = 'GATE_CLOSED', _('Gate Closed')

class BoardingRecord(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='boarding_record')
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name='boarding_records')
    passenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='boarding_records')
    boarding_status = models.CharField(
        max_length=20,
        choices=BoardingStatus.choices,
        default=BoardingStatus.NOT_STARTED
    )
    boarding_time = models.DateTimeField(null=True, blank=True)
    gate = models.ForeignKey(Gate, on_delete=models.SET_NULL, null=True, blank=True)
    scanned_by_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scanned_boardings'
    )
    sequence_number = models.IntegerField(default=1)

    class Meta:
        ordering = ['sequence_number', 'booking__seat_number']

    def __str__(self):
        return f"Boarding: {self.booking.passenger_name} - {self.flight.flight_number} [{self.boarding_status}]"


class BaggageStatus(models.TextChoices):
    CHECKED_IN = 'CHECKED_IN', _('Checked In')
    SECURITY_CHECKED = 'SECURITY_CHECKED', _('Security Checked')
    SORTING = 'SORTING', _('Sorting')
    AT_GATE = 'AT_GATE', _('At Gate')
    LOADING = 'LOADING', _('Loading')
    LOADED = 'LOADED', _('Loaded')
    UNLOADED = 'UNLOADED', _('Unloaded')
    DELIVERED = 'DELIVERED', _('Delivered')
    DELAYED = 'DELAYED', _('Delayed')
    MISSING = 'MISSING', _('Missing')

class BaggageRiskLevel(models.TextChoices):
    LOW = 'LOW', _('Low Risk')
    MEDIUM = 'MEDIUM', _('Medium Risk')
    HIGH = 'HIGH', _('High Risk (Alert)')

class Baggage(models.Model):
    tag_number = models.CharField(max_length=30, unique=True, db_index=True)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='baggage_items')
    passenger = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='baggage_items')
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name='baggage_items')
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, default=15.00)
    status = models.CharField(
        max_length=30,
        choices=BaggageStatus.choices,
        default=BaggageStatus.CHECKED_IN
    )
    special_handling = models.BooleanField(default=False, help_text=_("Fragile or Priority Baggage"))
    risk_score = models.FloatField(default=5.0) # 0 to 100
    risk_level = models.CharField(
        max_length=20,
        choices=BaggageRiskLevel.choices,
        default=BaggageRiskLevel.LOW
    )
    risk_reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tag_number} ({self.weight_kg}kg) - {self.get_status_display()}"

    @staticmethod
    def generate_tag(flight_number):
        clean_flight = flight_number.replace('-', '')
        random_code = ''.join(random.choices(string.digits, k=5))
        return f"BAG-{clean_flight}-{random_code}"


class BaggageScan(models.Model):
    baggage = models.ForeignKey(Baggage, on_delete=models.CASCADE, related_name='scans')
    location = models.CharField(max_length=100)
    status_at_scan = models.CharField(max_length=30)
    scanned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Scan: {self.baggage.tag_number} at {self.location} [{self.timestamp.strftime('%H:%M')}]"


class StaffAssignment(models.Model):
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='flight_assignments')
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name='staff_assignments')
    role_in_flight = models.CharField(max_length=100, default='Ground Operations Specialist')
    assigned_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='ACTIVE', choices=[('ACTIVE', 'Active'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')])
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-assigned_at']

    def __str__(self):
        return f"{self.staff.get_full_name() or self.staff.username} -> {self.flight.flight_number} ({self.role_in_flight})"


class TurnaroundOverallStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', _('Scheduled')
    IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
    COMPLETED = 'COMPLETED', _('Completed')
    DELAYED_RISK = 'DELAYED_RISK', _('Delayed / Critical Risk')

class GroundOperation(models.Model):
    flight = models.OneToOneField(Flight, on_delete=models.CASCADE, related_name='ground_operation')
    aircraft_arrived = models.DateTimeField(null=True, blank=True)
    cleaning_started = models.DateTimeField(null=True, blank=True)
    cleaning_completed = models.DateTimeField(null=True, blank=True)
    fueling_started = models.DateTimeField(null=True, blank=True)
    fueling_completed = models.DateTimeField(null=True, blank=True)
    catering_completed = models.DateTimeField(null=True, blank=True)
    baggage_unloading_started = models.DateTimeField(null=True, blank=True)
    baggage_unloading_completed = models.DateTimeField(null=True, blank=True)
    baggage_loading_started = models.DateTimeField(null=True, blank=True)
    baggage_loading_completed = models.DateTimeField(null=True, blank=True)
    cabin_prep_completed = models.DateTimeField(null=True, blank=True)
    boarding_started = models.DateTimeField(null=True, blank=True)
    boarding_completed = models.DateTimeField(null=True, blank=True)
    ready_for_departure = models.DateTimeField(null=True, blank=True)
    overall_status = models.CharField(
        max_length=30,
        choices=TurnaroundOverallStatus.choices,
        default=TurnaroundOverallStatus.SCHEDULED
    )
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Turnaround: {self.flight.flight_number} [{self.overall_status}]"

    def calculate_progress_percentage(self):
        stages = [
            self.aircraft_arrived,
            self.cleaning_completed or self.cleaning_started,
            self.fueling_completed or self.fueling_started,
            self.catering_completed,
            self.baggage_unloading_completed or self.baggage_unloading_started,
            self.baggage_loading_completed or self.baggage_loading_started,
            self.cabin_prep_completed,
            self.boarding_completed or self.boarding_started,
            self.ready_for_departure
        ]
        completed = sum(1 for s in stages if s is not None)
        return round((completed / len(stages)) * 100, 1)


class OperationalIssueType(models.TextChoices):
    BAGGAGE_ISSUE = 'BAGGAGE_ISSUE', _('Baggage Handling Issue')
    GATE_ISSUE = 'GATE_ISSUE', _('Gate Equipment / Jetbridge Issue')
    BOARDING_ISSUE = 'BOARDING_ISSUE', _('Boarding / Passenger Issue')
    STAFF_SHORTAGE = 'STAFF_SHORTAGE', _('Ground Staff Shortage')
    TURNAROUND_ISSUE = 'TURNAROUND_ISSUE', _('Turnaround Milestone Delay')
    EQUIPMENT_ISSUE = 'EQUIPMENT_ISSUE', _('Ramp Equipment Malfunction')
    OTHER = 'OTHER', _('Other Operational Problem')

class IssuePriority(models.TextChoices):
    LOW = 'LOW', _('Low')
    MEDIUM = 'MEDIUM', _('Medium')
    HIGH = 'HIGH', _('High')
    CRITICAL = 'CRITICAL', _('Critical')

class IssueStatus(models.TextChoices):
    OPEN = 'OPEN', _('Open')
    INVESTIGATING = 'INVESTIGATING', _('Investigating')
    RESOLVED = 'RESOLVED', _('Resolved')

class OperationalIssue(models.Model):
    flight = models.ForeignKey(Flight, on_delete=models.SET_NULL, null=True, blank=True, related_name='reported_issues')
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reported_issues')
    issue_type = models.CharField(
        max_length=30,
        choices=OperationalIssueType.choices,
        default=OperationalIssueType.OTHER
    )
    priority = models.CharField(
        max_length=20,
        choices=IssuePriority.choices,
        default=IssuePriority.MEDIUM
    )
    title = models.CharField(max_length=150)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=IssueStatus.choices,
        default=IssueStatus.OPEN
    )
    resolution_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title} ({self.get_status_display()})"


class DelayRecord(models.Model):
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name='delay_records')
    delay_minutes = models.IntegerField()
    reason = models.CharField(max_length=50, choices=DelayReason.choices)
    detailed_description = models.TextField(blank=True, default='')
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return f"{self.flight.flight_number} - {self.delay_minutes} min ({self.get_reason_display()})"


class GateAllocation(models.Model):
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name='gate_allocations')
    gate = models.ForeignKey(Gate, on_delete=models.CASCADE, related_name='gate_allocations')
    allocated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, default='ACTIVE', choices=[('ACTIVE', 'Active'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')])
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.flight.flight_number} @ {self.gate.gate_number}"


class AIRiskLevel(models.TextChoices):
    LOW = 'LOW', _('Low Risk')
    MEDIUM = 'MEDIUM', _('Moderate Risk')
    HIGH = 'HIGH', _('High Risk')
    CRITICAL = 'CRITICAL', _('Critical Risk')

class AIFlightPrediction(models.Model):
    flight = models.OneToOneField(Flight, on_delete=models.CASCADE, related_name='ai_prediction')
    predicted_delay_minutes = models.FloatField(default=0.0)
    delay_probability = models.FloatField(default=0.0) # 0.0 - 1.0
    risk_level = models.CharField(
        max_length=20,
        choices=AIRiskLevel.choices,
        default=AIRiskLevel.LOW
    )
    predicted_turnaround_minutes = models.FloatField(default=45.0)
    ground_risk_score = models.FloatField(default=10.0) # 0 - 100
    key_factors = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    last_calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-ground_risk_score']

    def __str__(self):
        return f"AI Prediction: {self.flight.flight_number} [Risk: {self.risk_level}, Delay: {self.predicted_delay_minutes:.0f}m]"
