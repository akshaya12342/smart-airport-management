from django import forms
from core.models import User, GroundStaffProfile, PassengerProfile, StaffAvailability
from .models import (
    Flight, Aircraft, Gate, Booking, Baggage, BaggageScan, 
    StaffAssignment, OperationalIssue, DelayRecord, DelayReason,
    FlightStatus, BaggageStatus, IssuePriority, IssueStatus, OperationalIssueType
)

class FlightSearchForm(forms.Form):
    source = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Kochi or COK'}))
    destination = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Delhi or DEL'}))
    travel_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    airline = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Air India or AI'}))
    flight_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. AI-452'}))

class PassengerBookingForm(forms.Form):
    passenger_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Passenger Name'}))
    passenger_email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'passenger@email.com'}))
    passenger_phone = forms.CharField(max_length=25, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+91 98765 43210'}))
    passenger_id_passport = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ID / Passport Number'}))
    seat_number = forms.CharField(max_length=10, widget=forms.HiddenInput(attrs={'id': 'selected_seat_input'}))
    baggage_weight = forms.DecimalField(max_digits=5, decimal_places=2, initial=15.0, widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Weight in kg'}))
    special_handling = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    payment_method = forms.CharField(max_length=50, required=False, widget=forms.HiddenInput(attrs={'id': 'payment_method_input'}))
    transaction_id = forms.CharField(max_length=50, required=False, widget=forms.HiddenInput(attrs={'id': 'transaction_id_input'}))

class FlightForm(forms.ModelForm):
    departure_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'id_departure_date'})
    )
    departure_time = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'hh:mm (e.g. 09:30 or 02:45)', 'id': 'id_departure_time'})
    )
    departure_meridian = forms.ChoiceField(
        required=False,
        choices=[('AM', 'AM (Morning)'), ('PM', 'PM (Afternoon / Night)')],
        initial='AM',
        widget=forms.Select(attrs={'class': 'form-select fw-bold text-primary', 'id': 'id_departure_meridian'})
    )

    arrival_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'id_arrival_date'})
    )
    arrival_time = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'hh:mm (e.g. 11:45 or 05:30)', 'id': 'id_arrival_time'})
    )
    arrival_meridian = forms.ChoiceField(
        required=False,
        choices=[('AM', 'AM (Morning)'), ('PM', 'PM (Afternoon / Night)')],
        initial='AM',
        widget=forms.Select(attrs={'class': 'form-select fw-bold text-primary', 'id': 'id_arrival_meridian'})
    )

    class Meta:
        model = Flight
        fields = [
            'flight_number', 'airline', 'aircraft', 'source_airport', 'destination_airport',
            'flight_type', 'scheduled_departure', 'scheduled_arrival', 'status', 'gate',
            'delay_minutes', 'delay_reason', 'base_price'
        ]
        widgets = {
            'flight_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. AI-452'}),
            'airline': forms.Select(attrs={'class': 'form-select'}),
            'aircraft': forms.Select(attrs={'class': 'form-select'}),
            'source_airport': forms.Select(attrs={'class': 'form-select'}),
            'destination_airport': forms.Select(attrs={'class': 'form-select'}),
            'flight_type': forms.Select(attrs={'class': 'form-select'}),
            'scheduled_departure': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'scheduled_arrival': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'gate': forms.Select(attrs={'class': 'form-select'}),
            'delay_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'delay_reason': forms.Select(attrs={'class': 'form-select'}),
            'base_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['scheduled_departure'].required = False
        self.fields['scheduled_arrival'].required = False
        
        from django.utils import timezone
        if self.instance and self.instance.pk:
            if self.instance.scheduled_departure:
                local_dep = timezone.localtime(self.instance.scheduled_departure)
                self.initial['departure_date'] = local_dep.date()
                self.initial['departure_time'] = local_dep.strftime('%I:%M')
                self.initial['departure_meridian'] = local_dep.strftime('%p')
            if self.instance.scheduled_arrival:
                local_arr = timezone.localtime(self.instance.scheduled_arrival)
                self.initial['arrival_date'] = local_arr.date()
                self.initial['arrival_time'] = local_arr.strftime('%I:%M')
                self.initial['arrival_meridian'] = local_arr.strftime('%p')

    def clean(self):
        cleaned_data = super().clean()
        import re
        from django.utils import timezone
        
        # Process Departure Date, Time & Meridian (AM/PM)
        dep_date = cleaned_data.get('departure_date')
        dep_time_str = cleaned_data.get('departure_time')
        dep_meridian = cleaned_data.get('departure_meridian') or 'AM'
        
        if dep_date and dep_time_str:
            dep_time_str = dep_time_str.strip().upper().replace(' ', '')
            if 'PM' in dep_time_str:
                dep_meridian = 'PM'
                dep_time_str = dep_time_str.replace('PM', '')
            elif 'AM' in dep_time_str:
                dep_meridian = 'AM'
                dep_time_str = dep_time_str.replace('AM', '')
                
            m = re.match(r'^(\d{1,2}):(\d{2})$', dep_time_str)
            if m:
                h, mins = int(m.group(1)), int(m.group(2))
                if 1 <= h <= 12 and 0 <= mins <= 59:
                    if dep_meridian == 'PM' and h < 12:
                        h += 12
                    elif dep_meridian == 'AM' and h == 12:
                        h = 0
                    dep_dt = timezone.datetime(dep_date.year, dep_date.month, dep_date.day, h, mins, 0)
                    cleaned_data['scheduled_departure'] = timezone.make_aware(dep_dt, timezone.get_current_timezone())
                elif 0 <= h <= 23 and 0 <= mins <= 59:
                    dep_dt = timezone.datetime(dep_date.year, dep_date.month, dep_date.day, h, mins, 0)
                    cleaned_data['scheduled_departure'] = timezone.make_aware(dep_dt, timezone.get_current_timezone())
                else:
                    self.add_error('departure_time', 'Invalid departure time. Hours must be 1-12 and minutes 0-59.')
            else:
                self.add_error('departure_time', 'Enter departure time in hh:mm format (e.g. 09:30 or 02:45).')
                
        # Process Arrival Date, Time & Meridian (AM/PM)
        arr_date = cleaned_data.get('arrival_date')
        arr_time_str = cleaned_data.get('arrival_time')
        arr_meridian = cleaned_data.get('arrival_meridian') or 'AM'
        
        if arr_date and arr_time_str:
            arr_time_str = arr_time_str.strip().upper().replace(' ', '')
            if 'PM' in arr_time_str:
                arr_meridian = 'PM'
                arr_time_str = arr_time_str.replace('PM', '')
            elif 'AM' in arr_time_str:
                arr_meridian = 'AM'
                arr_time_str = arr_time_str.replace('AM', '')
                
            m = re.match(r'^(\d{1,2}):(\d{2})$', arr_time_str)
            if m:
                h, mins = int(m.group(1)), int(m.group(2))
                if 1 <= h <= 12 and 0 <= mins <= 59:
                    if arr_meridian == 'PM' and h < 12:
                        h += 12
                    elif arr_meridian == 'AM' and h == 12:
                        h = 0
                    arr_dt = timezone.datetime(arr_date.year, arr_date.month, arr_date.day, h, mins, 0)
                    cleaned_data['scheduled_arrival'] = timezone.make_aware(arr_dt, timezone.get_current_timezone())
                elif 0 <= h <= 23 and 0 <= mins <= 59:
                    arr_dt = timezone.datetime(arr_date.year, arr_date.month, arr_date.day, h, mins, 0)
                    cleaned_data['scheduled_arrival'] = timezone.make_aware(arr_dt, timezone.get_current_timezone())
                else:
                    self.add_error('arrival_time', 'Invalid arrival time. Hours must be 1-12 and minutes 0-59.')
            else:
                self.add_error('arrival_time', 'Enter arrival time in hh:mm format (e.g. 11:45 or 05:30).')
                
        if not cleaned_data.get('scheduled_departure'):
            self.add_error('departure_date', 'Scheduled departure date and time with AM/PM is required.')
        if not cleaned_data.get('scheduled_arrival'):
            self.add_error('arrival_date', 'Scheduled arrival date and time with AM/PM is required.')
            
        return cleaned_data

class FlightStatusUpdateForm(forms.Form):
    status = forms.ChoiceField(choices=FlightStatus.choices, widget=forms.Select(attrs={'class': 'form-select'}))
    gate = forms.ModelChoiceField(queryset=Gate.objects.all(), required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    delay_minutes = forms.IntegerField(required=False, initial=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    delay_reason = forms.ChoiceField(choices=[('', 'None')] + list(DelayReason.choices), required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    cancellation_reason = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Reason if cancelling flight'}))

class AircraftForm(forms.ModelForm):
    class Meta:
        model = Aircraft
        fields = ['registration_number', 'model', 'aircraft_type', 'seating_capacity', 'airline', 'status']
        widgets = {
            'registration_number': forms.TextInput(attrs={'class': 'form-control'}),
            'model': forms.TextInput(attrs={'class': 'form-control'}),
            'aircraft_type': forms.Select(attrs={'class': 'form-select'}),
            'seating_capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'airline': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

class GateForm(forms.ModelForm):
    class Meta:
        model = Gate
        fields = ['gate_number', 'terminal', 'gate_type', 'compatibility', 'status']
        widgets = {
            'gate_number': forms.TextInput(attrs={'class': 'form-control'}),
            'terminal': forms.TextInput(attrs={'class': 'form-control'}),
            'gate_type': forms.Select(attrs={'class': 'form-select'}),
            'compatibility': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

class StaffAssignmentForm(forms.ModelForm):
    class Meta:
        model = StaffAssignment
        fields = ['staff', 'flight', 'role_in_flight', 'notes']
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'flight': forms.Select(attrs={'class': 'form-select'}),
            'role_in_flight': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Ramp Coordinator, Gate Lead'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class OperationalIssueForm(forms.ModelForm):
    class Meta:
        model = OperationalIssue
        fields = ['flight', 'issue_type', 'priority', 'title', 'description']
        widgets = {
            'flight': forms.Select(attrs={'class': 'form-select'}),
            'issue_type': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Short summary of the issue'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Detailed description of the operational problem'}),
        }

class BaggageScanForm(forms.ModelForm):
    class Meta:
        model = BaggageScan
        fields = ['location', 'status_at_scan', 'notes']
        widgets = {
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Gate G12 Ramp, Sort Belt 3'}),
            'status_at_scan': forms.Select(choices=BaggageStatus.choices, attrs={'class': 'form-select'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional observations'}),
        }

class DelayRecordForm(forms.ModelForm):
    class Meta:
        model = DelayRecord
        fields = ['flight', 'delay_minutes', 'reason', 'detailed_description']
        widgets = {
            'flight': forms.Select(attrs={'class': 'form-select'}),
            'delay_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'detailed_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
