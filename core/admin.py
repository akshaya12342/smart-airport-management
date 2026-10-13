from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.html import format_html
from .models import (
    User, PassengerProfile, GroundStaffProfile, 
    OperationsManagerProfile, Notification
)

@admin.action(description="Approve selected Ground Staff accounts")
def approve_ground_staff(modeladmin, request, queryset):
    updated = queryset.update(
        is_approved=True, 
        approved_at=timezone.now(),
        approved_by=request.user
    )
    modeladmin.message_user(request, f"Successfully approved {updated} ground staff account(s).")


class PassengerProfileInline(admin.StackedInline):
    model = PassengerProfile
    can_delete = False
    verbose_name_plural = 'Passenger Profile'
    extra = 0


class GroundStaffProfileInline(admin.StackedInline):
    model = GroundStaffProfile
    fk_name = 'user'
    can_delete = False
    verbose_name_plural = 'Ground Staff Profile'
    extra = 0


class OperationsManagerProfileInline(admin.StackedInline):
    model = OperationsManagerProfile
    can_delete = False
    verbose_name_plural = 'Operations Manager Profile'
    extra = 0


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('username', 'get_full_name', 'email', 'role_badge', 'operational_summary', 'is_staff', 'is_active', 'formatted_date_joined')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Airport Role & Contact', {
            'fields': ('role', 'phone'),
        }),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Airport Role & Contact', {
            'fields': ('role', 'phone', 'first_name', 'last_name', 'email'),
        }),
    )

    inlines = [PassengerProfileInline, GroundStaffProfileInline, OperationsManagerProfileInline]

    @admin.display(description="Role")
    def role_badge(self, obj):
        colors = {
            'PASSENGER': '#0284c7',
            'GROUND_STAFF': '#15803d',
            'OPERATIONS_MANAGER': '#4f46e5',
        }
        color = colors.get(obj.role, '#64748b')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_role_display()
        )

    @admin.display(description="Operational Status & Telemetry")
    def operational_summary(self, obj):
        if obj.is_ground_staff and hasattr(obj, 'staff_profile'):
            sp = obj.staff_profile
            app_status = "Approved" if sp.is_approved else "Pending Approval"
            assignments = obj.flight_assignments.filter(status='ACTIVE')
            if assignments.exists():
                a = assignments.first()
                gate_str = f"Gate {a.flight.gate.gate_number}" if a.flight.gate else "TBD"
                return f"{sp.employee_id} [{sp.get_availability_status_display()}] -> {a.flight.flight_number} @ {gate_str} ({app_status})"
            return f"{sp.employee_id} [{sp.get_availability_status_display()}] - {sp.station} ({app_status})"

        elif obj.is_passenger:
            b_count = obj.bookings.count()
            recent = obj.bookings.first()
            if recent:
                br = getattr(recent, 'boarding_record', None)
                b_status = "🟢 Boarded" if (br and br.boarding_status == 'BOARDED' or recent.status == 'BOARDED') else "🟡 Waiting"
                gate_str = f"Gate {recent.flight.gate.gate_number}" if recent.flight.gate else "TBD"
                return f"{b_count} Bookings (Recent: {recent.flight.flight_number} @ {gate_str} - {b_status})"
            return "No Bookings"

        elif obj.is_operations_manager and hasattr(obj, 'manager_profile'):
            return f"{obj.manager_profile.employee_id} [{obj.manager_profile.desk_location}]"

        return "-"

    @admin.display(description="Date Joined")
    def formatted_date_joined(self, obj):
        if obj.date_joined:
            return obj.date_joined.strftime("%d %b %Y, %I:%M %p")
        return "-"


@admin.register(GroundStaffProfile)
class GroundStaffProfileAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'get_staff_name', 'department', 'shift', 'availability_status', 'station', 'assigned_flights_and_gates', 'is_approved', 'formatted_approved_at')
    list_filter = ('is_approved', 'department', 'shift', 'availability_status', 'station')
    search_fields = ('employee_id', 'user__username', 'user__first_name', 'user__last_name', 'user__email')
    actions = [approve_ground_staff]
    
    @admin.display(description="Staff Name", ordering="user__first_name")
    def get_staff_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description="Assigned Flight & Gate Location")
    def assigned_flights_and_gates(self, obj):
        assignments = obj.user.flight_assignments.filter(status='ACTIVE')
        if assignments.exists():
            items = []
            for a in assignments:
                gate_str = f"Gate {a.flight.gate.gate_number}" if a.flight.gate else "Gate TBD"
                items.append(f"{a.flight.flight_number} ({gate_str})")
            return ", ".join(items)
        return "No Flight Assigned"

    @admin.display(description="Approved At")
    def formatted_approved_at(self, obj):
        if obj.approved_at:
            return obj.approved_at.strftime("%d %b %Y, %I:%M %p")
        return "-"


@admin.register(PassengerProfile)
class PassengerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'passport_number', 'nationality', 'special_assistance')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'passport_number')


@admin.register(OperationsManagerProfile)
class OperationsManagerProfileAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'user', 'desk_location', 'shift')
    search_fields = ('employee_id', 'user__username', 'user__first_name')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'category', 'flight_number', 'is_read', 'formatted_created_at')
    list_filter = ('category', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__username', 'flight_number')

    @admin.display(description="Created At")
    def formatted_created_at(self, obj):
        if obj.created_at:
            return obj.created_at.strftime("%d %b %Y, %I:%M %p")
        return "-"
