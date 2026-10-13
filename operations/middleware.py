from django.utils.deprecation import MiddlewareMixin
from operations.status_updater import run_auto_status_sync_if_needed


class FlightStatusAutoSyncMiddleware(MiddlewareMixin):
    """
    Middleware that automatically synchronizes flight statuses with current time
    on incoming web requests (throttled to avoid redundant queries).
    Ensures every page load and API response reflects accurate live flight statuses.
    """

    def process_request(self, request):
        # Trigger background flight status sync if throttle interval has elapsed
        try:
            run_auto_status_sync_if_needed(interval_seconds=3)
        except Exception:
            # Prevent middleware errors from blocking web request processing
            pass
        return None
