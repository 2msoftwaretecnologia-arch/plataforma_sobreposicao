import shutil
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

from .models import FileManagement, StorageSnapshot


def get_file_management():
    try:
        return FileManagement.objects.first()
    except FileManagement.DoesNotExist:
        return None


def format_bytes(num_bytes):
    value = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f"{value:.2f} {unit}"
        value /= 1024


def get_database_size_bytes():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        return cursor.fetchone()[0]


def get_disk_usage():
    path = getattr(settings, 'STORAGE_DISK_PATH', settings.BASE_DIR)
    usage = shutil.disk_usage(path)
    return usage.total, usage.used


def get_storage_status(percent):
    if percent >= 90:
        return 'lotado', 'Lotado'
    if percent >= 70:
        return 'quase_cheio', 'Quase cheio'
    return 'seguro', 'Seguro'


def capture_storage_snapshot():
    disk_total, disk_used = get_disk_usage()
    snapshot = StorageSnapshot.objects.create(
        database_size_bytes=get_database_size_bytes(),
        disk_used_bytes=disk_used,
        disk_total_bytes=disk_total,
    )
    return snapshot


def get_or_refresh_latest_snapshot(max_age_minutes=60):
    latest = StorageSnapshot.objects.first()
    if latest is None:
        return capture_storage_snapshot()

    age = timezone.now() - latest.captured_at
    if age > timedelta(minutes=max_age_minutes):
        return capture_storage_snapshot()

    return latest


def get_last_7_days_snapshots():
    since = timezone.now() - timedelta(days=7)
    snapshots = list(
        StorageSnapshot.objects.filter(captured_at__gte=since).order_by('captured_at')
    )

    daily = {}
    for snapshot in snapshots:
        day = timezone.localtime(snapshot.captured_at).date()
        daily[day] = snapshot

    return [daily[day] for day in sorted(daily.keys())]
