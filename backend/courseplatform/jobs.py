import hmac
import json
import logging
import secrets
from typing import Any

from .config import get_settings
from .db import connection


logger = logging.getLogger(__name__)

PASSWORD_RESET_JOB = "STUDENT_PASSWORD_RESET_EMAIL"
ACCOUNT_VERIFICATION_JOB = "STUDENT_ACCOUNT_VERIFICATION_EMAIL"
SUPPORTED_JOB_TYPES = {PASSWORD_RESET_JOB, ACCOUNT_VERIFICATION_JOB}


class JobConfigurationError(RuntimeError):
    pass


class JobDeliveryError(RuntimeError):
    pass


def _encryption_key() -> str:
    key = get_settings().notification_config_encryption_key
    if len(key.encode("utf-8")) < 32:
        raise JobConfigurationError(
            "NOTIFICATION_CONFIG_ENCRYPTION_KEY must contain at least 32 bytes."
        )
    return key


def _job_id() -> str:
    return f"JOB-{secrets.token_hex(12).upper()}"


def enqueue_job(job_type: str, payload: dict[str, Any], idempotency_key: str) -> str:
    if job_type not in SUPPORTED_JOB_TYPES:
        raise ValueError("Unsupported operational job type.")
    key = _encryption_key()
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.operational_jobs
              (job_id, job_type, idempotency_key, payload_encrypted, status,
               priority, attempt_count, max_attempts, available_at, created_at, updated_at)
            values (%s, %s, %s,
                    pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256'),
                    'PENDING', 100, 0, 5, now(), now(), now())
            on conflict (idempotency_key) do update
            set updated_at = courseplatform.operational_jobs.updated_at
            returning job_id
            """,
            (_job_id(), job_type, idempotency_key, serialized, key),
        ).fetchone()
        conn.commit()
    return str(row["job_id"])


def enqueue_identity_delivery(delivery_type: str, delivery: dict[str, Any]) -> str:
    if delivery_type == PASSWORD_RESET_JOB:
        entity_id = str(delivery.get("resetId") or "")
        payload = {"resetId": entity_id, "token": str(delivery.get("token") or "")}
    elif delivery_type == ACCOUNT_VERIFICATION_JOB:
        entity_id = str(delivery.get("verificationId") or "")
        payload = {"verificationId": entity_id, "token": str(delivery.get("token") or "")}
    else:
        raise ValueError("Unsupported identity delivery type.")
    if not entity_id or not payload["token"]:
        raise ValueError("Identity delivery is incomplete.")
    return enqueue_job(delivery_type, payload, f"{delivery_type}:{entity_id}")


def claim_jobs(worker_id: str, limit: int) -> list[dict[str, Any]]:
    key = _encryption_key()
    bounded_limit = max(1, min(int(limit), 50))
    with connection() as conn:
        rows = conn.execute(
            """
            with candidates as (
              select job_id
              from courseplatform.operational_jobs
              where (
                status = 'PENDING'
                or (status = 'PROCESSING' and lease_expires_at < now())
              )
                and available_at <= now()
                and attempt_count < max_attempts
              order by priority, available_at, created_at
              limit %s
              for update skip locked
            ), claimed as (
              update courseplatform.operational_jobs j
              set status = 'PROCESSING',
                  attempt_count = j.attempt_count + 1,
                  locked_by = %s,
                  lease_expires_at = now() + interval '2 minutes',
                  last_error_code = null,
                  updated_at = now()
              from candidates c
              where j.job_id = c.job_id
              returning j.*
            )
            select job_id, job_type, attempt_count, max_attempts,
                   pgp_sym_decrypt(payload_encrypted, %s)::text as payload_json
            from claimed
            order by priority, created_at
            """,
            (bounded_limit, worker_id[:120], key),
        ).fetchall()
        conn.commit()
    claimed: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        payload_json = item.pop("payload_json")
        item["payload"] = json.loads(payload_json)
        claimed.append(item)
    return claimed


def _mark_succeeded(job_id: str, worker_id: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            update courseplatform.operational_jobs
            set status = 'SUCCEEDED', completed_at = now(), lease_expires_at = null,
                locked_by = null, last_error_code = null, updated_at = now()
            where job_id = %s and status = 'PROCESSING' and locked_by = %s
            """,
            (job_id, worker_id[:120]),
        )
        conn.commit()


def _mark_failed(job: dict[str, Any], worker_id: str, error: Exception) -> str:
    terminal = int(job["attempt_count"]) >= int(job["max_attempts"])
    next_status = "DEAD" if terminal else "PENDING"
    # Exponential retry: 1, 2, 4, 8... minutes, capped at one hour.
    delay_seconds = min(3600, 60 * (2 ** max(0, int(job["attempt_count"]) - 1)))
    with connection() as conn:
        conn.execute(
            """
            update courseplatform.operational_jobs
            set status = %s,
                available_at = case when %s = 'PENDING'
                  then now() + make_interval(secs => %s) else available_at end,
                lease_expires_at = null, locked_by = null,
                last_error_code = %s,
                completed_at = case when %s = 'DEAD' then now() else null end,
                updated_at = now()
            where job_id = %s and status = 'PROCESSING' and locked_by = %s
            """,
            (
                next_status, next_status, delay_seconds, error.__class__.__name__[:80],
                next_status, job["job_id"], worker_id[:120],
            ),
        )
        conn.commit()
    return next_status


def _execute_job(job: dict[str, Any]) -> None:
    # Lazy import avoids a circular dependency while keeping existing domain
    # adapters as the compatibility boundary during the modular transition.
    from .actions import (
        dispatch_student_account_verification,
        dispatch_student_password_reset,
    )

    payload = job["payload"]
    if job["job_type"] == PASSWORD_RESET_JOB:
        delivered = dispatch_student_password_reset(payload["resetId"], payload["token"])
    elif job["job_type"] == ACCOUNT_VERIFICATION_JOB:
        delivered = dispatch_student_account_verification(
            payload["verificationId"], payload["token"]
        )
    else:
        raise JobDeliveryError("Unknown operational job type.")
    if delivered is False:
        raise JobDeliveryError("Identity delivery was not completed.")


def run_operational_cycle(limit: int | None = None, worker_id: str = "") -> dict[str, Any]:
    settings = get_settings()
    selected_limit = limit or settings.job_batch_size
    selected_worker = worker_id or f"worker-{secrets.token_hex(6)}"
    jobs = claim_jobs(selected_worker, selected_limit)
    result = {"claimed": len(jobs), "succeeded": 0, "retried": 0, "dead": 0}
    for job in jobs:
        try:
            _execute_job(job)
            _mark_succeeded(job["job_id"], selected_worker)
            result["succeeded"] += 1
        except Exception as error:
            status = _mark_failed(job, selected_worker, error)
            result["dead" if status == "DEAD" else "retried"] += 1
            logger.warning(
                "Operational job failed.",
                extra={
                    "event": "operational_job_failed",
                    "job_id": job["job_id"],
                    "job_type": job["job_type"],
                    "attempt": int(job["attempt_count"]),
                    "terminal": status == "DEAD",
                    "error_type": error.__class__.__name__,
                },
            )

    from .actions import (
        deliver_pending_email,
        deliver_pending_push,
        deliver_pending_telegram,
        deliver_pending_whatsapp,
    )

    notifications: dict[str, dict[str, int]] = {}
    for channel, delivery_function in (
        ("whatsapp", deliver_pending_whatsapp),
        ("email", deliver_pending_email),
        ("telegram", deliver_pending_telegram),
        ("push", deliver_pending_push),
    ):
        try:
            notifications[channel] = delivery_function(None, limit=selected_limit)
        except Exception as error:
            notifications[channel] = {"sent": 0, "failed": 0, "pending": 0}
            logger.warning(
                "Notification channel cycle failed.",
                extra={
                    "event": "notification_channel_cycle_failed",
                    "channel": channel,
                    "error_type": error.__class__.__name__,
                },
            )
    result["notifications"] = notifications
    metrics = operational_metrics()
    if metrics["deadJobs"] or metrics["overdueJobs"] or metrics["failedNotifications"]:
        logger.error("Operational alert threshold reached.", extra={"event": "operational_alert", **metrics})
    return result


def operational_metrics() -> dict[str, int]:
    with connection() as conn:
        row = conn.execute(
            """
            select
              count(*) filter (where status = 'PENDING') as pending_jobs,
              count(*) filter (where status = 'PROCESSING') as processing_jobs,
              count(*) filter (where status = 'DEAD') as dead_jobs,
              count(*) filter (
                where status = 'PENDING' and available_at < now() - interval '5 minutes'
              ) as overdue_jobs,
              (select count(*) from courseplatform.notification_deliveries
               where status = 'DEAD') as failed_notifications
            from courseplatform.operational_jobs
            """
        ).fetchone() or {}
    return {
        "pendingJobs": int(row.get("pending_jobs") or 0),
        "processingJobs": int(row.get("processing_jobs") or 0),
        "deadJobs": int(row.get("dead_jobs") or 0),
        "overdueJobs": int(row.get("overdue_jobs") or 0),
        "failedNotifications": int(row.get("failed_notifications") or 0),
    }


def runner_authorized(authorization: str, explicit_secret: str) -> bool:
    expected = get_settings().job_runner_secret
    if not expected:
        return False
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    candidate = explicit_secret or bearer
    return bool(candidate) and hmac.compare_digest(candidate, expected)
