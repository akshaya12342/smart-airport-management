from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from .models import UserRole

def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in allowed_roles:
                messages.error(request, "You do not have authorization to access that operational section.")
                if request.user.role == UserRole.PASSENGER:
                    return redirect('passenger_dashboard')
                elif request.user.role == UserRole.GROUND_STAFF:
                    return redirect('ground_staff_dashboard')
                elif request.user.role == UserRole.OPERATIONS_MANAGER:
                    return redirect('manager_dashboard')
                return redirect('login')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def passenger_required(view_func):
    return role_required([UserRole.PASSENGER])(view_func)

def ground_staff_required(view_func):
    return role_required([UserRole.GROUND_STAFF])(view_func)

def operations_manager_required(view_func):
    return role_required([UserRole.OPERATIONS_MANAGER])(view_func)

def staff_or_manager_required(view_func):
    return role_required([UserRole.GROUND_STAFF, UserRole.OPERATIONS_MANAGER])(view_func)
