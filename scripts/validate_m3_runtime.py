"""Validate the deployed M3 runtime without exporting server secrets."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.courseplatform.config import get_settings
from backend.courseplatform.db import connection
from backend.courseplatform.jobs import operational_metrics
from backend.courseplatform.storage import (
    download_private_object,
    require_organization_storage_path,
)


class ValidationError(RuntimeError):
    pass


def validate_runner(base_url: str) -> dict:
    with connection() as conn:
        scheduler = conn.execute(
            """
            select active, schedule
            from cron.job
            where jobname = 'courseplatform-operational-worker'
            """
        ).fetchone()
        secret_count = int(
            conn.execute(
                """
                select count(*) as secret_count
                from vault.secrets
                where name in (
                  'courseplatform_platform_url',
                  'courseplatform_job_runner_secret'
                )
                """
            ).fetchone()["secret_count"]
        )
        if not scheduler or not scheduler["active"] or secret_count != 2:
            raise ValidationError("O scheduler ou os segredos Vault nao estao prontos.")
        request_id = conn.execute(
            """
            select net.http_post(
              url := %s,
              headers := jsonb_build_object(
                'Content-Type', 'application/json',
                'Authorization', 'Bearer ' || (
                  select decrypted_secret
                  from vault.decrypted_secrets
                  where name = 'courseplatform_job_runner_secret'
                )
              ),
              body := jsonb_build_object('triggeredAt', now()),
              timeout_milliseconds := 55000
            ) as request_id
            """,
            (f"{base_url}/api/internal/jobs/run",),
        ).fetchone()["request_id"]
        conn.commit()

    response = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with connection() as conn:
            response = conn.execute(
                """
                select status_code, content, timed_out, error_msg
                from net._http_response
                where id = %s
                """,
                (request_id,),
            ).fetchone()
        if response:
            break
        time.sleep(1)
    if not response:
        raise ValidationError("O pg_net nao devolveu resposta do runner.")
    if response["timed_out"] or response["error_msg"]:
        raise ValidationError("O pedido do runner falhou no pg_net.")
    try:
        payload = json.loads(response["content"] or "{}")
    except json.JSONDecodeError as error:
        raise ValidationError("O runner devolveu JSON invalido.") from error
    if int(response["status_code"] or 0) != 200 or payload.get("status") != "processed":
        raise ValidationError(
            f"O runner devolveu HTTP {int(response['status_code'] or 0)}."
        )
    result = payload.get("result") or {}
    return {
        "cronActive": True,
        "schedule": scheduler["schedule"],
        "claimed": int(result.get("claimed") or 0),
        "succeeded": int(result.get("succeeded") or 0),
        "retried": int(result.get("retried") or 0),
        "dead": int(result.get("dead") or 0),
    }


def validate_metrics() -> dict:
    metrics = operational_metrics()
    required = {
        "pendingJobs",
        "processingJobs",
        "deadJobs",
        "overdueJobs",
        "failedNotifications",
        "dbConnections",
        "dbConnectionLimit",
        "dbConnectionUtilizationPercent",
        "organizations",
    }
    if not required.issubset(metrics):
        raise ValidationError("As metricas operacionais estao incompletas.")
    return {
        "pendingJobs": int(metrics["pendingJobs"]),
        "processingJobs": int(metrics["processingJobs"]),
        "deadJobs": int(metrics["deadJobs"]),
        "overdueJobs": int(metrics["overdueJobs"]),
        "failedNotifications": int(metrics["failedNotifications"]),
        "dbConnectionUtilizationPercent": int(
            metrics["dbConnectionUtilizationPercent"]
        ),
        "organizationCount": len(metrics["organizations"]),
    }


def validate_realtime() -> dict:
    with connection() as conn:
        membership = conn.execute(
            """
            select organization_id,
                   case when student_id is not null then 'STUDENT' else 'ADMIN' end actor_type,
                   coalesce(student_id, admin_id) actor_id
            from courseplatform.organization_memberships
            where status = 'ACTIVE'
              and (student_id is not null or admin_id is not null)
            order by created_at, membership_id
            limit 1
            """
        ).fetchone()
        if not membership:
            raise ValidationError("Nao existe uma membership ativa para validar Realtime.")
        claims = {
            "organization_id": membership["organization_id"],
            "actor_type": membership["actor_type"],
            "actor_id": membership["actor_id"],
        }
        own_topic = (
            f"chat:organization:{claims['organization_id']}:actor:"
            f"{claims['actor_type'].lower()}:{claims['actor_id']}:inbox"
        )
        own_allowed = bool(
            conn.execute(
                "select courseplatform.chat_realtime_topic_allowed(%s, %s::jsonb) as allowed",
                (own_topic, json.dumps(claims)),
            ).fetchone()["allowed"]
        )
        foreign_claims = {**claims, "organization_id": "ORG-M3-FOREIGN"}
        foreign_topic = (
            f"chat:organization:{foreign_claims['organization_id']}:actor:"
            f"{foreign_claims['actor_type'].lower()}:{foreign_claims['actor_id']}:inbox"
        )
        foreign_allowed = bool(
            conn.execute(
                "select courseplatform.chat_realtime_topic_allowed(%s, %s::jsonb) as allowed",
                (foreign_topic, json.dumps(foreign_claims)),
            ).fetchone()["allowed"]
        )
        infrastructure = conn.execute(
            """
            select
              to_regprocedure(
                'courseplatform.chat_realtime_topic_allowed(text,jsonb)'
              ) is not null as policy_function,
              exists(
                select 1 from pg_trigger
                where tgrelid = 'courseplatform.chat_messages'::regclass
                  and tgname = 'chat_messages_realtime_broadcast'
                  and not tgisinternal
              ) as broadcast_trigger
            """
        ).fetchone()
    if not own_allowed or foreign_allowed:
        raise ValidationError("O isolamento Realtime A/B falhou.")
    if not infrastructure["policy_function"] or not infrastructure["broadcast_trigger"]:
        raise ValidationError("A infraestrutura Realtime esta incompleta.")
    return {
        "ownTenantAllowed": own_allowed,
        "foreignTenantDenied": not foreign_allowed,
        "policyFunction": True,
        "broadcastTrigger": True,
    }


def validate_storage() -> dict:
    settings = get_settings()
    with connection() as conn:
        row = conn.execute(
            """
            select f.storage_bucket, f.storage_path,
                   f.storage_checksum_sha256, f.size_bytes,
                   c.organization_id
            from courseplatform.files f
            join courseplatform.attempts a on a.attempt_id = f.attempt_id
            join courseplatform.lesson_progress p on p.progress_id = a.progress_id
            join courseplatform.enrollments e on e.enrollment_id = p.enrollment_id
            join courseplatform.courses c on c.course_id = e.course_id
            where f.storage_status = 'READY'
              and f.storage_bucket is not null
              and f.storage_path is not null
              and f.storage_checksum_sha256 is not null
            order by f.uploaded_at desc nulls last, f.file_id
            limit 1
            """
        ).fetchone()
    if not row:
        raise ValidationError("Nao existe um objeto Storage READY para validar.")
    path = require_organization_storage_path(
        row["storage_path"], row["organization_id"]
    )
    max_bytes = max(int(row["size_bytes"] or 0), settings.storage_legacy_read_max_bytes)
    content = download_private_object(row["storage_bucket"], path, max_bytes)
    checksum = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(checksum, row["storage_checksum_sha256"]):
        raise ValidationError("O checksum do objeto Storage diverge da base.")
    if row["size_bytes"] and len(content) != int(row["size_bytes"]):
        raise ValidationError("O tamanho do objeto Storage diverge da base.")
    return {
        "privateDownload": True,
        "checksumValid": True,
        "bytes": len(content),
        "tenantPathValidated": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    parsed = urlsplit(args.base_url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        parser.error("--base-url deve ser uma URL HTTPS absoluta.")
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    load_dotenv(ROOT / ".env")
    get_settings().require_database()
    report = {
        "runner": validate_runner(base_url),
        "metrics": validate_metrics(),
        "realtime": validate_realtime(),
        "storage": validate_storage(),
    }
    print(json.dumps({"status": "ok", "checks": report}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(
            json.dumps(
                {"status": "failed", "reason": str(error)}, ensure_ascii=True
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
