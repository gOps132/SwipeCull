from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import MediaFile

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_DRIVE_FILES_URL = 'https://www.googleapis.com/drive/v3/files'
REQUEST_TIMEOUT = 15


class DriveAPIError(Exception):
    """Raised when Google OAuth or Drive API returns an error."""


def is_google_oauth_configured():
    """Return True when Google OAuth client credentials are present."""
    return bool(getattr(settings, 'GOOGLE_CLIENT_ID', '') and getattr(settings, 'GOOGLE_CLIENT_SECRET', ''))


def is_real_connection(connection):
    """Return True if the DriveConnection holds an active non-demo OAuth token."""
    return bool(
        connection
        and connection.is_active
        and connection.provider == 'google_drive'
        and connection.access_token
        and connection.access_token not in ('demo', 'demo-token')
    )


def build_auth_url(redirect_uri, state):
    """Build the Google OAuth2 consent screen URL for Drive access."""
    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(getattr(settings, 'GOOGLE_DRIVE_SCOPES', ['https://www.googleapis.com/auth/drive'])),
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
    }
    return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'


def exchange_code_for_tokens(code, redirect_uri):
    """Exchange an authorization code for access and refresh tokens."""
    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            'code': code,
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise DriveAPIError(f'Token exchange failed ({resp.status_code}): {resp.text}')
    return resp.json()


def refresh_access_token(connection):
    """Refresh an expired Google Drive access token using its refresh_token."""
    if not connection.refresh_token:
        raise DriveAPIError('Google Drive session expired and no refresh token is available. Please reconnect.')

    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'refresh_token': connection.refresh_token,
            'grant_type': 'refresh_token',
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise DriveAPIError(f'Token refresh failed ({resp.status_code}): {resp.text}')

    data = resp.json()
    connection.access_token = data['access_token']
    expires_in = int(data.get('expires_in', 3600))
    connection.token_expiry = timezone.now() + timedelta(seconds=expires_in)
    connection.save(update_fields=['access_token', 'token_expiry'])
    return connection.access_token


def ensure_valid_access_token(connection):
    """Return a valid access token, refreshing it if expired or near expiry."""
    if not is_real_connection(connection):
        raise DriveAPIError('Google Drive is not connected.')

    if connection.token_expiry and connection.token_expiry <= timezone.now() + timedelta(seconds=60):
        return refresh_access_token(connection)
    return connection.access_token


def _drive_headers(connection):
    token = ensure_valid_access_token(connection)
    return {'Authorization': f'Bearer {token}'}


def list_drive_folders(connection, page_size=50):
    """List folders in the user's Google Drive, including My Drive root."""
    params = {
        'q': "mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        'fields': 'files(id, name, modifiedTime)',
        'orderBy': 'modifiedTime desc',
        'pageSize': page_size,
    }
    resp = requests.get(
        GOOGLE_DRIVE_FILES_URL,
        headers=_drive_headers(connection),
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise DriveAPIError(f'Failed to list Drive folders ({resp.status_code}): {resp.text}')

    folders = [{'id': 'root', 'name': 'My Drive (Root)', 'modifiedTime': ''}]
    folders.extend(resp.json().get('files', []))
    return folders


def _parse_drive_datetime(raw_value):
    if not raw_value:
        return None
    parsed = parse_datetime(raw_value)
    if parsed is not None:
        return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
    try:
        dt = datetime.strptime(raw_value, '%Y:%m:%d %H:%M:%S')
        return timezone.make_aware(dt)
    except ValueError:
        return None


def sync_folder_files(connection, session, folder_id, max_files=100):
    """Fetch image files from a Google Drive folder and store them as MediaFile rows."""
    headers = _drive_headers(connection)
    safe_folder_id = folder_id.replace("'", "\\'")
    query = f"'{safe_folder_id}' in parents and trashed = false and mimeType contains 'image/'"

    synced_count = 0
    page_token = None

    while synced_count < max_files:
        params = {
            'q': query,
            'fields': (
                'nextPageToken, files(id, name, mimeType, size, '
                'imageMediaMetadata(width, height, time), createdTime, thumbnailLink)'
            ),
            'orderBy': 'createdTime desc',
            'pageSize': min(100, max_files - synced_count),
        }
        if page_token:
            params['pageToken'] = page_token

        resp = requests.get(GOOGLE_DRIVE_FILES_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if not resp.ok:
            raise DriveAPIError(f'Failed to list Drive files ({resp.status_code}): {resp.text}')

        payload = resp.json()
        files = payload.get('files', [])
        if not files:
            break

        for item in files:
            meta = item.get('imageMediaMetadata') or {}
            size_bytes = int(item['size']) if item.get('size') else 0
            size_mb = Decimal(f'{size_bytes / (1024 * 1024):.2f}') if size_bytes else Decimal('0.00')
            taken_at = _parse_drive_datetime(meta.get('time')) or _parse_drive_datetime(item.get('createdTime'))

            MediaFile.objects.update_or_create(
                drive_file_id=item['id'],
                defaults={
                    'session': session,
                    'file_name': item.get('name', 'Untitled')[:255],
                    'file_type': 'photo',
                    'mime_type': item.get('mimeType', 'image/jpeg')[:100],
                    'file_size_mb': size_mb,
                    'width': meta.get('width'),
                    'height': meta.get('height'),
                    'taken_at': taken_at,
                    'thumbnail_url': item.get('thumbnailLink') or '',
                },
            )
            synced_count += 1

        page_token = payload.get('nextPageToken')
        if not page_token:
            break

    session.total_files = session.media_files.count()
    session.save(update_fields=['total_files'])
    return synced_count


def fetch_drive_file_preview(connection, drive_file_id):
    """Download image bytes from Google Drive for authenticated preview."""
    headers = _drive_headers(connection)
    url = f'{GOOGLE_DRIVE_FILES_URL}/{drive_file_id}'
    resp = requests.get(
        url,
        headers=headers,
        params={'alt': 'media'},
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise DriveAPIError(f'Failed to fetch file preview ({resp.status_code})')
    content_type = resp.headers.get('Content-Type', 'image/jpeg')
    return resp.content, content_type


def trash_drive_file(connection, drive_file_id):
    """Move a file to Google Drive Trash (recoverable by user in Drive)."""
    headers = _drive_headers(connection)
    url = f'{GOOGLE_DRIVE_FILES_URL}/{drive_file_id}'
    resp = requests.patch(
        url,
        headers=headers,
        json={'trashed': True},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 404:
        return True
    if not resp.ok:
        raise DriveAPIError(f'Failed to trash Drive file {drive_file_id} ({resp.status_code}): {resp.text}')
    return True
