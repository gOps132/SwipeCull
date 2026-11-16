from django.utils import timezone

from .models import MediaFile


def populate_demo_files(session, count=10, seed_prefix='swipecull'):
    """Populate a CullSession with placeholder MediaFile rows idempotently."""
    now = timezone.now()
    new_files = 0
    for n in range(1, count + 1):
        _, file_created = MediaFile.objects.get_or_create(
            drive_file_id=f'demo-{session.pk}-{n:03d}',
            defaults={
                'session': session,
                'file_name': f'IMG_{n:04d}.jpg',
                'file_type': 'photo',
                'mime_type': 'image/jpeg',
                'file_size_mb': f'{2 + (n % 5) * 0.7:.2f}',
                'width': 800,
                'height': 1000,
                'taken_at': now,
                'thumbnail_url': f'https://picsum.photos/seed/{seed_prefix}-{session.pk}-{n}/800/1000',
            },
        )
        new_files += file_created

    session.total_files = session.media_files.count()
    session.save(update_fields=['total_files'])
    return new_files
