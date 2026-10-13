from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Airport, Airline, Aircraft, Gate, Flight, Seat, Booking,
    BoardingRecord, Baggage, BaggageScan, StaffAssignment,
    GroundOperation, OperationalIssue, DelayRecord, GateAllocation,
    AIFlightPrediction
)

@admin.register(Airport)
class AirportAdmin(admin.ModelAdmin):
    list_display = ('iata_code', 'name', 'city', 'country', 'terminals_count')
    search_fields = ('iata_code', 'name', 'city')

@admin.register(Airline)
class AirlineAdmin(admin.ModelAdmin):
    list_display = ('iata_code', 'name', 'country', 'active')
    search_fields = ('iata_code', 'name')

@admin.register(Aircraft)
class AircraftAdmin(admin.ModelAdmin):
    list_display = ('registration_number', 'model', 'aircraft_type', 'airline', 'seating_capacity', 'status')
    list_filter = ('status', 'aircraft_type', 'airline')
    search_fields = ('registration_number', 'model')

@admin.register(Gate)
class GateAdmin(admin.ModelAdmin):
    list_display = ('gate_number', 'terminal', 'gate_type', 'compatibility', 'status')
    list_filter = ('terminal', 'gate_type', 'compatibility', 'status')
    search_fields = ('gate_number', 'terminal')

@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display = ('flight_number', 'airline', 'source_airport', 'destination_airport', 'formatted_departure', 'status_badge', 'gate_display', 'delay_minutes', 'booked_seats_count')
    list_filter = ('status', 'airline', 'flight_type')
    search_fields = ('flight_number', 'source_airport__iata_code', 'destination_airport__iata_code')

    @admin.display(description="Scheduled Departure")
    def formatted_departure(self, obj):
        if obj.scheduled_departure:
            return obj.scheduled_departure.strftime("%d %b %Y, %I:%M %p")
        return "-"

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            'SCHEDULED': '#0284c7',
            'CONFIRMED': '#0d9488',
            'BOARDING': '#7e22ce',
            'READY_FOR_DEPARTURE': '#15803d',
            'DEPARTED': '#475569',
            'DELAYED': '#b45309',
            'CANCELLED': '#be123c',
        }
        color = colors.get(obj.status, '#64748b')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )

    @admin.display(description="Gate")
    def gate_display(self, obj):
        if obj.gate:
            return f"Gate {obj.gate.gate_number} ({obj.gate.terminal})"
        return "Unassigned"

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('booking_reference', 'passenger_name', 'flight_info', 'gate_info', 'seat_number', 'booking_status_badge', 'boarding_status_telemetry', 'baggage_info', 'formatted_booked_at')
    list_filter = ('status', 'booking_channel', 'flight__airline')
    search_fields = ('booking_reference', 'passenger_name', 'passenger_email', 'flight__flight_number', 'seat_number')

    @admin.display(description="Flight & Route")
    def flight_info(self, obj):
        return f"{obj.flight.flight_number} ({obj.flight.source_airport.iata_code} → {obj.flight.destination_airport.iata_code})"

    @admin.display(description="Gate")
    def gate_info(self, obj):
        return obj.flight.gate.gate_number if obj.flight.gate else "TBD"

    @admin.display(description="Booking Status")
    def booking_status_badge(self, obj):
        color = '#15803d' if obj.status in ['CONFIRMED', 'BOARDED'] else '#b91c1c' if obj.status == 'CANCELLED' else '#0284c7'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )

    @admin.display(description="Boarding Telemetry")
    def boarding_status_telemetry(self, obj):
        br = getattr(obj, 'boarding_record', None)
        if br and br.boarding_status == 'BOARDED' or obj.status == 'BOARDED':
            return format_html('<span style="background-color: #dcfce7; color: #15803d; padding: 2px 6px; border-radius: 4px; font-weight: bold;">🟢 {}</span>', 'BOARDED')
        elif obj.status == 'CANCELLED':
            return format_html('<span style="color: #991b1b;">{}</span>', 'CANCELLED')
        elif obj.status == 'CHECKED_IN':
            return format_html('<span style="color: #0284c7; font-weight: bold;">🔵 {}</span>', 'CHECKED IN')
        return format_html('<span style="background-color: #fef3c7; color: #b45309; padding: 2px 6px; border-radius: 4px;">🟡 {}</span>', 'WAITING / AT GATE')

    @admin.display(description="Baggage")
    def baggage_info(self, obj):
        bag = obj.baggage_items.first()
        if bag:
            return f"{bag.tag_number} ({bag.weight_kg}kg - {bag.get_status_display()})"
        return "No Bag"

    @admin.display(description="Booked At")
    def formatted_booked_at(self, obj):
        if obj.booked_at:
            return obj.booked_at.strftime("%d %b %Y, %I:%M %p")
        return "-"

@admin.register(BoardingRecord)
class BoardingRecordAdmin(admin.ModelAdmin):
    list_display = ('booking_ref', 'passenger_display', 'flight_display', 'gate_display', 'seat_display', 'boarding_status_pill', 'sequence_number', 'formatted_boarding_time', 'scanned_by_staff')
    list_filter = ('boarding_status', 'flight__flight_number')
    search_fields = ('booking__booking_reference', 'flight__flight_number', 'booking__passenger_name')

    @admin.display(description="PNR")
    def booking_ref(self, obj):
        return obj.booking.booking_reference

    @admin.display(description="Passenger")
    def passenger_display(self, obj):
        return obj.booking.passenger_name

    @admin.display(description="Flight")
    def flight_display(self, obj):
        return obj.flight.flight_number

    @admin.display(description="Gate")
    def gate_display(self, obj):
        return obj.flight.gate.gate_number if obj.flight.gate else "TBD"

    @admin.display(description="Seat")
    def seat_display(self, obj):
        return obj.booking.seat_number

    @admin.display(description="Boarding Status")
    def boarding_status_pill(self, obj):
        if obj.boarding_status == 'BOARDED':
            return format_html('<span style="background-color: #dcfce7; color: #15803d; padding: 2px 6px; border-radius: 4px; font-weight: bold;">🟢 {}</span>', 'BOARDED')
        return format_html('<span style="background-color: #fef3c7; color: #b45309; padding: 2px 6px; border-radius: 4px;">🟡 {}</span>', 'WAITING')

    @admin.display(description="Boarding Time")
    def formatted_boarding_time(self, obj):
        if obj.boarding_time:
            return obj.boarding_time.strftime("%d %b %Y, %I:%M:%S %p")
        return "-"

@admin.register(Baggage)
class BaggageAdmin(admin.ModelAdmin):
    list_display = ('tag_number', 'passenger_name', 'flight_number', 'weight_kg', 'status', 'risk_level', 'special_handling', 'formatted_created_at')
    list_filter = ('status', 'risk_level', 'special_handling')
    search_fields = ('tag_number', 'booking__booking_reference', 'booking__passenger_name', 'flight__flight_number')

    @admin.display(description="Passenger")
    def passenger_name(self, obj):
        return obj.booking.passenger_name

    @admin.display(description="Flight")
    def flight_number(self, obj):
        return obj.flight.flight_number

    @admin.display(description="Created At")
    def formatted_created_at(self, obj):
        if obj.created_at:
            return obj.created_at.strftime("%d %b %Y, %I:%M %p")
        return "-"

@admin.register(BaggageScan)
class BaggageScanAdmin(admin.ModelAdmin):
    list_display = ('baggage', 'location', 'status_at_scan', 'scanned_by', 'formatted_timestamp')
    search_fields = ('baggage__tag_number', 'location')

    @admin.display(description="Scan Time")
    def formatted_timestamp(self, obj):
        if obj.timestamp:
            return obj.timestamp.strftime("%d %b %Y, %I:%M:%S %p")
        return "-"

@admin.register(StaffAssignment)
class StaffAssignmentAdmin(admin.ModelAdmin):
    list_display = ('staff', 'flight', 'gate_location', 'role_in_flight', 'status', 'formatted_assigned_at')
    list_filter = ('status', 'role_in_flight')
    search_fields = ('staff__username', 'staff__first_name', 'staff__last_name', 'flight__flight_number')

    @admin.display(description="Gate")
    def gate_location(self, obj):
        return f"Gate {obj.flight.gate.gate_number}" if obj.flight.gate else "TBD"

    @admin.display(description="Assigned At")
    def formatted_assigned_at(self, obj):
        if obj.assigned_at:
            return obj.assigned_at.strftime("%d %b %Y, %I:%M %p")
        return "-"

@admin.register(GroundOperation)
class GroundOperationAdmin(admin.ModelAdmin):
    list_display = ('flight', 'overall_status', 'aircraft_arrived', 'boarding_started', 'boarding_completed', 'ready_for_departure', 'cleaning_completed', 'fueling_completed')
    list_filter = ('overall_status',)

@admin.register(OperationalIssue)
class OperationalIssueAdmin(admin.ModelAdmin):
    list_display = ('title', 'flight', 'issue_type', 'priority', 'status', 'reported_by', 'formatted_created_at')
    list_filter = ('issue_type', 'priority', 'status')
    search_fields = ('title', 'flight__flight_number')

    @admin.display(description="Reported At")
    def formatted_created_at(self, obj):
        if obj.created_at:
            return obj.created_at.strftime("%d %b %Y, %I:%M %p")
        return "-"

@admin.register(DelayRecord)
class DelayRecordAdmin(admin.ModelAdmin):
    list_display = ('flight', 'delay_minutes', 'reason', 'recorded_by', 'formatted_recorded_at')
    list_filter = ('reason',)

    @admin.display(description="Recorded At")
    def formatted_recorded_at(self, obj):
        if obj.recorded_at:
            return obj.recorded_at.strftime("%d %b %Y, %I:%M %p")
        return "-"

@admin.register(GateAllocation)
class GateAllocationAdmin(admin.ModelAdmin):
    list_display = ('flight', 'gate', 'formatted_start_time', 'formatted_end_time', 'allocated_by', 'status')
    list_filter = ('status',)

    @admin.display(description="Start Time")
    def formatted_start_time(self, obj):
        return obj.start_time.strftime("%d %b %Y, %I:%M %p") if obj.start_time else "-"

    @admin.display(description="End Time")
    def formatted_end_time(self, obj):
        return obj.end_time.strftime("%d %b %Y, %I:%M %p") if obj.end_time else "-"

@admin.register(AIFlightPrediction)
class AIFlightPredictionAdmin(admin.ModelAdmin):
    list_display = ('flight', 'predicted_delay_minutes', 'delay_probability', 'predicted_turnaround_minutes', 'risk_level', 'ground_risk_score', 'formatted_last_calculated_at')
    list_filter = ('risk_level',)

    @admin.display(description="Last Calculated At")
    def formatted_last_calculated_at(self, obj):
        return obj.last_calculated_at.strftime("%d %b %Y, %I:%M %p") if obj.last_calculated_at else "-"
