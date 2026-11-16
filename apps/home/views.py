import json
from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

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
    return {
        'id': media_file.id,
        'src': media_file.thumbnail_url or '',
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

    drive_connection = (
        active_session.drive_connection
        if active_session is not None
        else DriveConnection.objects.filter(user=request.user, is_active=True).first()
    )

    return render(
        request,
        'home/home.html',
        {
            'sessions': sessions,
            'active_session': active_session,
            'drive_connection': drive_connection,
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
    folder_name = request.POST.get('folder_name', '').strip() or 'New Photo Session'
    try:
        count = int(request.POST.get('count', 10))
    except (TypeError, ValueError):
        count = 10
    count = max(1, min(count, 30))

    connection, _ = DriveConnection.objects.get_or_create(
        user=request.user,
        provider='google_drive',
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
    deleted_count = len(trashed_files)
    freed_mb = round(
        sum(float(mf.file_size_mb) for mf in trashed_files if mf.file_size_mb is not None),
        2,
    )

    if trashed_files:
        MediaFile.objects.filter(id__in=[mf.id for mf in trashed_files]).delete()

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
        'session_status': session.status,
        'kept_count': stats['kept_count'],
        'trashed_count': stats['trashed_count'],
        'space_cleared_mb': stats['space_cleared_mb'],
        'remaining': stats['remaining'],
        'total': stats['total'],
    })
