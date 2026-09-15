import copy
import json
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import patch

from backend.courseplatform import actions as a


NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)


class Result:
    def __init__(self, rows=()):
        self.rows = copy.deepcopy(list(rows))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class CertificateDB:
    def __init__(self):
        self.cert = {
            'certificate_id': 'CERT1', 'student_id': 'S1', 'course_id': 'C1',
            'certificate_number': 'LSS-2026-TEST123456', 'certificate_type': 'SIMPLE',
            'status': 'ISSUED', 'download_count': 0, 'max_downloads': None,
            'template_snapshot_json': {'version': 1, 'profile': {'issuerName': 'Original'}},
        }
        self.profile = {'participation': a.normalize_participation_policy()}
        self.requests = []
        self.calls = []
        self.course = {'course_id': 'C1', 'title': 'Curso de teste'}
        self.enrollment = {'enrollment_id': 'E1', 'student_id': 'S1', 'course_id': 'C1',
                           'status': 'COMPLETED', 'progress_percent': 100}
        self.student = {'student_id': 'S1', 'full_name': 'Estudante de Teste'}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        pass

    def execute(self, sql, params=()):
        sql = ' '.join(sql.split()).lower()
        assert sql.count('%s') == len(params), (sql, params)
        self.calls.append((sql, params))
        if sql.startswith('select enrollment_id'):
            return Result([self.enrollment])
        if sql.startswith('select * from courseplatform.certificate_settings'):
            return Result([{'course_id': 'C1', 'certificate_profile_json': self.profile}])
        if sql.startswith('select * from courseplatform.courses'):
            return Result([self.course])
        if sql.startswith('select * from courseplatform.students'):
            return Result([self.student])
        if sql.startswith('select') and 'from courseplatform.certificates' in sql:
            if not self.cert:
                return Result()
            if 'cert.student_id = %s and cert.course_id' in sql:
                return Result([self.cert])
            if 'student_id = %s' in sql and params[-1] != 'S1':
                return Result()
            return Result([self.cert])
        if sql.startswith('insert into courseplatform.certificates'):
            self.cert = {'certificate_id': params[0], 'student_id': params[1], 'course_id': params[2],
                         'certificate_type': 'SIMPLE', 'status': 'ISSUED', 'download_count': 0,
                         'max_downloads': None, 'template_snapshot_json': json.loads(params[-1])}
            return Result([self.cert])
        if sql.startswith('select * from courseplatform.certificate_requests'):
            if 'request_id = %s' in sql:
                return Result([r for r in self.requests if r['request_id'] == params[0]])
            return Result([r for r in self.requests if r['status'] == 'PAYMENT_SUBMITTED'])
        if sql.startswith('insert into courseplatform.certificate_requests'):
            request = {'request_id': params[0], 'student_id': params[1], 'course_id': params[2],
                       'request_type': 'PARTICIPATION', 'status': 'PAYMENT_SUBMITTED'}
            self.requests.append(request)
            return Result([request])
        if sql.startswith('update courseplatform.certificates'):
            if 'download_count = download_count + 1' in sql:
                self.cert['download_count'] += 1
            elif "status = 'issued'" in sql:
                self.cert.update(status='ISSUED', approved_by=params[0], approved_at=NOW, download_count=0)
            else:
                self.cert['status'] = params[0]
                if params[0] == 'ISSUED':
                    self.cert.update(approved_by=params[4], approved_at=NOW)
                if params[6]:
                    self.cert['download_count'] = 0
            return Result([self.cert])
        if sql.startswith('update courseplatform.certificate_requests'):
            request = next(r for r in self.requests if r['request_id'] == params[-1])
            if "status = 'approved'" in sql:
                request.update(status='APPROVED', certificate_id=params[0])
            else:
                request['status'] = 'REJECTED'
            return Result([request])
        if sql.startswith('insert into courseplatform.certificate_settings'):
            self.profile = json.loads(params[6])
            return Result([{'course_id': params[0], 'certificate_profile_json': self.profile}])
        raise AssertionError(f'Unexpected query: {sql}')


class ParticipationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.db = CertificateDB()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in {
            'connection': self.db,
            'student_context': ({}, self.db.student),
            'admin_context': ({}, {'admin_id': 'ADMIN1', 'role': 'OWNER'}),
            'utc_now': NOW,
            'ensure_certificate_feature_schema': None,
            'audit': None,
            'course_completion_snapshot': (self.db.enrollment, self.db.course, 1, 1, True),
            'sync_enrollment_completion': self.db.enrollment,
            'certificate_content_summary': 'Conteudo',
            'certificate_template_snapshot': {'profile': {'issuerName': 'Original'}},
        }.items():
            self.stack.enter_context(patch.object(a, name, return_value=value))

    def assert_code(self, code, function, *args):
        with self.assertRaises(a.ApiError) as error:
            function(*args)
        self.assertEqual(error.exception.code, code)

    def test_legacy_defaults_preserve_free_unlimited_access(self):
        policy = a.normalize_participation_policy()
        self.assertTrue(policy['enabled'])
        self.assertEqual(policy['releaseMode'], 'automatic')
        self.assertIsNone(policy['maxDownloads'])
        self.assertTrue(a.certificate_download_access(self.db.cert, policy)['allowed'])

    def test_invalid_policy_is_rejected(self):
        for value in [-1, 0, 1.5, True, 'two', 1001]:
            with self.subTest(limit=value):
                self.assert_code('INVALID_CERTIFICATE_POLICY', a.normalize_participation_policy, {'maxDownloads': value})
        for policy in [{'releaseMode': 'anything'}, {'availableFrom': 'bad'},
                       {'availableUntil': '2026-10-01T10:00'},
                       {'availableFrom': '2026-10-01T12:00Z', 'availableUntil': '2026-10-01T10:00Z'}]:
            self.assert_code('INVALID_CERTIFICATE_POLICY', a.normalize_participation_policy, policy)

    def test_dates_normalize_timezones(self):
        policy = a.normalize_participation_policy({'availableFrom': '2026-09-12T14:00:00+02:00'})
        self.assertEqual(policy['availableFrom'], NOW.isoformat())
        self.assertTrue(a.certificate_download_access(self.db.cert, policy)['allowed'])

    def test_window_start_and_end_are_enforced(self):
        for policy, code in [({'availableFrom': '2026-09-13T12:00Z'}, 'CERTIFICATE_NOT_YET_AVAILABLE'),
                             ({'availableUntil': NOW.isoformat()}, 'CERTIFICATE_WINDOW_CLOSED')]:
            self.assertEqual(a.certificate_download_access(self.db.cert, policy)['code'], code)

    def test_disabled_prevents_issuance_and_hides_existing_certificate(self):
        self.db.profile['participation']['enabled'] = False
        result = a.ensure_simple_certificate(self.db, self.db.student, 'C1')
        self.assertIsNone(result[0])
        self.assertTrue(result[3])  # Professional eligibility is independent.
        self.assertIsNone(a.my_certificate({'courseId': 'C1'})['data']['certificate'])
        self.assertFalse(any(sql.startswith('insert into courseplatform.certificates') for sql, _ in self.db.calls))

    def test_deleted_certificate_is_not_automatically_recreated(self):
        self.db.cert['status'] = 'DELETED'
        self.assertEqual(a.ensure_simple_certificate(self.db, self.db.student, 'C1')[0]['status'], 'DELETED')
        self.assertIsNone(a.my_certificate({'courseId': 'C1'})['data']['certificate'])

    def test_first_issuance_is_serialized(self):
        self.db.cert = None
        self.assertIsNotNone(a.ensure_simple_certificate(self.db, self.db.student, 'C1')[0])
        self.assertIn('for update', self.db.calls[0][0])

    def test_approval_required_for_existing_certificate(self):
        policy = {'releaseMode': 'approval'}
        self.assertEqual(a.certificate_download_access(self.db.cert, policy)['code'], 'CERTIFICATE_APPROVAL_REQUIRED')
        self.db.cert['approved_at'] = NOW
        self.assertTrue(a.certificate_download_access(self.db.cert, policy)['allowed'])

    def test_blocked_status_wins_after_approval(self):
        self.db.cert.update(status='BLOCKED', approved_at=NOW)
        self.assertEqual(a.certificate_download_access(self.db.cert, {'releaseMode': 'approval'})['code'], 'CERTIFICATE_ACCESS_BLOCKED')

    def test_professional_unaffected_by_participation_policy(self):
        self.db.cert.update(certificate_type='PROFESSIONAL', max_downloads=5)
        self.assertTrue(a.certificate_download_access(self.db.cert, {'enabled': False})['allowed'])

    def test_download_limit_enforced_at_both_server_entrypoints(self):
        self.db.profile['participation']['maxDownloads'] = 1
        a.record_certificate_download({'certificateId': 'CERT1'})
        self.assertEqual(self.db.cert['download_count'], 1)
        self.assertIn('for update', self.db.calls[0][0])
        self.assert_code('DOWNLOAD_LIMIT_REACHED', a.record_certificate_download, {'certificateId': 'CERT1'})
        self.assert_code('DOWNLOAD_LIMIT_REACHED', a.certificate_pdf_payload, {'certificateId': 'CERT1'})
        self.assertEqual(self.db.cert['download_count'], 1)

    def test_student_and_admin_pdf_payloads_share_the_emission_snapshot(self):
        self.db.cert.update(
            course_title='Curso de teste', student_name='Estudante de Teste',
            verification_code='LSS2026TEST123456', issue_date=NOW, final_score=87,
            template_snapshot_json={
                'courseHours': 24,
                'profile': {'issuerName': 'Entidade Original', 'assets': {}},
            },
        )
        student = a.certificate_pdf_payload({'certificateId': 'CERT1', 'verificationBaseUrl': 'https://example.test/verify'})
        admin = a.admin_certificate_pdf_payload({'certificateId': 'CERT1', 'verificationBaseUrl': 'https://example.test/verify'})
        self.assertEqual(student, admin)
        self.assertEqual(student['pdfData']['workload'], '24 horas')
        self.assertEqual(student['pdfData']['issuer_name'], 'Entidade Original')
        self.assertEqual(student['pdfData']['final_score'], 87.0)

    def test_legacy_snapshot_uses_real_course_hours_without_demo_default(self):
        self.db.cert.update(
            course_title='Curso de teste', student_name='Estudante de Teste',
            course_hours=18.5,
        )
        result = a.certificate_pdf_payload({'certificateId': 'CERT1'})
        self.assertEqual(result['pdfData']['workload'], '18,5 horas')

    def test_missing_workload_fails_explicitly(self):
        self.db.cert.update(course_title='Curso de teste', student_name='Estudante de Teste')
        self.assert_code('CERTIFICATE_DATA_INCOMPLETE', a.certificate_pdf_payload, {'certificateId': 'CERT1'})

    def test_disabled_policy_applies_to_previously_issued_pdf(self):
        self.db.profile['participation']['enabled'] = False
        self.assert_code('PARTICIPATION_DISABLED', a.certificate_pdf_payload, {'certificateId': 'CERT1'})
        self.assert_code('PARTICIPATION_DISABLED', a.record_certificate_download, {'certificateId': 'CERT1'})

    def test_foreign_certificate_is_inaccessible(self):
        with patch.object(a, 'student_context', return_value=({}, {'student_id': 'OTHER'})):
            for endpoint in [a.record_certificate_download, a.certificate_pdf_payload]:
                self.assert_code('CERTIFICATE_NOT_FOUND', endpoint, {'certificateId': 'CERT1'})

    def test_hidden_document_does_not_return_snapshot_or_legacy_download_url(self):
        self.db.cert['drive_url'] = 'https://example.org/old.pdf'
        self.db.profile['participation']['releaseMode'] = 'approval'
        cert = a.my_certificate({'courseId': 'C1'})['data']['certificate']
        self.assertEqual(cert['templateSnapshot'], {})
        self.assertEqual(cert['driveUrl'], '')
        self.assertFalse(cert['downloadAccess']['allowed'])

    def test_request_approve_and_download_preserves_certificate_identity(self):
        self.db.profile['participation'].update(releaseMode='approval', maxDownloads=2)
        original = copy.deepcopy(self.db.cert)
        request = a.request_participation_certificate({'courseId': 'C1'})['data']['request']
        again = a.request_participation_certificate({'courseId': 'C1'})['data']['request']
        self.assertEqual(request['requestId'], again['requestId'])
        result = a.admin_review_certificate_request({'requestId': request['requestId'], 'decision': 'APPROVED'})
        self.assertEqual(result['data']['certificate']['certificateType'], 'SIMPLE')
        self.assertEqual(self.db.cert['certificate_id'], original['certificate_id'])
        self.assertEqual(self.db.cert['template_snapshot_json'], original['template_snapshot_json'])
        a.record_certificate_download({'certificateId': 'CERT1'})
        self.assertEqual(self.db.cert['download_count'], 1)
        self.assert_code('CERTIFICATE_REQUEST_ALREADY_REVIEWED', a.admin_review_certificate_request,
                         {'requestId': request['requestId'], 'decision': 'APPROVED'})

    def test_rejection_does_not_grant_access(self):
        self.db.profile['participation']['releaseMode'] = 'approval'
        request = a.request_participation_certificate({'courseId': 'C1'})['data']['request']
        a.admin_review_certificate_request({'requestId': request['requestId'], 'decision': 'REJECTED'})
        self.assert_code('CERTIFICATE_APPROVAL_REQUIRED', a.record_certificate_download, {'certificateId': 'CERT1'})

    def test_disabled_or_incomplete_course_rejects_requests(self):
        self.db.profile['participation']['enabled'] = False
        self.assert_code('PARTICIPATION_DISABLED', a.request_participation_certificate, {'courseId': 'C1'})
        self.db.profile['participation']['enabled'] = True
        with patch.object(a, 'course_completion_snapshot', return_value=(self.db.enrollment, self.db.course, 1, 0, False)):
            self.assert_code('COURSE_NOT_COMPLETED', a.request_participation_certificate, {'courseId': 'C1'})

    def test_admin_can_restore_and_reset_downloads(self):
        self.db.cert.update(status='DELETED', download_count=2)
        a.admin_set_certificate_status({'certificateId': 'CERT1', 'status': 'ISSUED', 'resetDownloads': True})
        self.assertEqual(self.db.cert['status'], 'ISSUED')
        self.assertEqual(self.db.cert['download_count'], 0)
        self.assertEqual(self.db.cert['approved_at'], NOW)

    def test_disabled_course_cannot_be_released_individually(self):
        self.db.profile['participation']['enabled'] = False
        self.assert_code('PARTICIPATION_DISABLED', a.admin_set_certificate_status, {'certificateId': 'CERT1', 'status': 'ISSUED'})

    def test_old_settings_client_does_not_erase_participation_rules(self):
        self.db.profile['participation'].update(enabled=False, maxDownloads=3)
        result = a.admin_save_certificate_settings({'courseId': 'C1', 'certificateProfile': {'issuerName': 'Nova entidade'}})
        profile = result['data']['settings']['certificateProfile']
        self.assertFalse(profile['participation']['enabled'])
        self.assertEqual(profile['participation']['maxDownloads'], 3)
        self.assertEqual(profile['issuerName'], 'Nova entidade')

    def test_policy_roundtrip_does_not_change_issued_snapshot(self):
        snapshot = copy.deepcopy(self.db.cert['template_snapshot_json'])
        policy = {'enabled': False, 'releaseMode': 'approval', 'maxDownloads': 3,
                  'availableFrom': '2026-09-12T12:00:00Z', 'availableUntil': '2026-10-12T12:00:00Z',
                  'instructions': 'Confirme o nome.'}
        a.admin_save_certificate_settings({'courseId': 'C1', 'certificateProfile': {'participation': policy}})
        result = a.admin_get_certificate_settings({'courseId': 'C1'})
        self.assertEqual(result['data']['settings']['certificateProfile']['participation'], a.normalize_participation_policy(policy))
        self.assertEqual(self.db.cert['template_snapshot_json'], snapshot)

    def test_disabling_course_after_request_prevents_approval(self):
        self.db.profile['participation']['releaseMode'] = 'approval'
        request = a.request_participation_certificate({'courseId': 'C1'})['data']['request']
        self.db.profile['participation']['enabled'] = False
        self.assert_code('PARTICIPATION_DISABLED', a.admin_review_certificate_request,
                         {'requestId': request['requestId'], 'decision': 'APPROVED'})
        self.assertEqual(self.db.requests[0]['status'], 'PAYMENT_SUBMITTED')

    def test_individual_release_does_not_bypass_course_window(self):
        self.db.cert['status'] = 'BLOCKED'
        self.db.profile['participation']['availableUntil'] = NOW.isoformat()
        a.admin_set_certificate_status({'certificateId': 'CERT1', 'status': 'ISSUED', 'resetDownloads': True})
        self.assert_code('CERTIFICATE_WINDOW_CLOSED', a.record_certificate_download, {'certificateId': 'CERT1'})

    def test_individual_quota_remains_stricter_than_course_quota(self):
        self.db.cert.update(max_downloads=1, download_count=1)
        access = a.certificate_download_access(self.db.cert, {'maxDownloads': 5})
        self.assertFalse(access['allowed'])
        self.assertEqual(access['maxDownloads'], 1)

    def test_authorization_cannot_be_bypassed_by_payload(self):
        with patch.object(a, 'admin_context', side_effect=a.ApiError('ADMIN_FORBIDDEN', 'Sem permissão.')):
            self.assert_code('ADMIN_FORBIDDEN', a.admin_save_certificate_settings, {'courseId': 'C1'})
            self.assert_code('ADMIN_FORBIDDEN', a.admin_set_certificate_status, {'certificateId': 'CERT1', 'status': 'ISSUED'})


if __name__ == '__main__':
    unittest.main()
