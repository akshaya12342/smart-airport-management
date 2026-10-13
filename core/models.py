from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class UserRole(models.TextChoices):
    PASSENGER = 'PASSENGER', _('Passenger')
    GROUND_STAFF = 'GROUND_STAFF', _('Ground Staff')
    OPERATIONS_MANAGER = 'OPERATIONS_MANAGER', _('Airport Operations Manager')

class User(AbstractUser):
    role = models.CharField(
        max_length=30,
        choices=UserRole.choices,
        default=UserRole.PASSENGER,
        help_text=_("Primary operational role in the airport system")
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_passenger(self):
        return self.role == UserRole.PASSENGER

    @property
    def is_ground_staff(self):
        return self.role == UserRole.GROUND_STAFF

    @property
    def is_operations_manager(self):
        return self.role == UserRole.OPERATIONS_MANAGER

    def get_role_badge_class(self):
        if self.is_operations_manager:
            return 'badge-manager'
        elif self.is_ground_staff:
            return 'badge-staff'
        return 'badge-passenger'

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = UserRole.OPERATIONS_MANAGER
            self.is_staff = True
        super().save(*args, **kwargs)
        if self.is_superuser:
            OperationsManagerProfile.objects.get_or_create(
                user=self,
                defaults={
                    'employee_id': f"MGR-{self.id:03d}" if self.id else "MGR-ADM",
                    'desk_location': 'Airport Operations Control Center (AOCC)',
                    'shift': 'MORNING',
                }
            )

    def __str__(self):
        full_name = self.get_full_name()
        return f"{full_name or self.username} ({self.get_role_display()})"


class PassengerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='passenger_profile')
    passport_number = models.CharField(max_length=30, blank=True, null=True)
    nationality = models.CharField(max_length=50, default='Indian')
    emergency_contact = models.CharField(max_length=100, blank=True, null=True)
    special_assistance = models.BooleanField(default=False, help_text=_("Wheelchair or medical assistance required"))

    def __str__(self):
        return f"Passenger: {self.user.get_full_name() or self.user.username}"


class GroundStaffDepartment(models.TextChoices):
    BAGGAGE_HANDLING = 'BAGGAGE_HANDLING', _('Baggage Handling')
    RAMP_OPERATIONS = 'RAMP_OPERATIONS', _('Ramp Operations')
    GATE_OPERATIONS = 'GATE_OPERATIONS', _('Gate Operations')
    CABIN_CLEANING = 'CABIN_CLEANING', _('Cabin Cleaning')
    FUEL_CATERING = 'FUEL_CATERING', _('Fueling & Catering')
    TURNAROUND_COORD = 'TURNAROUND_COORD', _('Turnaround Coordination')
    MAINTENANCE = 'MAINTENANCE', _('Aircraft Maintenance')

class StaffShift(models.TextChoices):
    MORNING = 'MORNING', _('Morning Shift (06:00 - 14:00)')
    AFTERNOON = 'AFTERNOON', _('Afternoon Shift (14:00 - 22:00)')
    NIGHT = 'NIGHT', _('Night Shift (22:00 - 06:00)')

class StaffAvailability(models.TextChoices):
    AVAILABLE = 'AVAILABLE', _('Available')
    ASSIGNED = 'ASSIGNED', _('Assigned')
    BUSY = 'BUSY', _('Busy')
    ON_LEAVE = 'ON_LEAVE', _('On Leave')
    OFF_DUTY = 'OFF_DUTY', _('Off Duty')

class GroundStaffProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    employee_id = models.CharField(max_length=20, unique=True)
    department = models.CharField(
        max_length=30,
        choices=GroundStaffDepartment.choices,
        default=GroundStaffDepartment.RAMP_OPERATIONS
    )
    shift = models.CharField(
        max_length=20,
        choices=StaffShift.choices,
        default=StaffShift.MORNING
    )
    availability_status = models.CharField(
        max_length=20,
        choices=StaffAvailability.choices,
        default=StaffAvailability.AVAILABLE
    )
    station = models.CharField(max_length=50, default='COK Terminal 1')
    is_approved = models.BooleanField(
        default=False,
        help_text=_("Designates whether this ground staff account has been approved by Operations Management.")
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_staff_profiles'
    )

    def __str__(self):
        return f"{self.employee_id} - {self.user.get_full_name() or self.user.username} ({self.get_department_display()})"


class OperationsManagerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='manager_profile')
    employee_id = models.CharField(max_length=20, unique=True)
    desk_location = models.CharField(max_length=100, default='Airport Operations Control Center (AOCC)')
    shift = models.CharField(
        max_length=20,
        choices=StaffShift.choices,
        default=StaffShift.MORNING
    )

    def __str__(self):
        return f"Manager {self.employee_id}: {self.user.get_full_name() or self.user.username}"


class NotificationCategory(models.TextChoices):
    FLIGHT_DELAY = 'FLIGHT_DELAY', _('Flight Delay')
    GATE_CHANGE = 'GATE_CHANGE', _('Gate Change')
    BOARDING = 'BOARDING', _('Boarding Alert')
    BAGGAGE = 'BAGGAGE', _('Baggage Update')
    STAFF_ASSIGNMENT = 'STAFF_ASSIGNMENT', _('Staff Assignment')
    AI_ALERT = 'AI_ALERT', _('AI Predictive Alert')
    OPERATIONAL_ALERT = 'OPERATIONAL_ALERT', _('Operational Issue Alert')
    GENERAL = 'GENERAL', _('General Notice')

class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    category = models.CharField(
        max_length=30,
        choices=NotificationCategory.choices,
        default=NotificationCategory.GENERAL
    )
    flight_number = models.CharField(max_length=20, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.category}] {self.title} -> {self.recipient.username}"
