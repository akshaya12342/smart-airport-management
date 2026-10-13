from django.urls import path
from . import views

urlpatterns = [
    # Public Home & Discovery
    path('', views.home_view, name='home'),
    path('flight/<int:flight_id>/details/', views.public_flight_details, name='public_flight_details'),

    # Passenger URLs
    path('passenger/dashboard/', views.passenger_dashboard, name='passenger_dashboard'),
    path('passenger/search/', views.flight_search, name='flight_search'),
    path('passenger/book/<int:flight_id>/', views.flight_book, name='flight_book'),
    path('passenger/confirm-booking/<int:flight_id>/', views.confirm_booking, name='confirm_booking'),
    path('passenger/ticket/<int:booking_id>/', views.booking_ticket, name='booking_ticket'),
    path('passenger/ticket/<int:booking_id>/cancel/', views.passenger_cancel_booking, name='passenger_cancel_booking'),
    path('passenger/flight-details/<int:booking_id>/', views.passenger_flight_details, name='passenger_flight_details'),

    # Ground Staff URLs
    path('staff/dashboard/', views.ground_staff_dashboard, name='ground_staff_dashboard'),
    path('staff/flights/', views.staff_flights, name='staff_flights'),
    path('staff/flight/<int:flight_id>/', views.assigned_flight_detail, name='assigned_flight_detail'),
    path('staff/flight/<int:flight_id>/seats/', views.staff_flight_seats, name='staff_flight_seats'),
    path('staff/booking/', views.staff_counter_booking, name='staff_counter_booking'),
    path('staff/ticket-check/', views.staff_ticket_verification, name='staff_ticket_verification'),
    path('staff/flight/<int:flight_id>/boarding/', views.staff_boarding_manager, name='staff_boarding_manager'),
    path('staff/flight/<int:flight_id>/boarding/<int:boarding_id>/mark/', views.staff_mark_boarded, name='staff_mark_boarded'),
    path('staff/boarding/<int:boarding_id>/advance/', views.staff_advance_passenger_level, name='staff_advance_passenger_level'),
    path('staff/flight/<int:flight_id>/baggage/', views.staff_baggage_manager, name='staff_baggage_manager'),
    path('staff/baggage/', views.staff_all_baggage, name='staff_all_baggage'),
    path('staff/baggage/<int:baggage_id>/update/', views.staff_update_baggage, name='staff_update_baggage'),
    path('staff/flight/<int:flight_id>/turnaround/', views.staff_turnaround_tracker, name='staff_turnaround_tracker'),
    path('staff/report-issue/', views.staff_report_issue, name='staff_report_issue'),

    # Operations Manager URLs
    path('manager/dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('manager/flights/', views.manager_flights, name='manager_flights'),
    path('manager/flights/add/', views.manager_add_flight, name='manager_add_flight'),
    path('manager/flights/<int:pk>/edit/', views.manager_edit_flight, name='manager_edit_flight'),
    path('manager/flights/<int:pk>/status/', views.manager_update_flight_status, name='manager_update_flight_status'),
    path('manager/aircraft/', views.manager_aircraft, name='manager_aircraft'),
    path('manager/aircraft/add/', views.manager_add_aircraft, name='manager_add_aircraft'),
    path('manager/gates/', views.manager_gates, name='manager_gates'),
    path('manager/gates/allocate/<int:flight_id>/', views.manager_allocate_gate, name='manager_allocate_gate'),
    path('manager/passengers/', views.manager_passengers, name='manager_passengers'),
    path('manager/counter-booking/', views.manager_counter_booking, name='manager_counter_booking'),
    path('manager/staff/', views.manager_staff, name='manager_staff'),
    path('manager/staff/<int:staff_id>/approve/', views.manager_approve_staff, name='manager_approve_staff'),
    path('manager/staff/assign/', views.manager_assign_staff, name='manager_assign_staff'),
    path('manager/baggage/', views.manager_baggage, name='manager_baggage'),
    path('manager/boarding/', views.manager_boarding, name='manager_boarding'),
    path('manager/delays/', views.manager_delays, name='manager_delays'),
    path('manager/ai-insights/', views.manager_ai_insights, name='manager_ai_insights'),
    path('manager/issues/', views.manager_issues, name='manager_issues'),
    path('manager/issues/<int:pk>/resolve/', views.manager_resolve_issue, name='manager_resolve_issue'),
    path('manager/reports/', views.manager_reports, name='manager_reports'),

    # Real-time Flight Status Sync API
    path('api/flights/sync-status/', views.api_sync_flight_status, name='api_sync_flight_status'),
]
