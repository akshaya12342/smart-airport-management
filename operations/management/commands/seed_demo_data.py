import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from core.models import (
    User, UserRole, PassengerProfile, GroundStaffProfile, 
    OperationsManagerProfile, Notification, NotificationCategory,
    GroundStaffDepartment, StaffShift, StaffAvailability
)
from operations.models import (
    Airport, Airline, Aircraft, AircraftType, AircraftStatus,
    Gate, GateType, GateCompatibility, GateStatus,
    Flight, FlightStatus, FlightType, DelayReason,
    Seat, SeatClass, Booking, BookingStatus, BookingChannel,
    BoardingRecord, BoardingStatus, Baggage, BaggageStatus, BaggageScan,
    StaffAssignment, GroundOperation, TurnaroundOverallStatus,
    OperationalIssue, OperationalIssueType, IssuePriority, IssueStatus,
    DelayRecord, GateAllocation, AIFlightPrediction
)
from ai_engine.prediction_service import update_flight_ai_prediction
from ai_engine.model_loader import preload_all_models

class Command(BaseCommand):
    help = 'Seeds realistic airport ground operations demo data and trains ML models'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Initializing AI/ML Models..."))
        preload_all_models()

        self.stdout.write(self.style.NOTICE("Clearing old demo data..."))
        Notification.objects.all().delete()
        AIFlightPrediction.objects.all().delete()
        DelayRecord.objects.all().delete()
        OperationalIssue.objects.all().delete()
        GroundOperation.objects.all().delete()
        StaffAssignment.objects.all().delete()
        BaggageScan.objects.all().delete()
        Baggage.objects.all().delete()
        BoardingRecord.objects.all().delete()
        Booking.objects.all().delete()
        Seat.objects.all().delete()
        GateAllocation.objects.all().delete()
        Flight.objects.all().delete()
        Gate.objects.all().delete()
        Aircraft.objects.all().delete()
        Airline.objects.all().delete()
        Airport.objects.all().delete()
        PassengerProfile.objects.all().delete()
        GroundStaffProfile.objects.all().delete()
        OperationsManagerProfile.objects.all().delete()
        User.objects.all().delete()

        # 1. Create Core Users
        self.stdout.write(self.style.NOTICE("Creating Users & Profiles..."))
        
        # Superuser / Admin
        admin_user = User.objects.create_superuser(
            username='admin01',
            email='admin01@airport.com',
            password='admin',
            first_name='System',
            last_name='Administrator',
            role=UserRole.OPERATIONS_MANAGER,
            phone='+91 98450 00001'
        )
        OperationsManagerProfile.objects.get_or_create(
            user=admin_user,
            defaults={
                'employee_id': 'ADM-001',
                'desk_location': 'Airport Operations Control Center (AOCC)',
                'shift': StaffShift.MORNING
            }
        )

        # Operations Manager
        manager_user = User.objects.create_user(
            username='manager',
            email='manager@airport.com',
            password='manager123',
            first_name='Arun',
            last_name='Kumar',
            role=UserRole.OPERATIONS_MANAGER,
            phone='+91 98450 11223'
        )
        OperationsManagerProfile.objects.create(
            user=manager_user,
            employee_id='MGR-701',
            desk_location='AOCC Command Desk 1',
            shift=StaffShift.MORNING
        )

        # Ground Staff 1 (Ramp Operations) - Approved
        staff1_user = User.objects.create_user(
            username='staff1',
            email='staff1@airport.com',
            password='staff123',
            first_name='Vikram',
            last_name='Singh',
            role=UserRole.GROUND_STAFF,
            phone='+91 98450 44556'
        )
        staff1_profile = GroundStaffProfile.objects.create(
            user=staff1_user,
            employee_id='STF-301',
            department=GroundStaffDepartment.RAMP_OPERATIONS,
            shift=StaffShift.AFTERNOON,
            availability_status=StaffAvailability.ASSIGNED,
            station='COK Terminal 1 Ramp',
            is_approved=True,
            approved_at=timezone.now()
        )

        # Ground Staff 2 (Gate & Boarding) - Approved
        staff2_user = User.objects.create_user(
            username='staff2',
            email='staff2@airport.com',
            password='staff123',
            first_name='Priya',
            last_name='Nair',
            role=UserRole.GROUND_STAFF,
            phone='+91 98450 77889'
        )
        staff2_profile = GroundStaffProfile.objects.create(
            user=staff2_user,
            employee_id='STF-302',
            department=GroundStaffDepartment.GATE_OPERATIONS,
            shift=StaffShift.MORNING,
            availability_status=StaffAvailability.ASSIGNED,
            station='COK Gate G12 Desk',
            is_approved=True,
            approved_at=timezone.now()
        )

        # Ground Staff 3 (Baggage) - Approved
        staff3_user = User.objects.create_user(
            username='staff3',
            email='staff3@airport.com',
            password='staff123',
            first_name='Anand',
            last_name='Menon',
            role=UserRole.GROUND_STAFF,
            phone='+91 98450 99001'
        )
        GroundStaffProfile.objects.create(
            user=staff3_user,
            employee_id='STF-303',
            department=GroundStaffDepartment.BAGGAGE_HANDLING,
            shift=StaffShift.MORNING,
            availability_status=StaffAvailability.AVAILABLE,
            station='COK Baggage Sort Bay 2',
            is_approved=True,
            approved_at=timezone.now()
        )

        # Ground Staff 4 (Turnaround / Cleaning) - PENDING APPROVAL (Demo)
        staff4_user = User.objects.create_user(
            username='staff_pending',
            email='kiran.staff@airport.com',
            password='staff123',
            first_name='Kiran',
            last_name='Joseph',
            role=UserRole.GROUND_STAFF,
            phone='+91 98450 33221'
        )
        GroundStaffProfile.objects.create(
            user=staff4_user,
            employee_id='STF-304',
            department=GroundStaffDepartment.CABIN_CLEANING,
            shift=StaffShift.MORNING,
            availability_status=StaffAvailability.AVAILABLE,
            station='COK Terminal 1 Bay',
            is_approved=False
        )


        # Passenger 1 (With Active & Past Bookings)
        passenger_user = User.objects.create_user(
            username='passenger',
            email='passenger@airport.com',
            password='pass123',
            first_name='Rahul',
            last_name='Sharma',
            role=UserRole.PASSENGER,
            phone='+91 98765 43210'
        )
        PassengerProfile.objects.create(
            user=passenger_user,
            passport_number='Z9823412',
            nationality='Indian',
            emergency_contact='+91 98765 00000',
            special_assistance=False
        )

        # Passenger 2 (New user with NO bookings)
        new_passenger_user = User.objects.create_user(
            username='newpassenger',
            email='newpassenger@airport.com',
            password='pass123',
            first_name='Ananya',
            last_name='Patel',
            role=UserRole.PASSENGER,
            phone='+91 91234 56789'
        )
        PassengerProfile.objects.create(
            user=new_passenger_user,
            passport_number='A5519821',
            nationality='Indian',
            emergency_contact='+91 91234 00000',
            special_assistance=False
        )

        # Extra passengers for realistic flight manifests
        extra_passengers = []
        names = [
            ("Devika", "Pillai", "devika@example.com"),
            ("Rohan", "Gupta", "rohan@example.com"),
            ("Aarav", "Mehta", "aarav@example.com"),
            ("Sneha", "Reddy", "sneha@example.com"),
            ("Karthik", "Subramanian", "karthik@example.com"),
            ("Farhan", "Ali", "farhan@example.com"),
            ("Emily", "Watson", "emily@example.com"),
            ("David", "Smith", "david@example.com"),
        ]
        for f_name, l_name, email in names:
            u = User.objects.create_user(
                username=email.split('@')[0],
                email=email,
                password='pass123',
                first_name=f_name,
                last_name=l_name,
                role=UserRole.PASSENGER,
                phone='+91 90000 ' + str(random.randint(10000, 99999))
            )
            PassengerProfile.objects.create(user=u, nationality='Indian' if 'Watson' not in l_name else 'British')
            extra_passengers.append(u)

        # 2. Create Airports (52 Airports: Indian Hubs, Regional, and Major International Hubs)
        self.stdout.write(self.style.NOTICE("Creating 52 Airports & Airlines..."))
        airports_data = [
            # Kerala & South India
            ('COK', 'Cochin International Airport', 'Kochi', 'India', 3),
            ('TRV', 'Trivandrum International Airport', 'Thiruvananthapuram', 'India', 2),
            ('CCJ', 'Calicut International Airport', 'Kozhikode', 'India', 2),
            ('CNN', 'Kannur International Airport', 'Kannur', 'India', 1),
            ('BLR', 'Kempegowda International Airport', 'Bengaluru', 'India', 2),
            ('MAA', 'Chennai International Airport', 'Chennai', 'India', 2),
            ('HYD', 'Rajiv Gandhi International Airport', 'Hyderabad', 'India', 2),
            ('CJB', 'Coimbatore International Airport', 'Coimbatore', 'India', 1),
            ('IXM', 'Madurai Airport', 'Madurai', 'India', 1),
            ('TRZ', 'Tiruchirappalli International Airport', 'Tiruchirappalli', 'India', 2),
            ('IXE', 'Mangaluru International Airport', 'Mangalore', 'India', 1),
            ('HBX', 'Hubballi Airport', 'Hubli', 'India', 1),
            ('TIR', 'Tirupati Airport', 'Tirupati', 'India', 1),
            ('VTZ', 'Visakhapatnam International Airport', 'Visakhapatnam', 'India', 1),
            
            # North & Central India
            ('DEL', 'Indira Gandhi International Airport', 'Delhi', 'India', 3),
            ('BOM', 'Chhatrapati Shivaji Maharaj International Airport', 'Mumbai', 'India', 2),
            ('PNQ', 'Pune International Airport', 'Pune', 'India', 2),
            ('AMD', 'Sardar Vallabhbhai Patel International Airport', 'Ahmedabad', 'India', 2),
            ('GOI', 'Dabolim Airport', 'Goa', 'India', 1),
            ('GOX', 'Manohar International Airport', 'Mopa', 'India', 1),
            ('JAI', 'Jaipur International Airport', 'Jaipur', 'India', 2),
            ('LKO', 'Chaudhary Charan Singh International Airport', 'Lucknow', 'India', 3),
            ('VNS', 'Lal Bahadur Shastri International Airport', 'Varanasi', 'India', 1),
            ('IDR', 'Devi Ahilya Bai Holkar Airport', 'Indore', 'India', 1),
            ('BHO', 'Raja Bhoj Airport', 'Bhopal', 'India', 1),
            ('NAG', 'Dr. Babasaheb Ambedkar International Airport', 'Nagpur', 'India', 1),
            ('BDQ', 'Vadodara Airport', 'Vadodara', 'India', 1),
            ('UDR', 'Maharana Pratap Airport', 'Udaipur', 'India', 1),
            ('RPR', 'Swami Vivekananda Airport', 'Raipur', 'India', 1),
            ('IXC', 'Shaheed Bhagat Singh International Airport', 'Chandigarh', 'India', 1),
            ('ATQ', 'Sri Guru Ram Dass Jee International Airport', 'Amritsar', 'India', 1),
            ('DED', 'Dehradun Airport', 'Dehradun', 'India', 1),
            ('SXR', 'Sheikh ul-Alam International Airport', 'Srinagar', 'India', 1),
            ('IXJ', 'Jammu Airport', 'Jammu', 'India', 1),

            # East & North East India
            ('CCU', 'Netaji Subhash Chandra Bose International Airport', 'Kolkata', 'India', 2),
            ('BBI', 'Biju Patnaik International Airport', 'Bhubaneswar', 'India', 2),
            ('PAT', 'Jayprakash Narayan Airport', 'Patna', 'India', 1),
            ('IXR', 'Birsa Munda Airport', 'Ranchi', 'India', 1),
            ('GAY', 'Gaya Airport', 'Gaya', 'India', 1),
            ('GAU', 'Lokpriya Gopinath Bordoloi International Airport', 'Guwahati', 'India', 1),
            ('IXB', 'Bagdogra Airport', 'Siliguri', 'India', 1),
            ('IMF', 'Bir Tikendrajit International Airport', 'Imphal', 'India', 1),

            # Major International Hubs
            ('DXB', 'Dubai International Airport', 'Dubai', 'United Arab Emirates', 3),
            ('DOH', 'Hamad International Airport', 'Doha', 'Qatar', 2),
            ('SIN', 'Singapore Changi Airport', 'Singapore', 'Singapore', 4),
            ('LHR', 'Heathrow Airport', 'London', 'United Kingdom', 5),
            ('JFK', 'John F. Kennedy International Airport', 'New York', 'United States', 6),
            ('FRA', 'Frankfurt Airport', 'Frankfurt', 'Germany', 2),
            ('KUL', 'Kuala Lumpur International Airport', 'Kuala Lumpur', 'Malaysia', 2),
            ('BKK', 'Suvarnabhumi Airport', 'Bangkok', 'Thailand', 2),
            ('SYD', 'Sydney Kingsford Smith Airport', 'Sydney', 'Australia', 3),
            ('NRT', 'Narita International Airport', 'Tokyo', 'Japan', 3),
        ]
        
        airports_map = {}
        for code, name, city, country, term_cnt in airports_data:
            apt, _ = Airport.objects.get_or_create(
                iata_code=code,
                defaults={
                    'name': name,
                    'city': city,
                    'country': country,
                    'terminals_count': term_cnt
                }
            )
            airports_map[code] = apt

        cok = airports_map['COK']
        del_apt = airports_map['DEL']
        bom = airports_map['BOM']
        blr = airports_map['BLR']
        dxb = airports_map['DXB']
        lhr = airports_map['LHR']
        maa = airports_map['MAA']
        hyd = airports_map['HYD']
        ccu = airports_map['CCU']
        doh = airports_map['DOH']
        sin = airports_map['SIN']
        goi = airports_map['GOI']
        jai = airports_map['JAI']

        # 3. Create Airlines
        ai = Airline.objects.create(iata_code='AI', name='Air India', country='India', color_hex='#e63946')
        indigo = Airline.objects.create(iata_code='6E', name='IndiGo', country='India', color_hex='#003566')
        vistara = Airline.objects.create(iata_code='UK', name='Vistara', country='India', color_hex='#581c87')
        spice = Airline.objects.create(iata_code='SG', name='SpiceJet', country='India', color_hex='#d97706')
        emirates = Airline.objects.create(iata_code='EK', name='Emirates', country='UAE', color_hex='#b91c1c')


        # 4. Create Aircraft Fleet & Seats
        self.stdout.write(self.style.NOTICE("Creating Aircraft & Seat Configurations..."))
        aircraft_ai1 = Aircraft.objects.create(
            registration_number='VT-ANV',
            model='Airbus A320neo',
            aircraft_type=AircraftType.NARROW_BODY,
            seating_capacity=180,
            airline=ai,
            status=AircraftStatus.ACTIVE
        )
        aircraft_6e1 = Aircraft.objects.create(
            registration_number='VT-IFP',
            model='Airbus A321neo',
            aircraft_type=AircraftType.NARROW_BODY,
            seating_capacity=220,
            airline=indigo,
            status=AircraftStatus.ACTIVE
        )
        aircraft_uk1 = Aircraft.objects.create(
            registration_number='VT-VIS',
            model='Boeing 737-800',
            aircraft_type=AircraftType.NARROW_BODY,
            seating_capacity=168,
            airline=vistara,
            status=AircraftStatus.ACTIVE
        )
        aircraft_ek1 = Aircraft.objects.create(
            registration_number='A6-EEO',
            model='Boeing 777-300ER',
            aircraft_type=AircraftType.WIDE_BODY,
            seating_capacity=350,
            airline=emirates,
            status=AircraftStatus.ACTIVE
        )

        # Generate Seats for Aircraft VT-ANV (Air India A320neo)
        seats_to_create = []
        for row in range(1, 31):
            for col in ['A', 'B', 'C', 'D', 'E', 'F']:
                seat_num = f"{row}{col}"
                seat_cls = SeatClass.BUSINESS if row <= 3 else (SeatClass.PREMIUM_ECONOMY if row <= 6 else SeatClass.ECONOMY)
                is_win = col in ['A', 'F']
                is_ais = col in ['C', 'D']
                is_emg = row in [12, 13]
                seats_to_create.append(
                    Seat(
                        aircraft=aircraft_ai1,
                        seat_number=seat_num,
                        row=row,
                        column=col,
                        seat_class=seat_cls,
                        is_window=is_win,
                        is_aisle=is_ais,
                        is_emergency_exit=is_emg
                    )
                )
        # Seats for VT-IFP (IndiGo)
        for row in range(1, 37):
            for col in ['A', 'B', 'C', 'D', 'E', 'F']:
                seats_to_create.append(
                    Seat(
                        aircraft=aircraft_6e1,
                        seat_number=f"{row}{col}",
                        row=row,
                        column=col,
                        seat_class=SeatClass.ECONOMY,
                        is_window=(col in ['A', 'F']),
                        is_aisle=(col in ['C', 'D']),
                        is_emergency_exit=(row in [14, 15])
                    )
                )
        Seat.objects.bulk_create(seats_to_create)

        # 5. Create Gates
        self.stdout.write(self.style.NOTICE("Creating Airport Gates..."))
        gate_g12 = Gate.objects.create(gate_number='G12', terminal='Terminal 1', gate_type=GateType.DOMESTIC, compatibility=GateCompatibility.ALL, status=GateStatus.OCCUPIED)
        gate_g08 = Gate.objects.create(gate_number='G08', terminal='Terminal 1', gate_type=GateType.DOMESTIC, compatibility=GateCompatibility.ALL, status=GateStatus.OCCUPIED)
        gate_g15 = Gate.objects.create(gate_number='G15', terminal='Terminal 3', gate_type=GateType.INTERNATIONAL, compatibility=GateCompatibility.WIDE_BODY_COMPATIBLE, status=GateStatus.OCCUPIED)
        gate_g04 = Gate.objects.create(gate_number='G04', terminal='Terminal 1', gate_type=GateType.DOMESTIC, compatibility=GateCompatibility.NARROW_BODY_ONLY, status=GateStatus.AVAILABLE)
        gate_g06 = Gate.objects.create(gate_number='G06', terminal='Terminal 1', gate_type=GateType.DOMESTIC, compatibility=GateCompatibility.ALL, status=GateStatus.AVAILABLE)
        gate_g14 = Gate.objects.create(gate_number='G14', terminal='Terminal 2', gate_type=GateType.FLEXIBLE, compatibility=GateCompatibility.ALL, status=GateStatus.AVAILABLE)
        gate_g18 = Gate.objects.create(gate_number='G18', terminal='Terminal 3', gate_type=GateType.INTERNATIONAL, compatibility=GateCompatibility.WIDE_BODY_COMPATIBLE, status=GateStatus.AVAILABLE)
        gate_g20 = Gate.objects.create(gate_number='G20', terminal='Terminal 2', gate_type=GateType.DOMESTIC, compatibility=GateCompatibility.NARROW_BODY_ONLY, status=GateStatus.MAINTENANCE)

        # 6. Create Flights
        self.stdout.write(self.style.NOTICE("Creating Flights & Flight Schedules..."))
        now = timezone.now()
        
        # Flight 1: AI-452 (Kochi -> Delhi) - DELAYED by 22m, Gate G12
        flight_ai452 = Flight.objects.create(
            flight_number='AI-452',
            airline=ai,
            aircraft=aircraft_ai1,
            source_airport=cok,
            destination_airport=del_apt,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now + timedelta(hours=1, minutes=30),
            scheduled_arrival=now + timedelta(hours=4, minutes=45),
            estimated_departure=now + timedelta(hours=1, minutes=52),
            status=FlightStatus.DELAYED,
            gate=gate_g12,
            delay_minutes=22,
            delay_reason=DelayReason.LATE_ARRIVAL,
            base_price=5400.00
        )
        DelayRecord.objects.create(
            flight=flight_ai452,
            delay_minutes=22,
            reason=DelayReason.LATE_ARRIVAL,
            detailed_description='Inbound aircraft VT-ANV experienced 25m holding pattern due to congested airspace at Delhi prior to landing at Kochi.',
            recorded_by=manager_user
        )

        # Flight 2: 6E-721 (Kochi -> Mumbai) - READY_FOR_DEPARTURE (45 mins away), Gate G08
        flight_6e721 = Flight.objects.create(
            flight_number='6E-721',
            airline=indigo,
            aircraft=aircraft_6e1,
            source_airport=cok,
            destination_airport=bom,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now + timedelta(minutes=45),
            scheduled_arrival=now + timedelta(hours=2, minutes=45),
            status=FlightStatus.READY_FOR_DEPARTURE,
            gate=gate_g08,
            delay_minutes=0,
            base_price=4200.00
        )

        # Flight 3: EK-531 (Kochi -> Dubai) - SCHEDULED, Gate G15
        flight_ek531 = Flight.objects.create(
            flight_number='EK-531',
            airline=emirates,
            aircraft=aircraft_ek1,
            source_airport=cok,
            destination_airport=dxb,
            flight_type=FlightType.INTERNATIONAL,
            scheduled_departure=now + timedelta(hours=4),
            scheduled_arrival=now + timedelta(hours=8),
            status=FlightStatus.SCHEDULED,
            gate=gate_g15,
            delay_minutes=0,
            base_price=18500.00
        )

        # Flight 4: UK-884 (Kochi -> Bengaluru) - DEPARTED (Completed Past Flight)
        flight_uk884 = Flight.objects.create(
            flight_number='UK-884',
            airline=vistara,
            aircraft=aircraft_uk1,
            source_airport=cok,
            destination_airport=blr,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now - timedelta(days=3, hours=4),
            scheduled_arrival=now - timedelta(days=3, hours=3),
            actual_departure=now - timedelta(days=3, hours=4),
            actual_arrival=now - timedelta(days=3, hours=3),
            status=FlightStatus.DEPARTED,
            gate=gate_g04,
            base_price=3600.00
        )

        # Flight 5: SG-332 (Kochi -> Chennai) - CANCELLED
        flight_sg332 = Flight.objects.create(
            flight_number='SG-332',
            airline=spice,
            aircraft=None,
            source_airport=cok,
            destination_airport=maa,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now + timedelta(days=1, hours=2),
            scheduled_arrival=now + timedelta(days=1, hours=3, minutes=30),
            status=FlightStatus.CANCELLED,
            cancellation_reason='Operational Issue: Technical defect detected during pre-flight maintenance check.',
            base_price=3900.00
        )

        # Additional Future Available Flights for Booking Search
        flight_ai454 = Flight.objects.create(
            flight_number='AI-454',
            airline=ai,
            aircraft=aircraft_ai1,
            source_airport=cok,
            destination_airport=del_apt,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now + timedelta(days=2, hours=3),
            scheduled_arrival=now + timedelta(days=2, hours=6, minutes=15),
            status=FlightStatus.SCHEDULED,
            gate=gate_g14,
            base_price=5100.00
        )
        flight_6e882 = Flight.objects.create(
            flight_number='6E-882',
            airline=indigo,
            aircraft=aircraft_6e1,
            source_airport=cok,
            destination_airport=del_apt,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now + timedelta(days=2, hours=7),
            scheduled_arrival=now + timedelta(days=2, hours=10, minutes=20),
            status=FlightStatus.SCHEDULED,
            gate=gate_g06,
            base_price=4800.00
        )
        # 6E-542 to Bengaluru (BLR)
        Flight.objects.create(
            flight_number='6E-542',
            airline=indigo,
            aircraft=aircraft_6e1,
            source_airport=cok,
            destination_airport=blr,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now + timedelta(hours=3),
            scheduled_arrival=now + timedelta(hours=4, minutes=10),
            status=FlightStatus.SCHEDULED,
            gate=gate_g04,
            base_price=2900.00
        )
        # AI-512 to Hyderabad (HYD)
        Flight.objects.create(
            flight_number='AI-512',
            airline=ai,
            aircraft=aircraft_ai1,
            source_airport=cok,
            destination_airport=hyd,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now + timedelta(hours=5),
            scheduled_arrival=now + timedelta(hours=6, minutes=40),
            status=FlightStatus.SCHEDULED,
            gate=gate_g06,
            base_price=3800.00
        )
        # 6E-892 to Goa (GOI)
        Flight.objects.create(
            flight_number='6E-892',
            airline=indigo,
            aircraft=aircraft_6e1,
            source_airport=cok,
            destination_airport=goi,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now + timedelta(hours=6, minutes=30),
            scheduled_arrival=now + timedelta(hours=7, minutes=50),
            status=FlightStatus.SCHEDULED,
            gate=gate_g14,
            base_price=3400.00
        )
        # UK-920 to Kolkata (CCU)
        Flight.objects.create(
            flight_number='UK-920',
            airline=vistara,
            aircraft=aircraft_uk1,
            source_airport=cok,
            destination_airport=ccu,
            flight_type=FlightType.DOMESTIC,
            scheduled_departure=now + timedelta(hours=7),
            scheduled_arrival=now + timedelta(hours=10, minutes=15),
            status=FlightStatus.SCHEDULED,
            gate=gate_g08,
            base_price=5900.00
        )
        # EK-533 to Doha (DOH)
        Flight.objects.create(
            flight_number='QR-517',
            airline=emirates,
            aircraft=aircraft_ek1,
            source_airport=cok,
            destination_airport=doh,
            flight_type=FlightType.INTERNATIONAL,
            scheduled_departure=now + timedelta(hours=8),
            scheduled_arrival=now + timedelta(hours=12, minutes=30),
            status=FlightStatus.SCHEDULED,
            gate=gate_g18,
            base_price=17200.00
        )
        # AI-771 to London Heathrow (LHR)
        Flight.objects.create(
            flight_number='AI-771',
            airline=ai,
            aircraft=aircraft_ai1,
            source_airport=cok,
            destination_airport=lhr,
            flight_type=FlightType.INTERNATIONAL,
            scheduled_departure=now + timedelta(hours=10),
            scheduled_arrival=now + timedelta(hours=20),
            status=FlightStatus.SCHEDULED,
            gate=gate_g15,
            base_price=42000.00
        )
        # 6E-108 to Singapore (SIN)
        Flight.objects.create(
            flight_number='6E-108',
            airline=indigo,
            aircraft=aircraft_6e1,
            source_airport=cok,
            destination_airport=sin,
            flight_type=FlightType.INTERNATIONAL,
            scheduled_departure=now + timedelta(hours=11, minutes=30),
            scheduled_arrival=now + timedelta(hours=16, minutes=45),
            status=FlightStatus.SCHEDULED,
            gate=gate_g18,
            base_price=14500.00
        )


        # 7. Create Staff Assignments
        self.stdout.write(self.style.NOTICE("Assigning Ground Staff to Flights..."))
        StaffAssignment.objects.create(
            staff=staff1_user,
            flight=flight_ai452,
            role_in_flight='Ramp Operations Coordinator',
            status='ACTIVE',
            notes='Lead turnaround coordination and monitor baggage loading.'
        )
        StaffAssignment.objects.create(
            staff=staff1_user,
            flight=flight_6e721,
            role_in_flight='Turnaround Supervisor',
            status='ACTIVE'
        )
        StaffAssignment.objects.create(
            staff=staff2_user,
            flight=flight_ai452,
            role_in_flight='Gate Boarding Lead',
            status='ACTIVE'
        )
        StaffAssignment.objects.create(
            staff=staff2_user,
            flight=flight_6e721,
            role_in_flight='Gate Boarding Agent',
            status='ACTIVE'
        )
        StaffAssignment.objects.create(
            staff=staff3_user,
            flight=flight_ai452,
            role_in_flight='Baggage Transfer Specialist',
            status='ACTIVE'
        )

        # 8. Create Ground Operations & Turnaround Milestones
        self.stdout.write(self.style.NOTICE("Creating Ground Turnaround Trackers..."))
        GroundOperation.objects.create(
            flight=flight_ai452,
            aircraft_arrived=now - timedelta(minutes=40),
            cleaning_started=now - timedelta(minutes=30),
            cleaning_completed=now - timedelta(minutes=10),
            fueling_started=now - timedelta(minutes=25),
            fueling_completed=now - timedelta(minutes=5),
            catering_completed=now - timedelta(minutes=15),
            baggage_unloading_started=now - timedelta(minutes=35),
            baggage_unloading_completed=now - timedelta(minutes=15),
            baggage_loading_started=now - timedelta(minutes=10),
            baggage_loading_completed=now - timedelta(minutes=2),
            cabin_prep_completed=now - timedelta(minutes=5),
            boarding_started=None,
            boarding_completed=None,
            ready_for_departure=None,
            overall_status=TurnaroundOverallStatus.IN_PROGRESS,
            updated_by=staff1_user,
            notes='Aircraft turnaround in progress at Gate G12. Baggage loading complete, awaiting boarding clearance.'
        )

        GroundOperation.objects.create(
            flight=flight_6e721,
            aircraft_arrived=now - timedelta(minutes=50),
            cleaning_completed=now - timedelta(minutes=20),
            fueling_completed=now - timedelta(minutes=15),
            catering_completed=now - timedelta(minutes=20),
            baggage_unloading_completed=now - timedelta(minutes=25),
            baggage_loading_completed=now - timedelta(minutes=5),
            cabin_prep_completed=now - timedelta(minutes=15),
            boarding_started=now - timedelta(minutes=10),
            overall_status=TurnaroundOverallStatus.IN_PROGRESS,
            updated_by=staff1_user,
            notes='Boarding underway. 85% passengers processed.'
        )

        # 9. Create Bookings & Passenger Journeys
        self.stdout.write(self.style.NOTICE("Creating Bookings & Passenger Journeys..."))
        
        # Booking 1: Passenger Rahul on AI-452 (Seat 18A, ANV45821 - Prompt Match!)
        seat_18a = Seat.objects.get(aircraft=aircraft_ai1, seat_number='18A')
        booking1 = Booking.objects.create(
            booking_reference='ANV45821',
            passenger=passenger_user,
            passenger_name='Rahul Sharma',
            passenger_email='passenger@airport.com',
            passenger_phone='+91 98765 43210',
            passenger_id_passport='Z9823412',
            flight=flight_ai452,
            seat=seat_18a,
            seat_number='18A',
            status=BookingStatus.CONFIRMED,
            booking_channel=BookingChannel.ONLINE_PASSENGER,
            ticket_price=5400.00
        )
        BoardingRecord.objects.create(
            booking=booking1,
            flight=flight_ai452,
            passenger=passenger_user,
            boarding_status=BoardingStatus.NOT_STARTED,
            gate=gate_g12,
            sequence_number=18
        )
        bag1 = Baggage.objects.create(
            tag_number='BAG-AI452-9842',
            booking=booking1,
            passenger=passenger_user,
            flight=flight_ai452,
            weight_kg=18.5,
            status=BaggageStatus.LOADED,
            special_handling=False,
            risk_score=12.0,
            risk_level='LOW',
            risk_reason='Normal handling'
        )
        BaggageScan.objects.create(baggage=bag1, location='Check-in Counter T1-04', status_at_scan='Checked In', scanned_by=staff3_user)
        BaggageScan.objects.create(baggage=bag1, location='Security Belt 2', status_at_scan='Security Checked', scanned_by=staff3_user)
        BaggageScan.objects.create(baggage=bag1, location='Gate G12 Ramp', status_at_scan='Loading', scanned_by=staff1_user)
        BaggageScan.objects.create(baggage=bag1, location='Aircraft Hold A', status_at_scan='Loaded', scanned_by=staff1_user)

        # Booking 2: Passenger Rahul on 6E-721 (Upcoming Boarding Flight, Seat 12C)
        seat_12c = Seat.objects.get(aircraft=aircraft_6e1, seat_number='12C')
        booking2 = Booking.objects.create(
            booking_reference='ANV98231',
            passenger=passenger_user,
            passenger_name='Rahul Sharma',
            passenger_email='passenger@airport.com',
            passenger_phone='+91 98765 43210',
            passenger_id_passport='Z9823412',
            flight=flight_6e721,
            seat=seat_12c,
            seat_number='12C',
            status=BookingStatus.CHECKED_IN,
            booking_channel=BookingChannel.ONLINE_PASSENGER,
            ticket_price=4200.00
        )
        BoardingRecord.objects.create(
            booking=booking2,
            flight=flight_6e721,
            passenger=passenger_user,
            boarding_status=BoardingStatus.BOARDING,
            gate=gate_g08,
            sequence_number=12
        )
        bag2 = Baggage.objects.create(
            tag_number='BAG-6E721-3140',
            booking=booking2,
            passenger=passenger_user,
            flight=flight_6e721,
            weight_kg=14.0,
            status=BaggageStatus.AT_GATE,
            special_handling=False
        )
        BaggageScan.objects.create(baggage=bag2, location='Check-in Counter T1-08', status_at_scan='Checked In')
        BaggageScan.objects.create(baggage=bag2, location='Gate G08 Ramp', status_at_scan='At Gate')

        # Booking 3: Completed Past Flight UK-884
        seat_14d = Seat.objects.create(aircraft=aircraft_uk1, seat_number='14D', row=14, column='D', seat_class=SeatClass.ECONOMY)
        booking3 = Booking.objects.create(
            booking_reference='ANV10492',
            passenger=passenger_user,
            passenger_name='Rahul Sharma',
            passenger_email='passenger@airport.com',
            passenger_phone='+91 98765 43210',
            passenger_id_passport='Z9823412',
            flight=flight_uk884,
            seat=seat_14d,
            seat_number='14D',
            status=BookingStatus.COMPLETED,
            booking_channel=BookingChannel.ONLINE_PASSENGER,
            ticket_price=3600.00
        )
        BoardingRecord.objects.create(
            booking=booking3,
            flight=flight_uk884,
            passenger=passenger_user,
            boarding_status=BoardingStatus.BOARDED,
            boarding_time=now - timedelta(days=3, hours=4, minutes=15),
            gate=gate_g04,
            sequence_number=24
        )

        # Extra Bookings for Flight Manifests (AI-452 & 6E-721)
        for i, p_user in enumerate(extra_passengers):
            s_num = f"{i+1}B"
            s_obj = Seat.objects.filter(aircraft=aircraft_ai1, seat_number=s_num).first()
            b = Booking.objects.create(
                booking_reference=f"ANV{random.randint(10000, 99999)}",
                passenger=p_user,
                passenger_name=p_user.get_full_name(),
                passenger_email=p_user.email,
                passenger_phone=p_user.phone or '+91 99999 11111',
                flight=flight_ai452,
                seat=s_obj,
                seat_number=s_num,
                status=BookingStatus.CONFIRMED,
                ticket_price=5400.00
            )
            BoardingRecord.objects.create(
                booking=b,
                flight=flight_ai452,
                passenger=p_user,
                boarding_status=BoardingStatus.NOT_STARTED,
                gate=gate_g12,
                sequence_number=i+1
            )
            Baggage.objects.create(
                tag_number=f"BAG-AI452-{random.randint(1000, 9999)}",
                booking=b,
                passenger=p_user,
                flight=flight_ai452,
                weight_kg=random.uniform(10.0, 24.0),
                status=BaggageStatus.LOADED
            )

        # Populate bookings for 6E-721 to test Boarding Progress Bar
        for i in range(1, 25):
            s_num = f"{i}E"
            s_obj = Seat.objects.filter(aircraft=aircraft_6e1, seat_number=s_num).first()
            p_user = extra_passengers[i % len(extra_passengers)]
            is_boarded = i <= 20
            b = Booking.objects.create(
                booking_reference=f"ANV{random.randint(20000, 99999)}",
                passenger=p_user,
                passenger_name=f"Passenger {p_user.first_name} {i}",
                passenger_email=p_user.email,
                passenger_phone='+91 98000 ' + str(random.randint(10000, 99999)),
                flight=flight_6e721,
                seat=s_obj,
                seat_number=s_num,
                status=BookingStatus.BOARDED if is_boarded else BookingStatus.CONFIRMED,
                ticket_price=4200.00
            )
            BoardingRecord.objects.create(
                booking=b,
                flight=flight_6e721,
                passenger=p_user,
                boarding_status=BoardingStatus.BOARDED if is_boarded else BoardingStatus.NOT_STARTED,
                boarding_time=now - timedelta(minutes=random.randint(2, 10)) if is_boarded else None,
                gate=gate_g08,
                scanned_by_staff=staff2_user if is_boarded else None,
                sequence_number=i
            )

        # 10. Create Operational Issues
        self.stdout.write(self.style.NOTICE("Creating Operational Issues..."))
        OperationalIssue.objects.create(
            flight=flight_ai452,
            reported_by=staff1_user,
            issue_type=OperationalIssueType.BAGGAGE_ISSUE,
            priority=IssuePriority.MEDIUM,
            title='Cargo Hold B Netting Inspection Needed',
            description='Minor latch stiffness reported on rear cargo hold door during baggage loading.',
            status=IssueStatus.OPEN
        )
        OperationalIssue.objects.create(
            flight=None,
            reported_by=staff2_user,
            issue_type=OperationalIssueType.GATE_ISSUE,
            priority=IssuePriority.HIGH,
            title='Gate G20 Jetbridge Sensor Calibration',
            description='Jetbridge canopy leveling sensor error on Gate G20. Gate placed in maintenance.',
            status=IssueStatus.INVESTIGATING
        )

        # 11. Create Notifications
        self.stdout.write(self.style.NOTICE("Creating Notifications..."))
        # For Passenger
        Notification.objects.create(
            recipient=passenger_user,
            title='Flight AI-452 Delay Update',
            message='Flight AI-452 to Delhi is delayed by 22 minutes due to late inbound aircraft arrival. New departure time: 14:52 at Gate G12.',
            category=NotificationCategory.FLIGHT_DELAY,
            flight_number='AI-452'
        )
        Notification.objects.create(
            recipient=passenger_user,
            title='Gate Assigned for AI-452',
            message='Your flight AI-452 has been assigned to Gate G12, Terminal 1.',
            category=NotificationCategory.GATE_CHANGE,
            flight_number='AI-452'
        )
        Notification.objects.create(
            recipient=passenger_user,
            title='Baggage Loaded for AI-452',
            message='Your check-in baggage BAG-AI452-9842 has been successfully loaded onto aircraft VT-ANV.',
            category=NotificationCategory.BAGGAGE,
            flight_number='AI-452'
        )

        # For Staff
        Notification.objects.create(
            recipient=staff1_user,
            title='Turnaround Assignment: AI-452',
            message='You have been assigned as Ramp Operations Coordinator for Flight AI-452 at Gate G12.',
            category=NotificationCategory.STAFF_ASSIGNMENT,
            flight_number='AI-452'
        )
        Notification.objects.create(
            recipient=staff2_user,
            title='Boarding Call for 6E-721',
            message='Boarding operations commenced at Gate G08 for Flight 6E-721.',
            category=NotificationCategory.BOARDING,
            flight_number='6E-721'
        )

        # For Operations Manager
        Notification.objects.create(
            recipient=manager_user,
            title='AI Risk Alert: AI-452 Turnaround Window Compressed',
            message='ML prediction engine flagged AI-452 with moderate turnaround risk due to 22m inbound delay.',
            category=NotificationCategory.AI_ALERT,
            flight_number='AI-452'
        )
        Notification.objects.create(
            recipient=manager_user,
            title='Gate G20 Maintenance Notice',
            message='Gate G20 has been temporarily closed for sensor calibration.',
            category=NotificationCategory.OPERATIONAL_ALERT
        )

        # 12. Run AI Predictions for all active flights
        self.stdout.write(self.style.NOTICE("Generating AI Predictions across all active flights..."))
        for f in Flight.objects.all():
            update_flight_ai_prediction(f)

        self.stdout.write(self.style.SUCCESS("✓ Seed demo data created successfully!"))
        self.stdout.write(self.style.SUCCESS("=== DEMO CREDENTIALS ==="))
        self.stdout.write(self.style.SUCCESS("Admin: admin01 / admin (or admin / admin)"))
        self.stdout.write(self.style.SUCCESS("Operations Manager: manager / manager123"))
        self.stdout.write(self.style.SUCCESS("Passenger: passenger / pass123 (or passenger@airport.com)"))
        self.stdout.write(self.style.SUCCESS("New Passenger: newpassenger / pass123 (Zero bookings test)"))
        self.stdout.write(self.style.SUCCESS("Ground Staff 1: staff1 / staff123 (Ramp Ops - AI-452)"))
        self.stdout.write(self.style.SUCCESS("Ground Staff 2: staff2 / staff123 (Gate Ops - 6E-721)"))
