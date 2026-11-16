import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

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
