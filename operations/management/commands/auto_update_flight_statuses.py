import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from operations.status_updater import auto_update_all_flight_statuses


class Command(BaseCommand):
    help = 'Automatically updates flight statuses by comparing scheduled departure times against current datetime'

    def add_arguments(self, parser):
        parser.add_argument(
            '--daemon',
            action='store_true',
            help='Run continuously in a loop as a background worker daemon',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=30,
            help='Polling interval in seconds when running in daemon mode (default: 30s)',
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress detailed output',
        )

    def handle(self, *args, **options):
        daemon_mode = options['daemon']
        interval = options['interval']
        quiet = options['quiet']

        if daemon_mode:
            self.stdout.write(self.style.SUCCESS(f"🚀 Starting Flight Status Auto-Updater daemon (interval: {interval}s)..."))
            try:
                while True:
                    result = auto_update_all_flight_statuses(notify=True)
                    if not quiet or result['updated_count'] > 0:
                        self.stdout.write(
                            f"[{result['timestamp']}] Scanned {result['total_scanned']} flights. Updated {result['updated_count']} flights."
                        )
                        for f in result['updated_flights']:
                            self.stdout.write(
                                self.style.SUCCESS(f"  → Flight {f['flight_number']}: Status changed to {f['new_status']}")
                            )
                    time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("\nFlight Status Auto-Updater daemon stopped."))
        else:
            self.stdout.write("Running Flight Status Auto-Update sync...")
            result = auto_update_all_flight_statuses(notify=True)
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Status check complete. Scanned: {result['total_scanned']}, Updated: {result['updated_count']}"
                )
            )
            for f in result['updated_flights']:
                self.stdout.write(
                    self.style.SUCCESS(f"  → Flight {f['flight_number']}: Status changed to {f['new_status']}")
                )
