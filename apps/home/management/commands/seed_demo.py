from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.home.models import CullSession, DriveConnection
from apps.home.services import populate_demo_files

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

        new_files = populate_demo_files(session, count=count)

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
