import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import CullSession, DriveConnection, MediaFile, SwipeDecision


class HomeSwipeFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='secret')
        self.other = User.objects.create_user(username='bob', password='secret')
        self.conn = DriveConnection.objects.create(user=self.user, access_token='demo')
        self.session = CullSession.objects.create(
            user=self.user,
            drive_connection=self.conn,
            folder_name='Trip Photos',
            folder_id='trip-1',
            total_files=2,
        )
        self.file1 = MediaFile.objects.create(
            session=self.session,
            drive_file_id='f-1',
            file_name='IMG_01.jpg',
            file_size_mb='4.00',
            width=4000,
            height=3000,
        )
        self.file2 = MediaFile.objects.create(
            session=self.session,
            drive_file_id='f-2',
            file_name='IMG_02.jpg',
            file_size_mb='2.50',
            width=3000,
            height=3000,
        )

    def test_home_renders_active_session_data(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('home'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['active_session'], self.session)
        self.assertEqual(resp.context['session_data']['total'], 2)
        self.assertEqual(len(resp.context['session_data']['photos']), 2)

    def test_other_user_cannot_access_session(self):
        self.client.force_login(self.other)
        resp = self.client.get(reverse('session_detail', args=[self.session.id]))
        self.assertEqual(resp.status_code, 404)

    def test_decide_completes_session_and_undo_reopens_it(self):
        self.client.force_login(self.user)

        r1 = self.client.post(
            reverse('decide_file', args=[self.session.id]),
            data=json.dumps({'media_file_id': self.file1.id, 'decision': 'keep'}),
            content_type='application/json',
        )
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        self.assertEqual(d1['kept_count'], 1)
        self.assertEqual(d1['remaining'], 1)
        self.assertEqual(d1['session_status'], 'active')

        r2 = self.client.post(
            reverse('decide_file', args=[self.session.id]),
            data=json.dumps({'media_file_id': self.file2.id, 'decision': 'trash'}),
            content_type='application/json',
        )
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertEqual(d2['trashed_count'], 1)
        self.assertEqual(d2['space_cleared_mb'], 2.5)
        self.assertEqual(d2['remaining'], 0)
        self.assertEqual(d2['session_status'], 'completed')

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'completed')

        r_undo = self.client.post(reverse('undo_decision', args=[self.session.id]))
        self.assertEqual(r_undo.status_code, 200)
        du = r_undo.json()
        self.assertEqual(du['restored_photo']['id'], self.file2.id)
        self.assertEqual(du['trashed_count'], 0)
        self.assertEqual(du['remaining'], 1)
        self.assertEqual(du['session_status'], 'active')
        self.assertEqual(SwipeDecision.objects.filter(session=self.session).count(), 1)

    def test_finalize_session_deletes_trashed_files(self):
        self.client.force_login(self.user)
        SwipeDecision.objects.create(
            media_file=self.file1, session=self.session, user=self.user, decision='keep'
        )
        SwipeDecision.objects.create(
            media_file=self.file2, session=self.session, user=self.user, decision='trash'
        )

        resp = self.client.post(reverse('finalize_session', args=[self.session.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['deleted_count'], 1)
        self.assertEqual(data['freed_mb'], 2.5)
        self.assertEqual(data['kept_count'], 1)
        self.assertEqual(data['trashed_count'], 0)
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['session_status'], 'completed')

        self.session.refresh_from_db()
        self.assertEqual(self.session.total_files, 1)
        self.assertEqual(self.session.status, 'completed')
        self.assertFalse(MediaFile.objects.filter(pk=self.file2.id).exists())
        self.assertTrue(MediaFile.objects.filter(pk=self.file1.id).exists())

    def test_create_session_populates_files_and_redirects(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse('create_session'),
            data={'folder_name': 'Weekend Hike', 'count': 6},
        )
        self.assertEqual(resp.status_code, 302)
        created = CullSession.objects.get(user=self.user, folder_name='Weekend Hike')
        self.assertEqual(created.total_files, 6)
        self.assertEqual(created.media_files.count(), 6)
        self.assertRedirects(resp, reverse('session_detail', args=[created.id]))

    def test_decision_log_join_view(self):
        SwipeDecision.objects.create(
            media_file=self.file1, session=self.session, user=self.user, decision='keep'
        )
        other_conn = DriveConnection.objects.create(user=self.other, access_token='other-demo')
        other_session = CullSession.objects.create(
            user=self.other, drive_connection=other_conn, folder_name='Other Folder', folder_id='other-1'
        )
        other_file = MediaFile.objects.create(
            session=other_session, drive_file_id='other-f-1', file_name='OTHER.jpg'
        )
        SwipeDecision.objects.create(
            media_file=other_file, session=other_session, user=self.other, decision='trash'
        )

        self.client.force_login(self.user)
        resp = self.client.get(reverse('decision_log'))
        self.assertEqual(resp.status_code, 200)
        decisions = list(resp.context['decisions'])
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].media_file.file_name, 'IMG_01.jpg')
        self.assertEqual(decisions[0].session.folder_name, 'Trip Photos')
        sql = resp.context['generated_sql']
        self.assertIn('JOIN', sql.upper())
        self.assertIn('media_file', sql)
        self.assertIn('cull_session', sql)

    def test_sessions_with_decisions_subquery_view(self):
        empty_session = CullSession.objects.create(
            user=self.user,
            drive_connection=self.conn,
            folder_name='Empty Session',
            folder_id='empty-1',
            status='active',
        )
        completed_session = CullSession.objects.create(
            user=self.user,
            drive_connection=self.conn,
            folder_name='Completed Session',
            folder_id='comp-1',
            status='completed',
        )
        comp_file = MediaFile.objects.create(
            session=completed_session, drive_file_id='comp-f-1', file_name='COMP.jpg'
        )
        SwipeDecision.objects.create(
            media_file=self.file1, session=self.session, user=self.user, decision='keep'
        )
        SwipeDecision.objects.create(
            media_file=comp_file, session=completed_session, user=self.user, decision='keep'
        )

        self.client.force_login(self.user)
        resp = self.client.get(reverse('sessions_with_decisions'))
        self.assertEqual(resp.status_code, 200)
        sessions = list(resp.context['sessions'])
        self.assertEqual(sessions, [self.session])
        self.assertNotIn(empty_session, sessions)
        self.assertNotIn(completed_session, sessions)
        sql = resp.context['generated_sql']
        self.assertIn('IN (SELECT', sql.upper())
        self.assertIn('swipe_decision', sql)

    def test_decision_log_filtering_summary_and_csv_export(self):
        SwipeDecision.objects.create(
            media_file=self.file1, session=self.session, user=self.user, decision='keep'
        )
        SwipeDecision.objects.create(
            media_file=self.file2, session=self.session, user=self.user, decision='trash'
        )
        self.client.force_login(self.user)

        resp = self.client.get(reverse('decision_log'), {'decision': 'trash', 'q': 'IMG_02'})
        self.assertEqual(resp.status_code, 200)
        decisions = list(resp.context['decisions'])
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].media_file.file_name, 'IMG_02.jpg')
        self.assertEqual(resp.context['summary']['trashed'], 1)
        self.assertEqual(resp.context['summary']['kept'], 0)
        self.assertEqual(float(resp.context['summary']['trashed_mb']), 2.5)

        csv_resp = self.client.get(reverse('export_decisions_csv'), {'decision': 'keep'})
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp['Content-Type'], 'text/csv')
        body = csv_resp.content.decode('utf-8')
        self.assertIn('IMG_01.jpg', body)
        self.assertNotIn('IMG_02.jpg', body)

    def test_analytics_view_aggregations(self):
        SwipeDecision.objects.create(
            media_file=self.file1, session=self.session, user=self.user, decision='keep'
        )
        SwipeDecision.objects.create(
            media_file=self.file2, session=self.session, user=self.user, decision='trash'
        )
        self.client.force_login(self.user)
        resp = self.client.get(reverse('analytics'))
        self.assertEqual(resp.status_code, 200)
        overview = resp.context['overview']
        self.assertEqual(overview['total_sessions'], 1)
        self.assertEqual(overview['total_kept'], 1)
        self.assertEqual(overview['total_trashed'], 1)
        self.assertEqual(overview['keep_rate'], 50)
        self.assertEqual(float(overview['total_trashed_mb']), 2.5)

    def test_create_session_with_provider_and_delete_session(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse('create_session'),
            data={'folder_name': 'Dropbox Backup', 'provider': 'dropbox', 'count': 4},
        )
        self.assertEqual(resp.status_code, 302)
        created = CullSession.objects.get(user=self.user, folder_name='Dropbox Backup')
        self.assertEqual(created.drive_connection.provider, 'dropbox')
        self.assertEqual(created.total_files, 4)

        # Other user cannot delete this session
        self.client.force_login(self.other)
        forbidden = self.client.post(reverse('delete_session', args=[created.id]))
        self.assertEqual(forbidden.status_code, 404)
        self.assertTrue(CullSession.objects.filter(pk=created.id).exists())

        # Owner can delete and redirect back to analytics
        self.client.force_login(self.user)
        deleted = self.client.post(
            reverse('delete_session', args=[created.id]),
            data={'next': reverse('analytics')},
        )
        self.assertRedirects(deleted, reverse('analytics'))
        self.assertFalse(CullSession.objects.filter(pk=created.id).exists())

    def test_home_renders_shortcuts_modal_and_analytics_link(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('home'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'shortcuts-modal')
        self.assertContains(resp, reverse('analytics'))

    def test_profile_and_settings_render_unified_nav_and_favicon(self):
        self.client.force_login(self.user)
        for url_name in ('profile', 'user_settings'):
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, reverse('analytics'))
            self.assertContains(resp, reverse('decision_log'))
            self.assertContains(resp, 'rel="icon"')


class GoogleDriveIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='secret')
        self.other = User.objects.create_user(username='bob', password='secret')
        self.client.force_login(self.user)

    @override_settings(GOOGLE_CLIENT_ID='', GOOGLE_CLIENT_SECRET='')
    def test_connect_warns_when_oauth_not_configured(self):
        resp = self.client.get(reverse('google_drive_connect'), follow=True)
        self.assertEqual(resp.status_code, 200)
        messages_list = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('not configured' in m for m in messages_list))

    @override_settings(
        GOOGLE_CLIENT_ID='test-client-id',
        GOOGLE_CLIENT_SECRET='test-client-secret',
        GOOGLE_REDIRECT_URI='http://localhost:8000/drive/callback/',
    )
    def test_connect_redirects_to_google_and_callback_saves_tokens(self):
        connect_resp = self.client.get(reverse('google_drive_connect'))
        self.assertEqual(connect_resp.status_code, 302)
        self.assertIn('accounts.google.com/o/oauth2/v2/auth', connect_resp['Location'])
        state = self.client.session['google_oauth_state']

        mock_token_resp = MagicMock(ok=True, status_code=200)
        mock_token_resp.json.return_value = {
            'access_token': 'real-access-token',
            'refresh_token': 'real-refresh-token',
            'expires_in': 3600,
        }
        with patch('apps.home.drive_service.requests.post', return_value=mock_token_resp) as mock_post:
            cb_resp = self.client.get(
                reverse('google_drive_callback'),
                {'code': 'auth-code-123', 'state': state},
            )

        self.assertRedirects(cb_resp, reverse('home'))
        mock_post.assert_called_once()
        conn = DriveConnection.objects.get(user=self.user, provider='google_drive')
        self.assertTrue(conn.is_active)
        self.assertEqual(conn.access_token, 'real-access-token')
        self.assertEqual(conn.refresh_token, 'real-refresh-token')

    def test_callback_rejects_invalid_state(self):
        session = self.client.session
        session['google_oauth_state'] = 'expected-state'
        session.save()

        resp = self.client.get(
            reverse('google_drive_callback'),
            {'code': 'abc', 'state': 'wrong-state'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(DriveConnection.objects.filter(user=self.user).exists())

    @override_settings(GOOGLE_CLIENT_ID='cid', GOOGLE_CLIENT_SECRET='csec')
    def test_folders_endpoint_refreshes_expired_token(self):
        conn = DriveConnection.objects.create(
            user=self.user,
            provider='google_drive',
            access_token='expired-token',
            refresh_token='refresh-123',
            token_expiry=timezone.now() - timedelta(minutes=5),
            is_active=True,
        )

        mock_refresh = MagicMock(ok=True, status_code=200)
        mock_refresh.json.return_value = {'access_token': 'new-token', 'expires_in': 3600}

        mock_folders = MagicMock(ok=True, status_code=200)
        mock_folders.json.return_value = {
            'files': [{'id': 'fld-1', 'name': 'Vacation 2026', 'modifiedTime': '2026-07-01T10:00:00Z'}]
        }

        with (
            patch('apps.home.drive_service.requests.post', return_value=mock_refresh),
            patch('apps.home.drive_service.requests.get', return_value=mock_folders) as mock_get,
        ):
            resp = self.client.get(reverse('google_drive_folders'))

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['folders'][0]['id'], 'root')
        self.assertEqual(data['folders'][1]['name'], 'Vacation 2026')
        conn.refresh_from_db()
        self.assertEqual(conn.access_token, 'new-token')
        self.assertEqual(mock_get.call_args.kwargs['headers']['Authorization'], 'Bearer new-token')

    def test_create_session_from_google_drive_and_preview_and_finalize_trash(self):
        conn = DriveConnection.objects.create(
            user=self.user,
            provider='google_drive',
            access_token='valid-token',
            refresh_token='refresh-123',
            token_expiry=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        mock_files_resp = MagicMock(ok=True, status_code=200)
        mock_files_resp.json.return_value = {
            'files': [
                {
                    'id': 'gd-file-1',
                    'name': 'beach.jpg',
                    'mimeType': 'image/jpeg',
                    'size': str(3 * 1024 * 1024),
                    'imageMediaMetadata': {'width': 1920, 'height': 1080, 'time': '2026:07:01 12:30:00'},
                    'createdTime': '2026-07-01T12:30:00Z',
                    'thumbnailLink': 'https://lh3.googleusercontent.com/thumb1',
                },
                {
                    'id': 'gd-file-2',
                    'name': 'blurry.jpg',
                    'mimeType': 'image/jpeg',
                    'size': str(2 * 1024 * 1024),
                    'imageMediaMetadata': {'width': 1200, 'height': 900},
                    'createdTime': '2026-07-01T12:31:00Z',
                },
            ]
        }

        with patch('apps.home.drive_service.requests.get', return_value=mock_files_resp):
            create_resp = self.client.post(
                reverse('create_session'),
                {
                    'source': 'google_drive',
                    'drive_folder_id': 'fld-1',
                    'drive_folder_name': 'Vacation 2026',
                },
            )

        session = CullSession.objects.get(user=self.user, folder_id='fld-1')
        self.assertRedirects(create_resp, reverse('session_detail', args=[session.id]))
        self.assertEqual(session.folder_name, 'Vacation 2026')
        self.assertEqual(session.total_files, 2)

        detail_resp = self.client.get(reverse('session_detail', args=[session.id]))
        photos = detail_resp.context['session_data']['photos']
        self.assertEqual(len(photos), 2)
        self.assertTrue(photos[0]['src'].startswith('/drive/file/'))

        mf_trash = MediaFile.objects.get(drive_file_id='gd-file-2')
        mock_preview = MagicMock(ok=True, status_code=200, content=b'jpeg-bytes', headers={'Content-Type': 'image/jpeg'})
        with patch('apps.home.drive_service.requests.get', return_value=mock_preview):
            preview_resp = self.client.get(reverse('drive_file_preview', args=[mf_trash.id]))
        self.assertEqual(preview_resp.status_code, 200)
        self.assertEqual(preview_resp.content, b'jpeg-bytes')

        self.client.force_login(self.other)
        forbidden_preview = self.client.get(reverse('drive_file_preview', args=[mf_trash.id]))
        self.assertEqual(forbidden_preview.status_code, 404)

        self.client.force_login(self.user)
        SwipeDecision.objects.create(media_file=mf_trash, session=session, user=self.user, decision='trash')
        mock_patch = MagicMock(ok=True, status_code=200)
        with patch('apps.home.drive_service.requests.patch', return_value=mock_patch) as patch_call:
            fin_resp = self.client.post(reverse('finalize_session', args=[session.id]))

        self.assertEqual(fin_resp.status_code, 200)
        fin_data = fin_resp.json()
        self.assertTrue(fin_data['drive_synced'])
        self.assertEqual(fin_data['deleted_count'], 1)
        self.assertEqual(fin_data['drive_errors'], [])
        patch_call.assert_called_once()
        self.assertIn('gd-file-2', patch_call.call_args.args[0])
        self.assertEqual(patch_call.call_args.kwargs['json'], {'trashed': True})
        self.assertFalse(MediaFile.objects.filter(pk=mf_trash.id).exists())

        disc_resp = self.client.post(reverse('google_drive_disconnect'))
        self.assertRedirects(disc_resp, reverse('home'))
        conn.refresh_from_db()
        self.assertFalse(conn.is_active)
        self.assertEqual(conn.access_token, '')
