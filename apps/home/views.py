import csv
from datetime import timedelta
from decimal import Decimal
import json
import secrets
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .drive_service import (
    DriveAPIError,
    build_auth_url,
    exchange_code_for_tokens,
    fetch_drive_file_preview,
    is_google_oauth_configured,
    is_real_connection,
    list_drive_folders,
    sync_folder_files,
    trash_drive_file,
)
from .models import CullSession, DriveConnection, MediaFile, SwipeDecision
from .services import populate_demo_files


def _serialize_media_file(media_file):
    size_mb = float(media_file.file_size_mb) if media_file.file_size_mb is not None else 0.0
    dim = (
        f'{media_file.width} × {media_file.height}'
        if media_file.width and media_file.height
        else media_file.get_file_type_display()
    )
    taken = media_file.taken_at.strftime('%b %d, %Y') if media_file.taken_at else 'Unknown date'
    is_demo = media_file.drive_file_id.startswith('demo-')
    src = media_file.thumbnail_url or '' if is_demo else reverse('drive_file_preview', args=[media_file.id])
    return {
        'id': media_file.id,
        'src': src,
        'name': media_file.file_name,
        'size': f'{size_mb:.1f} MB',
        'dim': dim,
        'date': taken,
        'bytes': size_mb,
    }


def _session_stats(session, user):
    decisions = SwipeDecision.objects.filter(session=session, user=user).select_related('media_file')
    kept_count = 0
    trashed_count = 0
    space_cleared_mb = 0.0
    decided_ids = set()
    history = []

    for d in decisions.order_by('decided_at', 'id'):
        decided_ids.add(d.media_file_id)
        if d.decision == 'keep':
            kept_count += 1
        else:
            trashed_count += 1
            if d.media_file.file_size_mb is not None:
                space_cleared_mb += float(d.media_file.file_size_mb)
        history.append({
            'photo': _serialize_media_file(d.media_file),
            'action': d.decision,
        })

    total = session.media_files.count()
    remaining = max(total - len(decided_ids), 0)
    return {
        'kept_count': kept_count,
        'trashed_count': trashed_count,
        'space_cleared_mb': round(space_cleared_mb, 2),
        'total': total,
        'remaining': remaining,
        'decided_ids': decided_ids,
        'history': history,
    }


def _render_home(request, active_session=None):
    sessions = list(CullSession.objects.filter(user=request.user).prefetch_related('media_files'))
    if active_session is None and sessions:
        active_session = next((s for s in sessions if s.status == 'active'), sessions[0])

    session_data = None
    if active_session is not None:
        stats = _session_stats(active_session, request.user)
        undecided_files = [
            _serialize_media_file(mf)
            for mf in active_session.media_files.all()
            if mf.id not in stats['decided_ids']
        ]
        session_data = {
            'session_id': active_session.id,
            'folder_name': active_session.folder_name,
            'status': active_session.status,
            'total': stats['total'],
            'kept_count': stats['kept_count'],
            'trashed_count': stats['trashed_count'],
            'space_cleared_mb': stats['space_cleared_mb'],
            'photos': undecided_files,
            'history': stats['history'],
            'decide_url': f'/session/{active_session.id}/decide/',
            'undo_url': f'/session/{active_session.id}/undo/',
            'finalize_url': f'/session/{active_session.id}/finalize/',
        }

    user_drive_connection = DriveConnection.objects.filter(
        user=request.user,
        provider='google_drive',
        is_active=True,
    ).first()
    drive_connection = user_drive_connection or (
        active_session.drive_connection if active_session is not None else None
    )

    return render(
        request,
        'home/home.html',
        {
            'sessions': sessions,
            'active_session': active_session,
            'drive_connection': drive_connection,
            'drive_connected': is_real_connection(user_drive_connection),
            'google_oauth_configured': is_google_oauth_configured(),
            'session_data': session_data,
        },
    )


@login_required
def home(request):
    return _render_home(request)


@login_required
def session_detail(request, session_id):
    session = get_object_or_404(CullSession, pk=session_id, user=request.user)
    return _render_home(request, active_session=session)


@login_required
@require_POST
def create_session(request):
    source = request.POST.get('source', 'demo').strip()
    folder_name = (
        request.POST.get('drive_folder_name', '').strip()
        if source == 'google_drive'
        else ''
    ) or request.POST.get('folder_name', '').strip() or 'New Photo Session'

    if source == 'google_drive':
        drive_folder_id = request.POST.get('drive_folder_id', '').strip()
        if not drive_folder_id:
            messages.error(request, 'Please select a Google Drive folder to import.')
            return redirect('home')

        connection = DriveConnection.objects.filter(
            user=request.user,
            provider='google_drive',
            is_active=True,
        ).first()
        if not is_real_connection(connection):
            messages.error(request, 'Please connect your Google Drive account first.')
            return redirect('home')

        session = CullSession.objects.create(
            user=request.user,
            drive_connection=connection,
            folder_name=folder_name[:255],
            folder_id=drive_folder_id[:255],
        )
        try:
            synced = sync_folder_files(connection, session, drive_folder_id)
        except DriveAPIError as exc:
            session.delete()
            messages.error(request, f'Could not sync folder from Google Drive: {exc}')
            return redirect('home')

        if synced == 0:
            messages.info(request, f'Imported "{session.folder_name}" — no image files found in this folder.')
        else:
            messages.success(request, f'Synced {synced} photo(s) from Google Drive folder "{session.folder_name}".')
        return redirect('session_detail', session_id=session.id)

    valid_providers = {choice[0] for choice in DriveConnection.PROVIDER_CHOICES}
    provider = request.POST.get('provider', 'google_drive').strip()
    if provider not in valid_providers:
        provider = 'google_drive'
    try:
        count = int(request.POST.get('count', 10))
    except (TypeError, ValueError):
        count = 10
    count = max(1, min(count, 30))

    connection, _ = DriveConnection.objects.get_or_create(
        user=request.user,
        provider=provider,
        defaults={'access_token': 'demo-token'},
    )
    session = CullSession.objects.create(
        user=request.user,
        drive_connection=connection,
        folder_name=folder_name[:255],
        folder_id=f'session-{uuid4().hex[:8]}',
    )
    populate_demo_files(session, count=count)
    return redirect('session_detail', session_id=session.id)


@login_required
@require_POST
def delete_session(request, session_id):
    session = get_object_or_404(CullSession, pk=session_id, user=request.user)
    session.delete()
    next_url = request.POST.get('next', '')
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect('home')


@login_required
@require_POST
def decide_file(request, session_id):
    session = get_object_or_404(CullSession, pk=session_id, user=request.user)
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid JSON payload.')

    media_file_id = payload.get('media_file_id')
    decision = payload.get('decision')
    if decision not in ('keep', 'trash') or not media_file_id:
        return HttpResponseBadRequest('media_file_id and valid decision (keep|trash) are required.')

    media_file = get_object_or_404(MediaFile, pk=media_file_id, session=session)
    SwipeDecision.objects.update_or_create(
        media_file=media_file,
        session=session,
        user=request.user,
        defaults={'decision': decision},
    )

    stats = _session_stats(session, request.user)
    if stats['remaining'] == 0 and session.status == 'active':
        session.status = 'completed'
        session.completed_at = timezone.now()
        session.save(update_fields=['status', 'completed_at'])

    return JsonResponse({
        'ok': True,
        'session_status': session.status,
        'kept_count': stats['kept_count'],
        'trashed_count': stats['trashed_count'],
        'space_cleared_mb': stats['space_cleared_mb'],
        'remaining': stats['remaining'],
        'total': stats['total'],
    })


@login_required
@require_POST
def undo_decision(request, session_id):
    session = get_object_or_404(CullSession, pk=session_id, user=request.user)
    last_decision = (
        SwipeDecision.objects.filter(session=session, user=request.user)
        .select_related('media_file')
        .order_by('-decided_at', '-id')
        .first()
    )
    if not last_decision:
        return JsonResponse({'ok': False, 'error': 'Nothing to undo.'}, status=400)

    restored_file = _serialize_media_file(last_decision.media_file)
    last_decision.delete()

    if session.status == 'completed':
        session.status = 'active'
        session.completed_at = None
        session.save(update_fields=['status', 'completed_at'])

    stats = _session_stats(session, request.user)
    return JsonResponse({
        'ok': True,
        'restored_photo': restored_file,
        'session_status': session.status,
        'kept_count': stats['kept_count'],
        'trashed_count': stats['trashed_count'],
        'space_cleared_mb': stats['space_cleared_mb'],
        'remaining': stats['remaining'],
        'total': stats['total'],
    })


@login_required
@require_POST
def finalize_session(request, session_id):
    session = get_object_or_404(CullSession, pk=session_id, user=request.user)
    trashed_decisions = SwipeDecision.objects.filter(
        session=session,
        user=request.user,
        decision='trash',
    ).select_related('media_file')

    trashed_files = [d.media_file for d in trashed_decisions]
    use_drive = is_real_connection(session.drive_connection)
    trashed_to_delete = []
    drive_errors = []

    for mf in trashed_files:
        if use_drive and not mf.drive_file_id.startswith('demo-'):
            try:
                trash_drive_file(session.drive_connection, mf.drive_file_id)
                trashed_to_delete.append(mf)
            except DriveAPIError as exc:
                drive_errors.append(f'{mf.file_name}: {exc}')
        else:
            trashed_to_delete.append(mf)

    deleted_count = len(trashed_to_delete)
    freed_mb = round(
        sum(float(mf.file_size_mb) for mf in trashed_to_delete if mf.file_size_mb is not None),
        2,
    )

    if trashed_to_delete:
        MediaFile.objects.filter(id__in=[mf.id for mf in trashed_to_delete]).delete()

    stats = _session_stats(session, request.user)
    session.total_files = stats['total']
    update_fields = ['total_files']
    if stats['remaining'] == 0 and session.status != 'completed':
        session.status = 'completed'
        session.completed_at = timezone.now()
        update_fields.extend(['status', 'completed_at'])
    session.save(update_fields=update_fields)

    return JsonResponse({
        'ok': True,
        'deleted_count': deleted_count,
        'freed_mb': freed_mb,
        'drive_synced': use_drive,
        'drive_errors': drive_errors,
        'session_status': session.status,
        'kept_count': stats['kept_count'],
        'trashed_count': stats['trashed_count'],
        'space_cleared_mb': stats['space_cleared_mb'],
        'remaining': stats['remaining'],
        'total': stats['total'],
    })


def _filtered_decisions(request):
    """Return user's SwipeDecisions joined with MediaFile & CullSession, filtered by GET params."""
    decisions = (
        SwipeDecision.objects.filter(user=request.user)
        .select_related('media_file', 'session')
        .order_by('-decided_at', '-id')
    )
    decision_filter = request.GET.get('decision', '').strip()
    session_filter = request.GET.get('session', '').strip()
    query = request.GET.get('q', '').strip()

    if decision_filter in ('keep', 'trash'):
        decisions = decisions.filter(decision=decision_filter)
    if session_filter.isdigit():
        decisions = decisions.filter(session_id=int(session_filter))
    if query:
        decisions = decisions.filter(media_file__file_name__icontains=query)

    return decisions, {
        'decision': decision_filter,
        'session': session_filter,
        'q': query,
    }


@login_required
def decision_log(request):
    """JOIN implementation: retrieve SwipeDecisions joined with MediaFile and CullSession."""
    decisions, filters = _filtered_decisions(request)
    summary = decisions.aggregate(
        total=Count('id'),
        kept=Count('id', filter=Q(decision='keep')),
        trashed=Count('id', filter=Q(decision='trash')),
        trashed_mb=Coalesce(
            Sum('media_file__file_size_mb', filter=Q(decision='trash')),
            Decimal('0.00'),
        ),
    )
    user_sessions = CullSession.objects.filter(user=request.user).order_by('-created_at')
    return render(
        request,
        'home/decision_log.html',
        {
            'decisions': decisions,
            'summary': summary,
            'user_sessions': user_sessions,
            'filters': filters,
            'generated_sql': str(decisions.query),
        },
    )


@login_required
def export_decisions_csv(request):
    """Export filtered SwipeDecisions as a CSV file."""
    decisions, _ = _filtered_decisions(request)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="swipecull_decisions.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID', 'File Name', 'Type', 'Size (MB)', 'Session Folder', 'Decision', 'Decided At'])
    for d in decisions:
        writer.writerow([
            d.id,
            d.media_file.file_name,
            d.media_file.get_file_type_display(),
            f'{d.media_file.file_size_mb:.2f}' if d.media_file.file_size_mb is not None else '',
            d.session.folder_name,
            d.get_decision_display(),
            d.decided_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])
    return response


@login_required
def sessions_with_decisions(request):
    """SUBQUERY implementation: retrieve active CullSessions that have at least one SwipeDecision."""
    session_ids = SwipeDecision.objects.filter(user=request.user).values('session_id')
    sessions = (
        CullSession.objects.filter(
            user=request.user,
            status='active',
            id__in=Subquery(session_ids),
        )
        .select_related('drive_connection')
        .order_by('-created_at')
    )
    return render(
        request,
        'home/sessions_with_decisions.html',
        {
            'sessions': sessions,
            'generated_sql': str(sessions.query),
        },
    )


@login_required
def analytics_view(request):
    """Aggregate storage, keep/trash ratios, and per-session progress for the user."""
    sessions = list(
        CullSession.objects.filter(user=request.user)
        .select_related('drive_connection')
        .annotate(
            kept_count=Count('swipe_decisions', filter=Q(swipe_decisions__decision='keep')),
            trashed_count=Count('swipe_decisions', filter=Q(swipe_decisions__decision='trash')),
            decided_count=Count('swipe_decisions'),
            trashed_mb=Coalesce(
                Sum(
                    'swipe_decisions__media_file__file_size_mb',
                    filter=Q(swipe_decisions__decision='trash'),
                ),
                Decimal('0.00'),
            ),
        )
        .order_by('-created_at')
    )

    total_kept = sum(s.kept_count for s in sessions)
    total_trashed = sum(s.trashed_count for s in sessions)
    total_decided = total_kept + total_trashed
    total_trashed_mb = sum((s.trashed_mb for s in sessions), Decimal('0.00'))
    keep_rate = round((total_kept / total_decided) * 100) if total_decided else 0

    for s in sessions:
        s.progress_pct = min(100, round((s.decided_count / s.total_files) * 100)) if s.total_files else 0

    overview = {
        'total_sessions': len(sessions),
        'active_sessions': sum(1 for s in sessions if s.status == 'active'),
        'completed_sessions': sum(1 for s in sessions if s.status == 'completed'),
        'total_kept': total_kept,
        'total_trashed': total_trashed,
        'total_decided': total_decided,
        'keep_rate': keep_rate,
        'trash_rate': 100 - keep_rate if total_decided else 0,
        'total_trashed_mb': total_trashed_mb,
    }

    return render(
        request,
        'home/analytics.html',
        {
            'sessions': sessions,
            'overview': overview,
        },
    )


def _get_google_redirect_uri(request):
    configured = getattr(settings, 'GOOGLE_REDIRECT_URI', '')
    return configured or request.build_absolute_uri(reverse('google_drive_callback'))


@login_required
def google_drive_connect(request):
    """Redirect the user to Google OAuth consent screen for Drive access."""
    if not is_google_oauth_configured():
        messages.warning(
            request,
            'Google Drive OAuth is not configured yet. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.',
        )
        return redirect('home')

    state = secrets.token_urlsafe(24)
    request.session['google_oauth_state'] = state
    auth_url = build_auth_url(_get_google_redirect_uri(request), state)
    return redirect(auth_url)


@login_required
def google_drive_callback(request):
    """Handle Google OAuth2 callback and persist tokens in DriveConnection."""
    error = request.GET.get('error')
    if error:
        messages.error(request, f'Google Drive authorization was cancelled or failed ({error}).')
        return redirect('home')

    expected_state = request.session.pop('google_oauth_state', None)
    received_state = request.GET.get('state')
    if not expected_state or expected_state != received_state:
        messages.error(request, 'Invalid OAuth state parameter. Please try connecting Google Drive again.')
        return redirect('home')

    code = request.GET.get('code')
    if not code:
        messages.error(request, 'Missing authorization code from Google.')
        return redirect('home')

    try:
        tokens = exchange_code_for_tokens(code, _get_google_redirect_uri(request))
    except DriveAPIError as exc:
        messages.error(request, f'Failed to connect Google Drive: {exc}')
        return redirect('home')

    expires_in = int(tokens.get('expires_in', 3600))
    expiry = timezone.now() + timedelta(seconds=expires_in)

    existing = DriveConnection.objects.filter(user=request.user, provider='google_drive').first()
    refresh_token = tokens.get('refresh_token') or (existing.refresh_token if existing else '')

    DriveConnection.objects.update_or_create(
        user=request.user,
        provider='google_drive',
        defaults={
            'access_token': tokens['access_token'],
            'refresh_token': refresh_token,
            'token_expiry': expiry,
            'is_active': True,
        },
    )
    messages.success(request, 'Google Drive connected! Click "+ New" to import a Drive folder.')
    return redirect('home')


@login_required
@require_POST
def google_drive_disconnect(request):
    """Disconnect the user's Google Drive OAuth tokens."""
    DriveConnection.objects.filter(user=request.user, provider='google_drive').update(
        is_active=False,
        access_token='',
        refresh_token='',
        token_expiry=None,
    )
    messages.info(request, 'Google Drive disconnected.')
    return redirect('home')


@login_required
def google_drive_folders(request):
    """Return the user's Google Drive folders as JSON for the folder picker."""
    connection = DriveConnection.objects.filter(
        user=request.user,
        provider='google_drive',
        is_active=True,
    ).first()
    if not is_real_connection(connection):
        return JsonResponse({'ok': False, 'error': 'Google Drive is not connected.'}, status=400)

    try:
        folders = list_drive_folders(connection)
    except DriveAPIError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)

    return JsonResponse({'ok': True, 'folders': folders})


@login_required
def drive_file_preview(request, media_file_id):
    """Proxy an image preview from Google Drive using the user's OAuth token."""
    media_file = get_object_or_404(MediaFile, pk=media_file_id, session__user=request.user)
    if media_file.drive_file_id.startswith('demo-') and media_file.thumbnail_url:
        return redirect(media_file.thumbnail_url)

    connection = media_file.session.drive_connection
    if not is_real_connection(connection):
        return HttpResponse('Google Drive connection is not active.', status=401)

    try:
        content, content_type = fetch_drive_file_preview(connection, media_file.drive_file_id)
    except DriveAPIError as exc:
        return HttpResponse(str(exc), status=502)

    response = HttpResponse(content, content_type=content_type)
    response['Cache-Control'] = 'private, max-age=300'
    return response
