import base64
import hashlib
import hmac
import json
import unittest

from backend.courseplatform import actions


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _AccessConnection:
    def __init__(self, allowed=False):
        self.allowed = allowed
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((" ".join(query.split()).lower(), params))
        return _Result({"allowed": True} if self.allowed else None)


class ChatBackendTests(unittest.TestCase):
    def test_chat_message_body_rejects_empty_and_oversized_values(self):
        self.assertEqual(actions.chat_message_body("  Olá, turma.  "), "Olá, turma.")
        with self.assertRaises(actions.ApiError) as empty:
            actions.chat_message_body("  \x00  ")
        self.assertEqual(empty.exception.code, "CHAT_MESSAGE_REQUIRED")
        with self.assertRaises(actions.ApiError) as oversized:
            actions.chat_message_body("a" * 2001)
        self.assertEqual(oversized.exception.code, "CHAT_MESSAGE_TOO_LONG")

    def test_student_access_is_scoped_by_room_type(self):
        conn = _AccessConnection(allowed=True)
        self.assertTrue(actions.student_can_access_chat_room(conn, "STU-1", {"room_type": "COMMUNITY"}))
        self.assertTrue(actions.student_can_access_chat_room(
            conn, "STU-1", {"room_type": "SUPPORT", "owner_student_id": "STU-1"}
        ))
        self.assertFalse(actions.student_can_access_chat_room(
            conn, "STU-1", {"room_type": "SUPPORT", "owner_student_id": "STU-2"}
        ))
        self.assertTrue(actions.student_can_access_chat_room(
            conn, "STU-1", {"room_type": "COURSE", "course_id": "COURSE-1"}
        ))
        self.assertIn("courseplatform.enrollments", conn.queries[-1][0])
        self.assertTrue(actions.student_can_access_chat_room(
            conn,
            "STU-1",
            {"room_type": "DIRECT", "direct_student_one_id": "STU-1", "direct_student_two_id": "STU-2"},
        ))
        self.assertFalse(actions.student_can_access_chat_room(
            conn,
            "STU-3",
            {"room_type": "DIRECT", "direct_student_one_id": "STU-1", "direct_student_two_id": "STU-2"},
        ))

    def test_direct_chat_pair_is_stable_and_rejects_self_chat(self):
        self.assertEqual(actions.chat_direct_pair("STU-9", "STU-2"), ("STU-2", "STU-9"))
        with self.assertRaises(actions.ApiError) as invalid:
            actions.chat_direct_pair("STU-2", "STU-2")
        self.assertEqual(invalid.exception.code, "INVALID_CHAT_CONTACT")

    def test_public_message_hides_removed_content_and_marks_ownership(self):
        actor = {"type": "STUDENT", "id": "STU-1"}
        row = {
            "message_id": "MSG-1",
            "room_id": "ROOM-1",
            "sender_type": "STUDENT",
            "sender_student_id": "STU-1",
            "student_name": "Ana Teste",
            "public_student_id": "STU-2026-01",
            "body": "conteúdo que não deve ser exposto",
            "status": "DELETED",
            "report_count": 0,
        }
        message = actions.public_chat_message(row, actor)
        self.assertTrue(message["isMine"])
        self.assertTrue(message["isDeleted"])
        self.assertEqual(message["body"], "")
        self.assertEqual(message["sender"]["publicId"], "STU-2026-01")

    def test_public_message_exposes_delivery_and_read_state(self):
        actor = {"type": "STUDENT", "id": "STU-1"}
        base = {
            "message_id": "MSG-2",
            "room_id": "ROOM-1",
            "sender_type": "STUDENT",
            "sender_student_id": "STU-1",
            "student_name": "Ana Teste",
            "status": "ACTIVE",
            "body": "Mensagem",
        }
        delivered = actions.public_chat_message({**base, "delivered_count": 1}, actor)
        read = actions.public_chat_message({**base, "delivered_count": 1, "read_count": 1}, actor)
        self.assertEqual(delivered["deliveryStatus"], "DELIVERED")
        self.assertEqual(read["deliveryStatus"], "READ")

    def test_chat_actions_are_registered_for_students_and_admins(self):
        expected = {
            "getChatRealtimeConfiguration",
            "getChatRooms",
            "getChatContacts",
            "startDirectChat",
            "updatePresence",
            "getChatMessages",
            "sendChatMessage",
            "editChatMessage",
            "deleteChatMessage",
            "markChatRoomRead",
            "reportChatMessage",
            "adminListChatRooms",
            "adminGetChatRealtimeConfiguration",
            "adminGetChatMessages",
            "adminSendChatMessage",
            "adminEditChatMessage",
            "adminDeleteChatMessage",
            "adminMarkChatRoomRead",
            "adminUpdatePresence",
            "adminGetPlatformStatistics",
        }
        self.assertTrue(expected.issubset(actions.ACTIONS))

    def test_realtime_token_is_scoped_signed_and_short_lived(self):
        secret = "realtime-test-secret-with-at-least-32-bytes"
        token, expires_at = actions.chat_realtime_token(
            {"type": "STUDENT", "id": "STU-PRIVATE-1"},
            secret,
            30,
        )
        header_segment, claims_segment, signature = token.split(".")

        def decode(segment):
            padded = segment + "=" * ((4 - len(segment) % 4) % 4)
            return json.loads(base64.urlsafe_b64decode(padded))

        claims = decode(claims_segment)
        expected_signature = base64.urlsafe_b64encode(
            hmac.new(secret.encode(), f"{header_segment}.{claims_segment}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        self.assertEqual(signature, expected_signature)
        self.assertEqual(claims["role"], "authenticated")
        self.assertEqual(claims["actor_type"], "STUDENT")
        self.assertEqual(claims["actor_id"], "STU-PRIVATE-1")
        self.assertLessEqual(claims["exp"] - claims["iat"], 30 * 60)
        self.assertEqual(int(expires_at.timestamp()), claims["exp"])

    def test_realtime_transport_broadcasts_only_minimal_invalidations(self):
        trigger_sql = actions.CHAT_REALTIME_TRIGGER_SQL
        policy_sql = actions.CHAT_REALTIME_ACCESS_SQL
        self.assertIn("realtime.send", trigger_sql)
        self.assertIn("ROOMS_CHANGED", trigger_sql)
        self.assertIn("chat:actor:student:", trigger_sql)
        self.assertNotIn("realtime.broadcast_changes", trigger_sql)
        self.assertNotIn("new,\n    old", trigger_sql.lower())
        self.assertIn("chat:actor:", policy_sql)
        self.assertIn("active_group.status = 'ACTIVE'", policy_sql)


if __name__ == "__main__":
    unittest.main()
