from .models import Notification
from operations.models import Airport

def notifications_processor(request):
    try:
        all_airports = Airport.objects.all().order_by('city')
    except Exception:
        all_airports = []

    if request.user.is_authenticated:
        unread_notifications = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).order_by('-created_at')
        
        recent_notifications = Notification.objects.filter(
            recipient=request.user
        ).order_by('-created_at')[:8]
        
        return {
            'unread_notifications_count': unread_notifications.count(),
            'user_notifications': recent_notifications,
            'all_airports': all_airports,
        }
    return {
        'unread_notifications_count': 0,
        'user_notifications': [],
        'all_airports': all_airports,
    }

