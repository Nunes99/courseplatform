import hmac
import hashlib
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
OPERATIONAL_ALERT_KEY = "operational-queue-health"
OPERATIONAL_ALERT_COOLDOWN_MINUTES = 30


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
    if _operational_alert_triggered(metrics):
        logger.error("Operational alert threshold reached.", extra={"event": "operational_alert", **metrics})
        try:
            _dispatch_operational_alert(metrics)
        except Exception as error:
            logger.error(
                "Operational alert delivery failed.",
                extra={
                    "event": "operational_alert_delivery_failed",
                    "error_type": error.__class__.__name__,
                },
            )
    return result


def _alert_fingerprint(metrics: dict[str, int]) -> str:
    normalized = {
        key: int(metrics.get(key) or 0)
        for key in (
            "deadJobs", "overdueJobs", "failedNotifications",
            "dbConnectionUtilizationPercent",
        )
    }
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _operational_alert_triggered(metrics: dict[str, int]) -> bool:
    settings = get_settings()
    database_threshold = int(
        getattr(settings, "db_connection_alert_percent", 80) or 80
    )
    return bool(
        int(metrics.get("deadJobs") or 0)
        or int(metrics.get("overdueJobs") or 0)
        or int(metrics.get("failedNotifications") or 0)
        or int(metrics.get("dbConnectionUtilizationPercent") or 0)
        >= database_threshold
    )


def _claim_operational_alert(metrics: dict[str, int]) -> bool:
    fingerprint = _alert_fingerprint(metrics)
    with connection() as conn:
        conn.execute(
            """
            insert into courseplatform.operational_alert_state
              (alert_key, status, fingerprint, metrics_json, created_at, updated_at)
            values (%s, 'OPEN', %s, %s::jsonb, now(), now())
            on conflict (alert_key) do nothing
            """,
            (OPERATIONAL_ALERT_KEY, fingerprint, json.dumps(metrics)),
        )
        row = conn.execute(
            """
            select status, fingerprint, last_notified_at, lease_expires_at
            from courseplatform.operational_alert_state
            where alert_key = %s
            for update
            """,
            (OPERATIONAL_ALERT_KEY,),
        ).fetchone() or {}
        due = bool(
            row.get("status") != "OPEN"
            or row.get("fingerprint") != fingerprint
            or row.get("last_notified_at") is None
            or conn.execute(
                "select %s < now() - make_interval(mins => %s) as due",
                (row.get("last_notified_at"), OPERATIONAL_ALERT_COOLDOWN_MINUTES),
            ).fetchone()["due"]
        )
        lease_available = row.get("lease_expires_at") is None or conn.execute(
            "select %s < now() as available",
            (row.get("lease_expires_at"),),
        ).fetchone()["available"]
        if due and lease_available:
            conn.execute(
                """
                update courseplatform.operational_alert_state
                set status = 'OPEN', fingerprint = %s, metrics_json = %s::jsonb,
                    lease_expires_at = now() + interval '2 minutes',
                    last_error_code = null, updated_at = now()
                where alert_key = %s
                """,
                (fingerprint, json.dumps(metrics), OPERATIONAL_ALERT_KEY),
            )
        conn.commit()
    return bool(due and lease_available)


def _finish_operational_alert(error: Exception | None = None) -> None:
    with connection() as conn:
        conn.execute(
            """
            update courseplatform.operational_alert_state
            set lease_expires_at = null,
                last_notified_at = case when %s is null then now() else last_notified_at end,
                notification_count = notification_count + case when %s is null then 1 else 0 end,
                last_error_code = %s,
                updated_at = now()
            where alert_key = %s
            """,
            (
                None if error is None else error.__class__.__name__[:80],
                None if error is None else error.__class__.__name__[:80],
                None if error is None else error.__class__.__name__[:80],
                OPERATIONAL_ALERT_KEY,
            ),
        )
        conn.commit()


def _dispatch_operational_alert(metrics: dict[str, int]) -> None:
    if not _claim_operational_alert(metrics):
        return
    try:
        from .actions import email_runtime_configuration, send_email_notification

        with connection() as conn:
            recipients = conn.execute(
                """
                select distinct lower(email) as email, full_name
                from courseplatform.admins
                where status = 'ACTIVE'
                  and role in ('OWNER', 'ADMIN', 'ADMINISTRATOR')
                  and nullif(trim(email), '') is not null
                order by lower(email)
                """
            ).fetchall()
        if not recipients:
            raise JobConfigurationError("No active operational alert recipient is configured.")
        configuration = email_runtime_configuration()
        if not configuration.get("configured"):
            raise JobConfigurationError("The institutional SMTP channel is not configured.")
        settings = get_settings()
        action_url = f"{settings.platform_url.rstrip('/')}/admin.html#/operations"
        summary = (
            f"Tarefas bloqueadas: {int(metrics.get('deadJobs') or 0)}\n"
            f"Tarefas atrasadas: {int(metrics.get('overdueJobs') or 0)}\n"
            f"Notificacoes com falha: {int(metrics.get('failedNotifications') or 0)}\n"
            f"Utilizacao de ligacoes Postgres: "
            f"{int(metrics.get('dbConnectionUtilizationPercent') or 0)}%"
        )
        for recipient in recipients:
            send_email_notification(
                {
                    "recipient": recipient["email"],
                    "student_name": recipient.get("full_name") or "Administracao",
                    "title": "Alerta operacional da plataforma",
                    "email_subject": "CoursePlatform: intervencao operacional necessaria",
                    "message": summary,
                    "email_message": summary,
                    "action_url": action_url,
                },
                configuration,
            )
    except Exception as error:
        _finish_operational_alert(error)
        raise
    _finish_operational_alert()


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
        database_row = conn.execute(
            """
            select
              count(*) filter (where datname = current_database()) as database_connections,
              count(*) filter (
                where datname = current_database() and state = 'active'
              ) as active_database_connections,
              count(*) filter (
                where datname = current_database() and state = 'idle in transaction'
              ) as idle_in_transaction_connections,
              current_setting('max_connections')::integer as connection_limit
            from pg_stat_activity
            """
        ).fetchone() or {}
    database_connections = int(database_row.get("database_connections") or 0)
    connection_limit = max(1, int(database_row.get("connection_limit") or 1))
    return {
        "pendingJobs": int(row.get("pending_jobs") or 0),
        "processingJobs": int(row.get("processing_jobs") or 0),
        "deadJobs": int(row.get("dead_jobs") or 0),
        "overdueJobs": int(row.get("overdue_jobs") or 0),
        "failedNotifications": int(row.get("failed_notifications") or 0),
        "dbConnections": database_connections,
        "dbActiveConnections": int(database_row.get("active_database_connections") or 0),
        "dbIdleInTransactionConnections": int(
            database_row.get("idle_in_transaction_connections") or 0
        ),
        "dbConnectionLimit": connection_limit,
        "dbConnectionUtilizationPercent": round(
            database_connections * 100 / connection_limit
        ),
    }


def runner_authorized(authorization: str, explicit_secret: str) -> bool:
    expected = get_settings().job_runner_secret
    if not expected:
        return False
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    candidate = explicit_secret or bearer
    return bool(candidate) and hmac.compare_digest(candidate, expected)
