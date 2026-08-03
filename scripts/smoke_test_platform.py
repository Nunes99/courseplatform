import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

from backend.courseplatform.actions import ApiError, dispatch
from backend.courseplatform.db import fetch_one


def _latest_transition_file() -> Path | None:
    folder = Path("local-secrets")
    if not folder.exists():
        return None
    files = sorted(
        list(folder.glob("supabase-password-auth-*.txt")) + list(folder.glob("auth-transition-*.txt")),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _read_transition_credentials():
    path = _latest_transition_file()
    if not path:
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    credentials = {}
    try:
        admin_header = next(i for i, line in enumerate(lines) if line.startswith("adminId\t"))
        admin_headers = lines[admin_header].split("\t")
        for line in lines[admin_header + 1:]:
            if not line.strip():
                break
            row = dict(zip(admin_headers, line.split("\t")))
            if row.get("email") and row.get("password"):
                credentials["admin_email"] = row["email"]
                credentials["admin_key"] = row["password"]
                break
    except StopIteration:
        if len(lines) > 4:
            credentials["admin_key"] = lines[4].strip()
    try:
        header_index = next(i for i, line in enumerate(lines) if line.startswith("publicStudentId\t"))
    except StopIteration:
        return credentials
    headers = lines[header_index].split("\t")
    for line in lines[header_index + 1:]:
        if not line.strip():
            continue
        row = dict(zip(headers, line.split("\t")))
        password = row.get("password") or row.get("accessCode")
        if row.get("email") and password:
            credentials["student_email"] = row["email"]
            credentials["student_code"] = password
            break
    return credentials


def _credential(name: str, fallback: str = "") -> str:
    return os.getenv(name, "").strip() or fallback


def call(action: str, payload: dict | None = None) -> dict:
    try:
        result = dispatch(action, payload or {})
    except ApiError as error:
        raise AssertionError(f"{action} failed: {error.code} {error.message}") from error
    if not result.get("success"):
        raise AssertionError(f"{action} failed: {result.get('error')}")
    print(f"ok {action}")
    return result.get("data") or {}


def main():
    transition = _read_transition_credentials()
    student_email = _credential("SMOKE_STUDENT_EMAIL", transition.get("student_email", ""))
    student_code = _credential("SMOKE_STUDENT_CODE", transition.get("student_code", ""))
    admin_email = _credential("SMOKE_ADMIN_EMAIL")
    admin_key = _credential("SMOKE_ADMIN_KEY", transition.get("admin_key", ""))
    admin_email = admin_email or transition.get("admin_email", "")

    student_token = None
    admin_token = None
    try:
        health = call("health")
        assert health.get("database") is True, health
        assert health.get("authConfigured") is True, health

        call("publicCourseConfig")
        call("publicMediaConfig")

        if student_email and student_code:
            student = call("login", {"email": student_email, "accessCode": student_code})
            student_token = student["sessionToken"]
            courses_data = call("getMyCourses", {"sessionToken": student_token})
            dashboard = call("getDashboard", {"sessionToken": student_token})
            notification_data = call("getMyNotifications", {"sessionToken": student_token, "limit": 5})
            assert isinstance(notification_data.get("notifications"), list), notification_data
            assert int(notification_data.get("unreadCount") or 0) >= 0, notification_data
            courses = courses_data.get("courses") or []
            if courses:
                course_id = (courses[0].get("course") or {}).get("courseId")
                call("getMediaConfig", {"sessionToken": student_token, "courseId": course_id})
            lessons = dashboard.get("lessons") or []
            if lessons:
                progress = lessons[0].get("progress") or {}
                assert progress.get("contentAccessStatus") in {"AVAILABLE", "LOCKED"}, progress
                assert progress.get("evaluationStatus") in {
                    "NOT_STARTED", "IN_PROGRESS", "UNDER_REVIEW", "CORRECTION_REQUIRED",
                    "APPROVED", "FAILED", "TIME_EXCEEDED",
                }, progress
                lesson_id = (lessons[0].get("lesson") or {}).get("lessonId")
                if lesson_id:
                    if progress.get("contentAccessStatus") == "AVAILABLE":
                        lesson_data = call("getLesson", {"sessionToken": student_token, "lessonId": lesson_id})
                        assert int((lesson_data.get("lesson") or {}).get("submissionDurationMinutes") or 0) > 0
        else:
            print("skip student authenticated smoke: SMOKE_STUDENT_EMAIL/SMOKE_STUDENT_CODE missing")

        if admin_key:
            if not admin_email:
                admin = fetch_one(
                    "select email from courseplatform.admins where status = 'ACTIVE' order by created_at nulls last limit 1"
                )
                admin_email = admin["email"] if admin else ""
            if admin_email:
                admin = call("adminLogin", {"email": admin_email, "adminKey": admin_key})
                admin_token = admin["adminToken"]
                courses = call("adminListCourses", {"adminToken": admin_token})
                call("adminMe", {"adminToken": admin_token})
                call("adminListStudents", {"adminToken": admin_token, "limit": 5})
                call("adminListStaff", {"adminToken": admin_token})
                submissions = call("adminListSubmissions", {"adminToken": admin_token, "limit": 5})
                notification_log = call("adminListNotifications", {"adminToken": admin_token, "limit": 5})
                assert isinstance(notification_log.get("notifications"), list), notification_log
                assert "configured" in (notification_log.get("whatsappConfiguration") or {}), notification_log
                if submissions.get("submissions"):
                    progress = submissions["submissions"][0].get("progress") or {}
                    assert progress.get("contentAccessStatus") in {"AVAILABLE", "LOCKED"}, progress
                    assert progress.get("evaluationStatus"), progress
                call("adminGetMediaConfig", {"adminToken": admin_token})
                call("adminListGroups", {"adminToken": admin_token})
                first_course_item = (courses.get("courses") or [{}])[0]
                first_course = (first_course_item.get("course") or first_course_item).get("courseId")
                if first_course:
                    structure = call("adminGetCourseStructure", {"adminToken": admin_token, "courseId": first_course})
                    if structure.get("lessons"):
                        lesson = (structure["lessons"][0].get("lesson") or {})
                        assert int(lesson.get("submissionDurationMinutes") or 0) > 0, lesson
        else:
            print("skip admin authenticated smoke: SMOKE_ADMIN_KEY missing")

        print("SMOKE_OK")
    finally:
        if student_token:
            call("logout", {"sessionToken": student_token})
        if admin_token:
            call("adminLogout", {"adminToken": admin_token})


if __name__ == "__main__":
    main()
