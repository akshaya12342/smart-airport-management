import random
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from .models import (
    User, UserRole, PassengerProfile, GroundStaffProfile,
    GroundStaffDepartment, StaffShift, StaffAvailability,
    Notification, NotificationCategory
)

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')
        
    if request.method == 'POST':
        # Check if 1-click quick demo login button was clicked
        quick_role = request.POST.get('quick_role')
        if quick_role:
            demo_credentials = {
                'admin': ('admin01', 'admin'),
                'admin01': ('admin01', 'admin'),
                'passenger': ('passenger', 'pass123'),
                'newpassenger': ('newpassenger', 'pass123'),
                'staff1': ('staff1', 'staff123'),
                'staff2': ('staff2', 'staff123'),
                'manager': ('manager', 'manager123'),
            }
            if quick_role in demo_credentials:
                u_name, u_pass = demo_credentials[quick_role]
                user = authenticate(request, username=u_name, password=u_pass)
                if user:
                    # Ground staff approval check
                    if user.is_ground_staff and hasattr(user, 'staff_profile') and not user.staff_profile.is_approved:
                        messages.warning(
                            request,
                            "Your Ground Staff account is pending approval by Airport Operations. "
                            "You will be able to log in once approved by an Operations Manager."
                        )
                        return render(request, 'core/login.html')

                    login(request, user)
                    messages.success(request, f"Welcome back, {user.get_full_name() or user.username}! Logged in as {user.get_role_display()}.")
                    return redirect('dashboard_redirect')
        
        username_or_email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        # Support login via email or username
        user = authenticate(request, username=username_or_email, password=password)
        if not user:
            # Check if email was provided
            try:
                user_obj = User.objects.get(email__iexact=username_or_email)
                user = authenticate(request, username=user_obj.username, password=password)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                pass
                
        if user:
            # Ground staff approval check
            if user.is_ground_staff and hasattr(user, 'staff_profile') and not user.staff_profile.is_approved:
                messages.warning(
                    request,
                    "Your Ground Staff account is pending approval by Airport Operations. "
                    "You will be able to log in once an Operations Manager approves your account."
                )
                return render(request, 'core/login.html')

            login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            return redirect('dashboard_redirect')
        else:
            messages.error(request, "Invalid username/email or password.")
            
    return render(request, 'core/login.html')

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')
        
    departments = GroundStaffDepartment.choices
    shifts = StaffShift.choices

    if request.method == 'POST':
        role = request.POST.get('role', UserRole.PASSENGER)
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
        elif len(password) < 4:
            messages.error(request, "Password must be at least 4 characters long.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Username is already taken.")
        elif User.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists.")
        else:
            if role == UserRole.GROUND_STAFF:
                department = request.POST.get('department', GroundStaffDepartment.RAMP_OPERATIONS)
                shift = request.POST.get('shift', StaffShift.MORNING)
                station = request.POST.get('station', 'COK Terminal 1')
                
                # Generate unique Employee ID
                rand_num = random.randint(350, 999)
                emp_id = f"STF-{rand_num}"
                while GroundStaffProfile.objects.filter(employee_id=emp_id).exists():
                    rand_num = random.randint(350, 999)
                    emp_id = f"STF-{rand_num}"

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    role=UserRole.GROUND_STAFF
                )
                GroundStaffProfile.objects.create(
                    user=user,
                    employee_id=emp_id,
                    department=department,
                    shift=shift,
                    station=station,
                    availability_status=StaffAvailability.AVAILABLE,
                    is_approved=False
                )

                # Send notification to all Operations Managers
                for mgr in User.objects.filter(role=UserRole.OPERATIONS_MANAGER):
                    Notification.objects.create(
                        recipient=mgr,
                        title="New Ground Staff Registration Pending Approval",
                        message=f"Ground Staff member {user.get_full_name() or user.username} ({emp_id} - {department}) registered. Please review and approve in Ground Staff Roster.",
                        category=NotificationCategory.STAFF_ASSIGNMENT
                    )

                messages.info(
                    request,
                    f"Ground Staff registration submitted successfully! Your account ({emp_id}) is pending approval by the Airport Operations Manager. You will be able to log in once approved."
                )
                return redirect('login')

            else: # PASSENGER
                passport = request.POST.get('passport', '').strip()
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    role=UserRole.PASSENGER
                )
                PassengerProfile.objects.create(
                    user=user,
                    passport_number=passport,
                    nationality='Indian'
                )
                login(request, user)
                messages.success(request, f"Account created! Welcome, {user.first_name or user.username}!")
                return redirect('passenger_dashboard')
            
    context = {
        'departments': departments,
        'shifts': shifts,
    }
    return render(request, 'core/register.html', context)

@login_required
def dashboard_redirect(request):
    user = request.user
    if user.is_operations_manager:
        return redirect('manager_dashboard')
    elif user.is_ground_staff:
        return redirect('ground_staff_dashboard')
    else:
        return redirect('passenger_dashboard')

@login_required
def notifications_list(request):
    notifications = Notification.objects.filter(recipient=request.user)
    return render(request, 'core/notifications.html', {'notifications': notifications})

@login_required
def mark_notification_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.is_read = True
    notif.save()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})
    return redirect('notifications_list')

@login_required
def mark_all_notifications_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read.")
    return redirect('notifications_list')
