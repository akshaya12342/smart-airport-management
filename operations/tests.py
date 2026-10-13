from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from core.models import User, UserRole, Notification
from operations.models import (
    Airport, Airline, Aircraft, Gate, Flight, Seat, Booking, BoardingRecord,
    Baggage, BaggageScan, StaffAssignment, GroundOperation, OperationalIssue,
    FlightStatus, BookingStatus, BoardingStatus, BaggageStatus, GateStatus
)
from ai_engine.prediction_service import (
    predict_flight_delay, predict_ground_risk, predict_baggage_risk,
    predict_turnaround_time, recommend_gates
)

class AirportGroundOpsTestSuite(TestCase):
    def setUp(self):
        self.client = Client()
        
        # 1. Create Users for all 3 roles (Exact 3 roles, No super admin)
        self.passenger_user = User.objects.create_user(
            username='passenger1', email='pax1@test.com', password='pass123',
            role=UserRole.PASSENGER, first_name='Rahul', last_name='Sharma'
        )
        self.new_passenger_user = User.objects.create_user(
            username='newpax', email='newpax@test.com', password='pass123',
            role=UserRole.PASSENGER, first_name='Ananya', last_name='Patel'
        )
        self.staff_user = User.objects.create_user(
            username='staff_test', email='staff@test.com', password='staff123',
            role=UserRole.GROUND_STAFF, first_name='Vikram', last_name='Singh'
        )
        self.other_staff_user = User.objects.create_user(
            username='other_staff', email='otherstaff@test.com', password='staff123',
            role=UserRole.GROUND_STAFF, first_name='Priya', last_name='Nair'
        )
        self.manager_user = User.objects.create_user(
            username='manager_test', email='mgr@test.com', password='manager123',
            role=UserRole.OPERATIONS_MANAGER, first_name='Arun', last_name='Kumar'
        )

        # 2. Airports & Airlines
        self.cok = Airport.objects.create(iata_code='COK', name='Cochin Intl', city='Kochi')
        self.del_apt = Airport.objects.create(iata_code='DEL', name='Delhi Intl', city='Delhi')
        self.ai = Airline.objects.create(iata_code='AI', name='Air India')

        # 3. Aircraft & Seats
        self.aircraft = Aircraft.objects.create(
            registration_number='VT-TEST', model='Airbus A320neo', seating_capacity=180, airline=self.ai
        )
        self.seat_18a = Seat.objects.create(
            aircraft=self.aircraft, seat_number='18A', row=18, column='A', is_window=True
        )
        self.seat_18b = Seat.objects.create(
            aircraft=self.aircraft, seat_number='18B', row=18, column='B'
        )

        # 4. Gates
        self.gate_g12 = Gate.objects.create(gate_number='G12', terminal='Terminal 1', status=GateStatus.AVAILABLE)
        self.gate_g08 = Gate.objects.create(gate_number='G08', terminal='Terminal 1', status=GateStatus.AVAILABLE)

        # 5. Flights
        now = timezone.now()
        self.flight_ai452 = Flight.objects.create(
            flight_number='AI-452', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now + timedelta(hours=3),
            scheduled_arrival=now + timedelta(hours=6),
            status=FlightStatus.SCHEDULED,
            gate=self.gate_g12,
            base_price=5400.00
        )
        GroundOperation.objects.create(flight=self.flight_ai452)

        # 6. Staff Assignment (staff_test assigned to flight_ai452)
        StaffAssignment.objects.create(
            staff=self.staff_user, flight=self.flight_ai452, role_in_flight='Ramp Coordinator'
        )

    # --- PUBLIC HOME PAGE TESTS ---
    def test_public_home_page_and_top_right_bar(self):
        """Visiting root URL '/' displays live flights without login, and includes Login/Register in top right bar"""
        # Ensure client is unauthenticated
        self.client.logout()
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Live Flight Information Display (FIDS)")
        self.assertContains(res, "AI-452")
        self.assertContains(res, "Air India")
        self.assertContains(res, "Sign In / Login")
        self.assertContains(res, "Register")

        # Airplane button in topbar returns back to home page
        self.assertContains(res, "airplane-home-btn")
        self.assertContains(res, "bi-airplane-fill")

        # Unauthenticated click to view flight details prompts login
        details_res = self.client.get(reverse('public_flight_details', kwargs={'flight_id': self.flight_ai452.id}))
        self.assertEqual(details_res.status_code, 302)
        self.assertIn('/login/', details_res.url)

    def test_airplane_home_button_and_airports_list(self):
        """Test that airplane button exists in topbar across passenger, staff, manager pages and airports list is rendered"""
        # 1. Passenger Dashboard has airplane home button
        self.client.login(username='passenger1', password='pass123')
        pax_res = self.client.get(reverse('passenger_dashboard'))
        self.assertEqual(pax_res.status_code, 200)
        self.assertContains(pax_res, "airplane-home-btn")
        self.assertContains(pax_res, "allAirportsDatalist")

        # 2. Staff Dashboard has airplane home button
        self.client.login(username='staff_test', password='staff123')
        staff_res = self.client.get(reverse('ground_staff_dashboard'))
        self.assertEqual(staff_res.status_code, 200)
        self.assertContains(staff_res, "airplane-home-btn")

        # 3. Manager Dashboard has airplane home button
        self.client.login(username='manager_test', password='manager123')
        mgr_res = self.client.get(reverse('manager_dashboard'))
        self.assertEqual(mgr_res.status_code, 200)
        self.assertContains(mgr_res, "airplane-home-btn")


    # --- PASSENGER TESTS ---
    def test_new_passenger_zero_bookings(self):
        """New passenger with no bookings sees empty state"""
        self.client.login(username='newpax', password='pass123')
        res = self.client.get(reverse('passenger_dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "NO ACTIVE BOOKINGS")
        self.assertContains(res, "Book a Flight Now")

    def test_passenger_booking_flow_and_flight_verification(self):
        """Passenger books flight, checks seat map, confirms booking, receives PNR"""
        self.client.login(username='passenger1', password='pass123')
        
        # View seat map
        res = self.client.get(reverse('flight_book', kwargs={'flight_id': self.flight_ai452.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "18A")

        # Confirm booking on Seat 18A
        post_data = {
            'seat_number': '18A',
            'passenger_name': 'Rahul Sharma',
            'passenger_email': 'pax1@test.com',
            'passenger_phone': '+91 98765 43210',
            'passenger_id_passport': 'Z9823412',
            'baggage_weight': 18.5,
        }
        res = self.client.post(reverse('confirm_booking', kwargs={'flight_id': self.flight_ai452.id}), post_data, follow=True)
        self.assertEqual(res.status_code, 200)

        # Check booking in DB
        booking = Booking.objects.filter(flight=self.flight_ai452, passenger=self.passenger_user).first()
        self.assertIsNotNone(booking)
        self.assertEqual(booking.seat_number, '18A')
        self.assertTrue(booking.booking_reference.startswith('ANV'))

        # Check BoardingRecord & Baggage created
        self.assertTrue(BoardingRecord.objects.filter(booking=booking).exists())
        self.assertTrue(Baggage.objects.filter(booking=booking).exists())

        # Test Real-time dynamic retrieval: Manager updates flight delay to 22m
        self.flight_ai452.status = FlightStatus.DELAYED
        self.flight_ai452.delay_minutes = 22
        self.flight_ai452.save()

        # Passenger views dashboard and automatically sees latest delay!
        dash_res = self.client.get(reverse('passenger_dashboard'))
        self.assertContains(dash_res, "DELAYED (+22m)")
        self.assertContains(dash_res, "Flight Found ✓")

    def test_passenger_ajax_payment_and_ticket_redirect(self):
        """Passenger completes seat selection, submits payment option via gateway, receives success JSON and ticket link"""
        self.client.login(username='passenger1', password='pass123')
        post_data = {
            'seat_number': '18A',
            'passenger_name': 'Akshaya M',
            'passenger_email': 'makshaya992@gmail.com',
            'passenger_phone': '+91 9876543210',
            'passenger_id_passport': 'IND882211',
            'baggage_weight': 15.0,
            'payment_method': 'UPI (Google Pay)',
            'transaction_id': 'TXN_20261008_9988'
        }
        res = self.client.post(
            reverse('confirm_booking', kwargs={'flight_id': self.flight_ai452.id}),
            post_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res.status_code, 200)
        json_data = res.json()
        self.assertEqual(json_data['status'], 'success')
        self.assertEqual(json_data['seat_number'], '18A')
        self.assertEqual(json_data['transaction_id'], 'TXN_20261008_9988')
        self.assertIn('/passenger/ticket/', json_data['redirect_url'])

    def test_double_booking_prevention(self):
        """Cannot book an already booked seat"""
        # Create existing booking on 18A
        Booking.objects.create(
            booking_reference='ANV11111', passenger=self.passenger_user,
            passenger_name='Rahul Sharma', passenger_email='pax1@test.com',
            passenger_phone='99999', flight=self.flight_ai452, seat=self.seat_18a,
            seat_number='18A', status=BookingStatus.CONFIRMED
        )

        # Second passenger tries to book 18A
        self.client.login(username='newpax', password='pass123')
        post_data = {
            'seat_number': '18A',
            'passenger_name': 'Ananya Patel',
            'passenger_email': 'newpax@test.com',
            'passenger_phone': '88888',
            'baggage_weight': 15.0,
        }
        res = self.client.post(reverse('confirm_booking', kwargs={'flight_id': self.flight_ai452.id}), post_data, follow=True)
        self.assertContains(res, "was just booked by another passenger")

    # --- GROUND STAFF TESTS ---
    def test_ground_staff_unrestricted_flight_access(self):
        """Ground staff can view and manage all flights in the airport without assignment restrictions"""
        # staff_test can access flight details
        self.client.login(username='staff_test', password='staff123')
        res = self.client.get(reverse('assigned_flight_detail', kwargs={'flight_id': self.flight_ai452.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "AI-452")

        # other_staff (even without specific assignment) can also access any flight details
        self.client.login(username='other_staff', password='staff123')
        res2 = self.client.get(reverse('assigned_flight_detail', kwargs={'flight_id': self.flight_ai452.id}))
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, "AI-452")

    def test_ground_staff_boarding_and_turnaround(self):
        """Staff marks passenger boarded and updates turnaround milestone"""
        booking = Booking.objects.create(
            booking_reference='ANV22222', passenger=self.passenger_user,
            passenger_name='Rahul Sharma', passenger_email='pax1@test.com',
            passenger_phone='99999', flight=self.flight_ai452, seat=self.seat_18a,
            seat_number='18A', status=BookingStatus.CONFIRMED
        )
        rec = BoardingRecord.objects.create(
            booking=booking, flight=self.flight_ai452, passenger=self.passenger_user,
            boarding_status=BoardingStatus.NOT_STARTED
        )

        self.client.login(username='staff_test', password='staff123')
        
        # Mark boarded
        res = self.client.post(
            reverse('staff_mark_boarded', kwargs={'flight_id': self.flight_ai452.id, 'boarding_id': rec.id}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res.status_code, 200)
        rec.refresh_from_db()
        self.assertEqual(rec.boarding_status, BoardingStatus.BOARDED)

        # Update turnaround milestone
        turn_res = self.client.post(
            reverse('staff_turnaround_tracker', kwargs={'flight_id': self.flight_ai452.id}),
            {'milestone': 'cleaning', 'action_type': 'complete'},
            follow=True
        )
        self.assertEqual(turn_res.status_code, 200)
        ground_op = GroundOperation.objects.get(flight=self.flight_ai452)
        self.assertIsNotNone(ground_op.cleaning_completed)

    # --- OPERATIONS MANAGER TESTS ---
    def test_manager_ai_gate_allocation_and_notifications(self):
        """Manager allocates gate with AI recommender and automatic notification sent"""
        self.client.login(username='manager_test', password='manager123')
        
        # Get AI recommendations
        res = self.client.get(reverse('manager_allocate_gate', kwargs={'flight_id': self.flight_ai452.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Gate G12")
        self.assertContains(res, "Score:")

        # Allocate Gate G12
        post_res = self.client.post(
            reverse('manager_allocate_gate', kwargs={'flight_id': self.flight_ai452.id}),
            {'gate_id': self.gate_g12.id},
            follow=True
        )
        self.assertEqual(post_res.status_code, 200)
        self.flight_ai452.refresh_from_db()
        self.assertEqual(self.flight_ai452.gate, self.gate_g12)

    def test_manager_counter_booking(self):
        """Manager simulates counter booking for walk-in passenger"""
        self.client.login(username='manager_test', password='manager123')
        post_data = {
            'flight_id': self.flight_ai452.id,
            'passenger_name': 'Walk-in Traveler',
            'passenger_email': 'walkin@example.com',
            'passenger_phone': '+91 91111 22222',
            'passenger_id_passport': 'P1234567',
            'seat_number': '18B'
        }
        res = self.client.post(reverse('manager_counter_booking'), post_data, follow=True)
        self.assertEqual(res.status_code, 200)
        
        b = Booking.objects.filter(passenger_email='walkin@example.com').first()
        self.assertIsNotNone(b)
        self.assertEqual(b.seat_number, '18B')
        self.assertEqual(b.booking_channel, 'OPERATIONS_COUNTER')

    def test_manager_dashboard_and_views(self):
        """Tests that manager dashboard, flights list, staff, baggage, boarding, delay analytics, and AI views render HTTP 200 without error"""
        self.client.login(username='manager_test', password='manager123')
        
        # Test Manager Dashboard
        res = self.client.get(reverse('manager_dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Airport Operations Control Center (AOCC)")
        self.assertContains(res, "TOTAL FLIGHTS")
        
        # Test Flight List
        res_flights = self.client.get(reverse('manager_flights'))
        self.assertEqual(res_flights.status_code, 200)

        # Test Flight Status Modal GET & POST
        res_status_get = self.client.get(reverse('manager_update_flight_status', kwargs={'pk': self.flight_ai452.pk}))
        self.assertEqual(res_status_get.status_code, 200)
        self.assertContains(res_status_get, "Flight Operational Status")

        # POST update delay to 25 min
        post_status = self.client.post(
            reverse('manager_update_flight_status', kwargs={'pk': self.flight_ai452.pk}),
            {
                'status': 'DELAYED',
                'delay_minutes': 25,
                'delay_reason': 'WEATHER',
                'gate': self.gate_g12.id,
            },
            follow=True
        )
        self.assertEqual(post_status.status_code, 200)
        self.flight_ai452.refresh_from_db()
        self.assertEqual(self.flight_ai452.status, 'DELAYED')
        self.assertEqual(self.flight_ai452.delay_minutes, 25)
        
        # Test Gate Management
        res_gates = self.client.get(reverse('manager_gates'))
        self.assertEqual(res_gates.status_code, 200)
        
        # Test Staff Roster
        res_staff = self.client.get(reverse('manager_staff'))
        self.assertEqual(res_staff.status_code, 200)
        
        # Test Baggage Hub
        res_baggage = self.client.get(reverse('manager_baggage'))
        self.assertEqual(res_baggage.status_code, 200)
        
        # Test Boarding Monitor
        res_boarding = self.client.get(reverse('manager_boarding'))
        self.assertEqual(res_boarding.status_code, 200)
        
        # Test Delay Analytics
        res_delays = self.client.get(reverse('manager_delays'))
        self.assertEqual(res_delays.status_code, 200)
        
        # Test AI Insights
        res_ai = self.client.get(reverse('manager_ai_insights'))
        self.assertEqual(res_ai.status_code, 200)
        
        # Test Operational Issues Desk
        res_issues = self.client.get(reverse('manager_issues'))
        self.assertEqual(res_issues.status_code, 200)
        
        # Test Reports Hub
        res_reports = self.client.get(reverse('manager_reports'))
        self.assertEqual(res_reports.status_code, 200)

    def test_ground_staff_registration_and_manager_approval(self):
        """Ground staff registers -> account pending -> blocked from login -> Manager approves -> staff can login"""
        # 1. Staff registers
        reg_data = {
            'role': 'GROUND_STAFF',
            'username': 'newstaff_app',
            'email': 'newstaff@airport.com',
            'password': 'staffpass123',
            'confirm_password': 'staffpass123',
            'first_name': 'Karan',
            'last_name': 'Mehta',
            'phone': '+91 98888 77777',
            'department': 'RAMP_OPERATIONS',
            'shift': 'MORNING',
            'station': 'COK Terminal 1 Ramp',
        }
        reg_res = self.client.post(reverse('register'), reg_data, follow=True)
        self.assertEqual(reg_res.status_code, 200)
        self.assertContains(reg_res, "pending approval")

        staff_user = User.objects.get(username='newstaff_app')
        self.assertTrue(staff_user.is_ground_staff)
        self.assertFalse(staff_user.staff_profile.is_approved)

        # 2. Staff tries to login before approval -> BLOCKED
        self.client.logout()
        login_res = self.client.post(reverse('login'), {'username': 'newstaff_app', 'password': 'staffpass123'})
        self.assertContains(login_res, "pending approval")
        self.assertNotIn('_auth_user_id', self.client.session)

        # 3. Operations Manager views roster, sees staff pending, and approves
        self.client.login(username='manager_test', password='manager123')
        roster_res = self.client.get(reverse('manager_staff'))
        self.assertContains(roster_res, "newstaff_app")
        self.assertContains(roster_res, "Pending Approval")

        # Approve staff
        approve_res = self.client.post(
            reverse('manager_approve_staff', kwargs={'staff_id': staff_user.staff_profile.id}),
            {'action': 'approve'},
            follow=True
        )
        self.assertEqual(approve_res.status_code, 200)
        staff_user.staff_profile.refresh_from_db()
        self.assertTrue(staff_user.staff_profile.is_approved)

        # 4. Now staff CAN log in
        self.client.logout()
        staff_login_res = self.client.post(reverse('login'), {'username': 'newstaff_app', 'password': 'staffpass123'}, follow=True)
        self.assertEqual(staff_login_res.status_code, 200)
        self.assertEqual(int(self.client.session['_auth_user_id']), staff_user.id)

    def test_superuser_creates_operations_manager(self):
        """Createsuperuser automatically gets OPERATIONS_MANAGER role and profile"""
        admin_user = User.objects.create_superuser(
            username='opsadmin',
            email='opsadmin@airport.com',
            password='adminpassword123'
        )
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.is_operations_manager)
        self.assertTrue(hasattr(admin_user, 'manager_profile'))
        self.assertEqual(admin_user.manager_profile.desk_location, 'Airport Operations Control Center (AOCC)')

    # --- STAFF ADVANCED OPERATIONS TESTS ---
    def test_staff_flights_board_and_gate_telemetry(self):
        """Staff can view comprehensive flight board, gate allocations, and baggage weights"""
        self.client.login(username='staff_test', password='staff123')
        res = self.client.get(reverse('staff_flights'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "AI-452")
        self.assertContains(res, "G12")
        self.assertContains(res, "Terminal 1")
        self.assertContains(res, "Seat Allocation")

    def test_staff_flight_seats_2d_map(self):
        """Staff can inspect 2D seat map with booked passengers, seat numbers, and baggage weights"""
        booking = Booking.objects.create(
            booking_reference='ANV99887', passenger=self.passenger_user,
            passenger_name='Rahul Sharma', passenger_email='pax1@test.com',
            passenger_phone='+91 9876543210', flight=self.flight_ai452, seat=self.seat_18a,
            seat_number='18A', status=BookingStatus.CONFIRMED
        )
        Baggage.objects.create(
            tag_number='TAG99887', booking=booking, passenger=self.passenger_user,
            flight=self.flight_ai452, weight_kg=20.5, status=BaggageStatus.CHECKED_IN,
            special_handling=True
        )

        self.client.login(username='staff_test', password='staff123')
        res = self.client.get(reverse('staff_flight_seats', kwargs={'flight_id': self.flight_ai452.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "18A")
        self.assertContains(res, "Rahul Sharma")
        self.assertContains(res, "20.5")  # baggage weight

    def test_staff_counter_booking_with_baggage(self):
        """Staff can book a walk-in passenger, assign seat, and log baggage scale weight"""
        self.client.login(username='staff_test', password='staff123')
        
        # Load form
        get_res = self.client.get(f"{reverse('staff_counter_booking')}?flight_id={self.flight_ai452.id}")
        self.assertEqual(get_res.status_code, 200)
        
        # Post booking
        post_data = {
            'flight_id': self.flight_ai452.id,
            'passenger_name': 'Deepak Verma',
            'passenger_email': 'deepak@test.com',
            'passenger_phone': '+91 9988776655',
            'passenger_id_passport': 'IND992211',
            'seat_number': '18B',
            'baggage_weight': '16.8',
            'special_handling': 'on'
        }
        post_res = self.client.post(reverse('staff_counter_booking'), post_data, follow=True)
        self.assertEqual(post_res.status_code, 200)

        # Verify booking in DB
        booking = Booking.objects.filter(passenger_email='deepak@test.com', flight=self.flight_ai452).first()
        self.assertIsNotNone(booking)
        self.assertEqual(booking.seat_number, '18B')
        self.assertEqual(booking.booking_channel, 'OPERATIONS_COUNTER')

        # Verify baggage item and weight
        bag = Baggage.objects.filter(booking=booking).first()
        self.assertIsNotNone(bag)
        self.assertEqual(float(bag.weight_kg), 16.8)
        self.assertTrue(bag.special_handling)

        # Verify boarding record
        boarding = BoardingRecord.objects.filter(booking=booking).first()
        self.assertIsNotNone(boarding)
        self.assertEqual(boarding.boarding_status, BoardingStatus.NOT_STARTED)

    def test_staff_ticket_verification_and_advancement(self):
        """Staff can search ticket, verify ID & baggage weight, and advance level to BOARDED"""
        booking_rahul = Booking.objects.create(
            booking_reference='ANVRHL01', passenger=self.passenger_user,
            passenger_name='Rahul Sharma', passenger_email='pax1@test.com',
            passenger_phone='+91 9876543210', flight=self.flight_ai452, seat=self.seat_18a,
            seat_number='18A', status=BookingStatus.CONFIRMED
        )
        baggage_rahul = Baggage.objects.create(
            tag_number='TAGRHL01', booking=booking_rahul, passenger=self.passenger_user,
            flight=self.flight_ai452, weight_kg=20.5, status=BaggageStatus.CHECKED_IN,
            special_handling=True
        )
        BoardingRecord.objects.create(
            booking=booking_rahul, flight=self.flight_ai452, passenger=self.passenger_user,
            boarding_status=BoardingStatus.NOT_STARTED, gate=self.gate_g12
        )

        self.client.login(username='staff_test', password='staff123')

        # Search ticket
        search_res = self.client.get(f"{reverse('staff_ticket_verification')}?q={booking_rahul.booking_reference}")
        self.assertEqual(search_res.status_code, 200)
        self.assertContains(search_res, "Rahul Sharma")
        self.assertContains(search_res, "AI-452")
        self.assertContains(search_res, "20.5")

        # Update baggage weight at verification desk
        update_bag_res = self.client.post(
            reverse('staff_ticket_verification'),
            {
                'q': booking_rahul.booking_reference,
                'action': 'update_baggage_weight',
                'baggage_weight': '22.0'
            },
            follow=True
        )
        self.assertEqual(update_bag_res.status_code, 200)
        baggage_rahul.refresh_from_db()
        self.assertEqual(float(baggage_rahul.weight_kg), 22.0)

        # Advance passenger level to BOARDED
        advance_res = self.client.post(
            reverse('staff_ticket_verification'),
            {
                'q': booking_rahul.booking_reference,
                'action': 'advance_boarded'
            },
            follow=True
        )
        self.assertEqual(advance_res.status_code, 200)
        booking_rahul.refresh_from_db()
        self.assertEqual(booking_rahul.status, BookingStatus.BOARDED)
        
        boarding_rec = BoardingRecord.objects.get(booking=booking_rahul)
        self.assertEqual(boarding_rec.boarding_status, BoardingStatus.BOARDED)
        self.assertEqual(boarding_rec.scanned_by_staff, self.staff_user)

    def test_staff_all_baggage_operations_view(self):
        """Ground staff can inspect all passengers' baggage details, weights, and update baggage status"""
        booking = Booking.objects.create(
            booking_reference='ANVBAG01', passenger=self.passenger_user,
            passenger_name='Rahul Sharma', passenger_email='pax1@test.com',
            passenger_phone='+91 9876543210', flight=self.flight_ai452, seat=self.seat_18a,
            seat_number='18A', status=BookingStatus.CONFIRMED
        )
        bag = Baggage.objects.create(
            tag_number='TAGBAG01', booking=booking, passenger=self.passenger_user,
            flight=self.flight_ai452, weight_kg=19.5, status=BaggageStatus.CHECKED_IN,
            special_handling=True
        )

        self.client.login(username='staff_test', password='staff123')
        res = self.client.get(reverse('staff_all_baggage'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "TAGBAG01")
        self.assertContains(res, "Rahul Sharma")
        self.assertContains(res, "19.5")
        self.assertContains(res, "AI-452")

        # Update baggage status to LOADED
        post_res = self.client.post(
            reverse('staff_update_baggage', kwargs={'baggage_id': bag.id}),
            {'status': 'LOADED', 'location': 'Cargo Hold Gate G12'},
            follow=True
        )
        self.assertEqual(post_res.status_code, 200)
        bag.refresh_from_db()
        self.assertEqual(bag.status, BaggageStatus.LOADED)

    def test_passenger_cancel_booking_workflow_and_seat_restoration(self):
        """
        Passenger ticket cancellation workflow:
        1. Booking seat 18A reserves the seat and reduces flight availability.
        2. GET cancellation endpoint presents confirmation modal / details.
        3. POST confirms cancellation, updating status to CANCELLED.
        4. Seat 18A is immediately freed and available for another passenger to book.
        """
        # Step 1: Create confirmed booking for Rahul on Seat 18A
        booking_rahul = Booking.objects.create(
            booking_reference='ANVCAN01', passenger=self.passenger_user,
            passenger_name='Rahul Sharma', passenger_email='pax1@test.com',
            passenger_phone='+91 9876543210', flight=self.flight_ai452, seat=self.seat_18a,
            seat_number='18A', status=BookingStatus.CONFIRMED, ticket_price=5400.00
        )
        BoardingRecord.objects.create(
            booking=booking_rahul, flight=self.flight_ai452, passenger=self.passenger_user,
            boarding_status=BoardingStatus.NOT_STARTED, sequence_number=1
        )
        baggage = Baggage.objects.create(
            tag_number='TAGCAN01', booking=booking_rahul, passenger=self.passenger_user,
            flight=self.flight_ai452, weight_kg=15.0, status=BaggageStatus.CHECKED_IN
        )

        # Seat 18A is now taken
        self.assertEqual(self.flight_ai452.booked_seats_count, 1)
        self.assertEqual(self.flight_ai452.available_seats_count, 179)

        # Verify Ananya cannot book seat 18A while it is booked by Rahul
        self.client.login(username='newpax', password='pass123')
        clash_res = self.client.post(
            reverse('confirm_booking', kwargs={'flight_id': self.flight_ai452.id}),
            {
                'passenger_name': 'Ananya Patel',
                'passenger_email': 'newpax@test.com',
                'passenger_phone': '+91 9811223344',
                'seat_number': '18A',
                'baggage_weight': 15.0,
                'payment_method': 'UPI'
            },
            follow=True
        )
        # Should be rejected
        self.assertContains(clash_res, "was just booked by another passenger")

        # Step 2: Rahul views ticket page and cancel confirmation page
        self.client.login(username='passenger1', password='pass123')
        ticket_page = self.client.get(reverse('booking_ticket', kwargs={'booking_id': booking_rahul.id}))
        self.assertEqual(ticket_page.status_code, 200)
        self.assertContains(ticket_page, "Cancel Ticket")
        self.assertContains(ticket_page, "cancelTicketModal")

        cancel_get = self.client.get(reverse('passenger_cancel_booking', kwargs={'booking_id': booking_rahul.id}))
        self.assertEqual(cancel_get.status_code, 200)
        self.assertContains(cancel_get, "Confirm Cancellation")
        self.assertContains(cancel_get, "18A")
        self.assertContains(cancel_get, "5400.00")

        # Step 3: Rahul confirms ticket cancellation via POST
        cancel_post = self.client.post(
            reverse('passenger_cancel_booking', kwargs={'booking_id': booking_rahul.id}),
            follow=True
        )
        self.assertEqual(cancel_post.status_code, 200)
        self.assertContains(cancel_post, "cancelled successfully")
        self.assertContains(cancel_post, "Seat 18A has been released")

        # Verify database state
        booking_rahul.refresh_from_db()
        self.assertEqual(booking_rahul.status, BookingStatus.CANCELLED)

        # Step 4: Verify seat availability restored immediately
        self.assertEqual(self.flight_ai452.booked_seats_count, 0)
        self.assertEqual(self.flight_ai452.available_seats_count, 180)

        # Step 5: Now Ananya can successfully book the newly released seat 18A!
        self.client.login(username='newpax', password='pass123')
        success_res = self.client.post(
            reverse('confirm_booking', kwargs={'flight_id': self.flight_ai452.id}),
            {
                'passenger_name': 'Ananya Patel',
                'passenger_email': 'newpax@test.com',
                'passenger_phone': '+91 9811223344',
                'seat_number': '18A',
                'baggage_weight': 12.0,
                'payment_method': 'UPI'
            },
            follow=True
        )
        self.assertEqual(success_res.status_code, 200)
        self.assertTrue(Booking.objects.filter(flight=self.flight_ai452, seat_number='18A', status=BookingStatus.CONFIRMED, passenger=self.new_passenger_user).exists())
        self.assertEqual(self.flight_ai452.booked_seats_count, 1)

    def test_unauthorized_user_cannot_cancel_others_ticket(self):
        """A passenger cannot cancel another passenger's booking"""
        booking_rahul = Booking.objects.create(
            booking_reference='ANVSEC01', passenger=self.passenger_user,
            passenger_name='Rahul Sharma', passenger_email='pax1@test.com',
            passenger_phone='+91 9876543210', flight=self.flight_ai452, seat=self.seat_18a,
            seat_number='18A', status=BookingStatus.CONFIRMED
        )
        
        # Logged in as Ananya
        self.client.login(username='newpax', password='pass123')
        res = self.client.post(
            reverse('passenger_cancel_booking', kwargs={'booking_id': booking_rahul.id}),
            follow=True
        )
        # Should be forbidden / redirected with error
        booking_rahul.refresh_from_db()
        self.assertEqual(booking_rahul.status, BookingStatus.CONFIRMED)
        self.assertContains(res, "Unauthorized access")

    # --- AUTOMATIC FLIGHT STATUS UPDATER TESTS ---
    def test_automatic_flight_status_time_rules(self):
        """
        Verify automatic status calculation logic:
        - Passed/Crossed scheduled departure -> DEPARTED
        - <= 1 hour before departure -> READY_FOR_DEPARTURE
        - Between 1 and 4 hours before departure -> BOARDING
        - > 4 hours before departure -> SCHEDULED
        - Cancelled flight -> remains CANCELLED
        """
        from operations.status_updater import determine_flight_status, update_single_flight_status
        now = timezone.now()

        # 1. Past flight (crossed departure time)
        past_flight = Flight.objects.create(
            flight_number='AI-PAST1', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now - timedelta(minutes=15),
            scheduled_arrival=now + timedelta(hours=2),
            status=FlightStatus.SCHEDULED,
        )
        status, changed = determine_flight_status(past_flight, now=now)
        self.assertEqual(status, FlightStatus.DEPARTED)
        self.assertTrue(changed)

        # 2. Ready for departure (within 1 hour)
        ready_flight = Flight.objects.create(
            flight_number='AI-RDY1', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now + timedelta(minutes=35),
            scheduled_arrival=now + timedelta(hours=3),
            status=FlightStatus.SCHEDULED,
        )
        status, changed = determine_flight_status(ready_flight, now=now)
        self.assertEqual(status, FlightStatus.READY_FOR_DEPARTURE)
        self.assertTrue(changed)

        # 3. Boarding (between 1 and 4 hours)
        boarding_flight = Flight.objects.create(
            flight_number='AI-BRD1', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now + timedelta(hours=2, minutes=30),
            scheduled_arrival=now + timedelta(hours=5),
            status=FlightStatus.SCHEDULED,
        )
        status, changed = determine_flight_status(boarding_flight, now=now)
        self.assertEqual(status, FlightStatus.BOARDING)
        self.assertTrue(changed)

        # 4. Far future flight (> 4 hours)
        future_flight = Flight.objects.create(
            flight_number='AI-FUT1', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now + timedelta(hours=8),
            scheduled_arrival=now + timedelta(hours=11),
            status=FlightStatus.SCHEDULED,
        )
        status, changed = determine_flight_status(future_flight, now=now)
        self.assertEqual(status, FlightStatus.SCHEDULED)
        self.assertFalse(changed)

        # 5. Cancelled flight
        cancelled_flight = Flight.objects.create(
            flight_number='AI-CNL1', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now - timedelta(hours=1),
            scheduled_arrival=now + timedelta(hours=2),
            status=FlightStatus.CANCELLED,
            cancellation_reason='Weather alert'
        )
        status, changed = determine_flight_status(cancelled_flight, now=now)
        self.assertEqual(status, FlightStatus.CANCELLED)
        self.assertFalse(changed)

    def test_auto_update_all_flights_and_ground_operations_sync(self):
        """
        Verify that auto_update_all_flight_statuses updates statuses in DB,
        advances ground operations turnaround milestones, and dispatches notifications.
        """
        from operations.status_updater import auto_update_all_flight_statuses
        from operations.models import TurnaroundOverallStatus
        now = timezone.now()

        # Create flight 45 mins before departure (should become READY_FOR_DEPARTURE)
        flight_rdy = Flight.objects.create(
            flight_number='6E-SYNC1', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now + timedelta(minutes=45),
            scheduled_arrival=now + timedelta(hours=3),
            status=FlightStatus.SCHEDULED,
            gate=self.gate_g12
        )
        go_rdy = GroundOperation.objects.create(flight=flight_rdy)

        # Create booking and assign staff
        booking = Booking.objects.create(
            booking_reference='ANVSYNC1', passenger=self.passenger_user,
            passenger_name='Rahul Sharma', passenger_email='pax1@test.com',
            passenger_phone='+91 9876543210', flight=flight_rdy, seat=self.seat_18a,
            seat_number='18A', status=BookingStatus.CONFIRMED
        )
        StaffAssignment.objects.create(
            staff=self.staff_user, flight=flight_rdy, role_in_flight='Gate Lead', status='ACTIVE'
        )

        # Run auto update
        res = auto_update_all_flight_statuses(now=now, notify=True)
        self.assertGreaterEqual(res['updated_count'], 1)

        flight_rdy.refresh_from_db()
        self.assertEqual(flight_rdy.status, FlightStatus.READY_FOR_DEPARTURE)

        # Verify ground operations synced
        go_rdy.refresh_from_db()
        self.assertIsNotNone(go_rdy.ready_for_departure)
        self.assertEqual(go_rdy.overall_status, TurnaroundOverallStatus.IN_PROGRESS)

        # Verify notifications sent to passenger and staff
        pax_notifs = Notification.objects.filter(recipient=self.passenger_user, flight_number='6E-SYNC1')
        self.assertTrue(pax_notifs.exists())

        staff_notifs = Notification.objects.filter(recipient=self.staff_user, flight_number='6E-SYNC1')
        self.assertTrue(staff_notifs.exists())

    def test_management_command_and_api_endpoint(self):
        """Test management command and REST API endpoint for flight status auto-sync"""
        from django.core.management import call_command
        from io import StringIO

        # Run management command
        out = StringIO()
        call_command('auto_update_flight_statuses', stdout=out)
        self.assertIn("Status check complete", out.getvalue())

        # Test API endpoint
        api_res = self.client.get(reverse('api_sync_flight_status'))
        self.assertEqual(api_res.status_code, 200)
        data = api_res.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('total_scanned', data)
        self.assertIn('updated_count', data)

    def test_departed_flight_booking_blocked_and_ui_display(self):
        """
        Test that:
        1. When flight departure time is crossed / status is DEPARTED, passenger cannot book it
        2. Attempting GET flight_book redirects to flight_search with error message
        3. Attempting POST confirm_booking is rejected with error
        4. In flight_search, departed flight has disabled button, and 4h flight shows Boarding Started
        """
        now = timezone.now()
        
        # 1. Past flight (already departed)
        past_fl = Flight.objects.create(
            flight_number='AI-DEP99', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now - timedelta(minutes=30),
            scheduled_arrival=now + timedelta(hours=2),
            status=FlightStatus.SCHEDULED, # will auto sync to DEPARTED
            gate=self.gate_g12,
            base_price=4500.00
        )
        
        # 2. Boarding flight (within 4 hours)
        boarding_fl = Flight.objects.create(
            flight_number='AI-BRD99', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now + timedelta(hours=3),
            scheduled_arrival=now + timedelta(hours=6),
            status=FlightStatus.SCHEDULED, # will auto sync to BOARDING
            gate=self.gate_g08,
            base_price=4800.00
        )
        
        self.client.login(username='passenger1', password='pass123')
        
        # Verify flight search displays departed and boarding statuses
        search_res = self.client.get(reverse('flight_search'))
        self.assertEqual(search_res.status_code, 200)
        self.assertContains(search_res, "AI-DEP99")
        self.assertContains(search_res, "Departed (Booking Closed)")
        self.assertContains(search_res, "AI-BRD99")
        self.assertContains(search_res, "Boarding Started")
        
        # Try to access flight_book for departed flight -> blocked and redirected
        book_get = self.client.get(reverse('flight_book', kwargs={'flight_id': past_fl.id}), follow=True)
        self.assertEqual(book_get.status_code, 200)
        self.assertContains(book_get, "Booking Unavailable: Flight AI-DEP99 has already departed.")
        
        # Try to submit confirm_booking for departed flight -> blocked
        post_data = {
            'seat_number': '18A',
            'passenger_name': 'Rahul Sharma',
            'passenger_email': 'pax1@test.com',
            'passenger_phone': '+91 98765 43210',
            'passenger_id_passport': 'Z9823412',
            'baggage_weight': 15.0,
        }
        confirm_post = self.client.post(
            reverse('confirm_booking', kwargs={'flight_id': past_fl.id}),
            post_data,
            follow=True
        )
        self.assertContains(confirm_post, "Booking Unavailable: Flight AI-DEP99 has already departed.")
        self.assertFalse(Booking.objects.filter(flight=past_fl).exists())
        
        # Try AJAX confirm_booking for departed flight -> JSON error 400
        ajax_res = self.client.post(
            reverse('confirm_booking', kwargs={'flight_id': past_fl.id}),
            post_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
    def test_boarding_cutoff_and_booking_closure(self):
        """
        Test that:
        1. When flight is within 2 hours of departure, status is READY_FOR_DEPARTURE (Boarding Closed)
        2. Booking is closed (is_bookable=False, is_boarding_closed=True)
        3. Flight search displays disabled 'Boarding Closed (Booking Closed)'
        4. Booking attempt is rejected with clear message
        5. Flight within 2-4 hours is BOARDING ('Boarding Started') and bookable with 'Book (Boarding Started)'
        6. Flight > 4 hours is SCHEDULED ('On Time') and bookable with 'Book Now'
        """
        now = timezone.now()
        
        # 1. Flight departing in 1 hour (within 2 hours cutoff)
        cutoff_fl = Flight.objects.create(
            flight_number='AI-CUTOFF1', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now + timedelta(minutes=50),
            scheduled_arrival=now + timedelta(hours=3),
            status=FlightStatus.SCHEDULED,
            gate=self.gate_g12,
            base_price=4200.00
        )
        
        # 2. Flight departing in 3 hours (2-4 hours window)
        boarding_fl = Flight.objects.create(
            flight_number='AI-BRD3', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now + timedelta(hours=3),
            scheduled_arrival=now + timedelta(hours=6),
            status=FlightStatus.SCHEDULED,
            gate=self.gate_g08,
            base_price=4600.00
        )

        # 3. Flight departing in 6 hours (> 4 hours window)
        scheduled_fl = Flight.objects.create(
            flight_number='AI-SCHED6', airline=self.ai, aircraft=self.aircraft,
            source_airport=self.cok, destination_airport=self.del_apt,
            scheduled_departure=now + timedelta(hours=6),
            scheduled_arrival=now + timedelta(hours=9),
            status=FlightStatus.SCHEDULED,
            gate=self.gate_g12,
            base_price=4000.00
        )

        cutoff_fl.auto_sync_status()
        boarding_fl.auto_sync_status()
        scheduled_fl.auto_sync_status()

        self.assertEqual(cutoff_fl.status, FlightStatus.READY_FOR_DEPARTURE)
        self.assertTrue(cutoff_fl.is_boarding_closed)
        self.assertFalse(cutoff_fl.is_bookable)

        self.assertEqual(boarding_fl.status, FlightStatus.BOARDING)
        self.assertFalse(boarding_fl.is_boarding_closed)
        self.assertTrue(boarding_fl.is_bookable)

        self.assertEqual(scheduled_fl.status, FlightStatus.SCHEDULED)
        self.assertFalse(scheduled_fl.is_boarding_closed)
        self.assertTrue(scheduled_fl.is_bookable)

        self.client.login(username='passenger1', password='pass123')
        
        # Check flight search rendering
        search_res = self.client.get(reverse('flight_search'))
        self.assertEqual(search_res.status_code, 200)
        self.assertContains(search_res, "AI-CUTOFF1")
        self.assertContains(search_res, "Boarding Closed (Booking Closed)")
        self.assertContains(search_res, "AI-BRD3")
        self.assertContains(search_res, "Book (Boarding Started)")
        self.assertContains(search_res, "AI-SCHED6")
        self.assertContains(search_res, "Book Now")

        # Booking attempt on cutoff flight must be blocked
        book_res = self.client.get(reverse('flight_book', kwargs={'flight_id': cutoff_fl.id}), follow=True)
        self.assertEqual(book_res.status_code, 200)
        self.assertContains(book_res, "Booking Closed: Flight AI-CUTOFF1 is within 2 hours of departure")




