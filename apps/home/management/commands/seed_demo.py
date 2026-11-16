from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.home.models import CullSession, DriveConnection, MediaFile

DEMO_FOLDER_NAME = 'Demo Trip Photos'
DEMO_FOLDER_ID = 'demo-folder'


class Command(BaseCommand):
    help = (
        'Create a demo drive connection and cull session with placeholder '
        'media files so the swipe flow can be built and demoed without '
        'real Google Drive OAuth. Safe to run more than once.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            help='User to attach the demo session to (default: first superuser, then first user).',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=15,
            help='Number of demo media files to create (default: 15).',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete the existing demo session (and its decisions) before seeding.',
        )

    def handle(self, *args, **options):
        count = options['count']
        if count < 1:
            raise CommandError('--count must be at least 1.')

        user = self._get_user(options['username'])

        if options['reset']:
            deleted, _ = CullSession.objects.filter(
                user=user, folder_id=DEMO_FOLDER_ID
            ).delete()
            if deleted:
                self.stdout.write(f'Removed previous demo session data ({deleted} rows).')

        # Placeholder credentials only: this connection never talks to a real provider.
        connection, _ = DriveConnection.objects.get_or_create(
            user=user,
            provider='google_drive',
            access_token='demo-token',
        )

        session, created = CullSession.objects.get_or_create(
            user=user,
            drive_connection=connection,
            folder_id=DEMO_FOLDER_ID,
            defaults={'folder_name': DEMO_FOLDER_NAME},
        )

        now = timezone.now()
        new_files = 0
        for n in range(1, count + 1):
            # drive_file_id is globally unique, so namespace it by session.
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
                    'thumbnail_url': f'https://picsum.photos/seed/swipecull-{n}/800/1000',
                },
            )
            new_files += file_created

        session.total_files = session.media_files.count()
        session.save(update_fields=['total_files'])

        verb = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} demo session #{session.pk} for "{user.username}": '
            f'{new_files} new files, {session.total_files} total.'
        ))

    def _get_user(self, username):
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f'User "{username}" does not exist.')

        user = (
            User.objects.filter(is_superuser=True).order_by('pk').first()
            or User.objects.order_by('pk').first()
        )
        if user is None:
            raise CommandError(
                'No users exist yet. Register an account (or run createsuperuser) first.'
            )
        return user
