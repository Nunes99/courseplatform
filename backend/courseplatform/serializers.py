from collections.abc import Callable
from typing import Any


IsoSerializer = Callable[[Any], str | None]


def serialize_course(row: dict[str, Any] | None, *, as_iso: IsoSerializer):
    if not row:
        return None
    return {
        "courseId": row["course_id"],
        "courseCode": row.get("course_code"),
        "title": row.get("title"),
        "description": row.get("description"),
        "totalHours": float(row.get("total_hours") or 0),
        "passingScore": float(row.get("passing_score") or 0),
        "status": row.get("status"),
        "createdAt": as_iso(row.get("created_at")),
        "updatedAt": as_iso(row.get("updated_at")),
    }


def serialize_course_version(row: dict[str, Any] | None, *, as_iso: IsoSerializer):
    if not row:
        return None
    return {
        "courseVersionId": row.get("course_version_id"),
        "courseId": row.get("course_id"),
        "versionNumber": int(row.get("version_number") or 0),
        "status": row.get("status"),
        "title": row.get("title"),
        "description": row.get("description"),
        "totalHours": float(row.get("total_hours") or 0),
        "passingScore": float(row.get("passing_score") or 0),
        "createdBy": row.get("created_by"),
        "publishedBy": row.get("published_by"),
        "createdAt": as_iso(row.get("created_at")),
        "updatedAt": as_iso(row.get("updated_at")),
        "publishedAt": as_iso(row.get("published_at")),
    }


def serialize_course_offering(row: dict[str, Any] | None, *, as_iso: IsoSerializer):
    if not row:
        return None
    return {
        "offeringId": row.get("offering_id"),
        "courseId": row.get("course_id"),
        "courseVersionId": row.get("course_version_id"),
        "offeringCode": row.get("offering_code"),
        "name": row.get("name"),
        "startDate": as_iso(row.get("start_date")),
        "endDate": as_iso(row.get("end_date")),
        "capacity": None if row.get("capacity") is None else int(row.get("capacity")),
        "status": row.get("status"),
        "leadAdminId": row.get("lead_admin_id"),
        "rules": row.get("rules_json") or {},
        "calendar": row.get("calendar_json") or [],
        "enrollmentCount": int(row.get("enrollment_count") or 0),
        "createdAt": as_iso(row.get("created_at")),
        "updatedAt": as_iso(row.get("updated_at")),
    }


def serialize_enrollment(row: dict[str, Any] | None, *, as_iso: IsoSerializer):
    if not row:
        return None
    return {
        "enrollmentId": row["enrollment_id"],
        "studentId": row.get("student_id"),
        "courseId": row.get("course_id"),
        "courseVersionId": row.get("course_version_id"),
        "offeringId": row.get("offering_id"),
        "groupId": row.get("group_id"),
        "status": row.get("status"),
        "enrolledAt": as_iso(row.get("enrolled_at")),
        "completedAt": as_iso(row.get("completed_at")),
        "progressPercent": float(row.get("progress_percent") or 0),
        "finalScore": None if row.get("final_score") is None else float(row["final_score"]),
        "certificateId": row.get("certificate_id"),
    }


def serialize_group_member(row: dict[str, Any] | None, *, as_iso: IsoSerializer):
    if not row:
        return None
    return {
        "groupMemberId": row["group_member_id"],
        "groupId": row.get("group_id"),
        "enrollmentId": row.get("enrollment_id"),
        "studentId": row.get("student_id"),
        "status": row.get("status"),
        "joinedAt": as_iso(row.get("joined_at")),
        "updatedAt": as_iso(row.get("updated_at")),
    }
