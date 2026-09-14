"""Copy legacy Base64 submissions and receipts to private Supabase Storage.

Dry-run is the default. Use --apply only in a controlled staging/production
window after the schema migration and a verified database backup.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.courseplatform.config import get_settings
from backend.courseplatform.db import connection
from backend.courseplatform.actions import audit
from backend.courseplatform.storage import (
    storage_object_path,
    upload_private_object,
    validate_legacy_upload,
)


@dataclass
class BackfillResult:
    scanned: int = 0
    eligible: int = 0
    copied: int = 0
    failed: int = 0


def submission_rows(limit: int):
    with connection() as conn:
        return conn.execute(
            """
            select file_id, attempt_id, student_id, file_name, mime_type, drive_url
            from courseplatform.files
            where drive_url like 'data:%;base64,%'
              and coalesce(storage_status, '') <> 'READY'
            order by uploaded_at nulls first, file_id
            limit %s
            """,
            (limit,),
        ).fetchall()


def receipt_rows(limit: int):
    with connection() as conn:
        return conn.execute(
            """
            select request_id, student_id, payment_receipt_name, payment_receipt_mime_type,
                   payment_receipt_url
            from courseplatform.certificate_requests
            where payment_receipt_url like 'data:%;base64,%'
              and coalesce(payment_receipt_storage_status, '') <> 'READY'
            order by submitted_at nulls first, request_id
            limit %s
            """,
            (limit,),
        ).fetchall()


def backfill_submissions(limit: int, apply: bool) -> BackfillResult:
    settings = get_settings()
    result = BackfillResult()
    for row in submission_rows(limit):
        result.scanned += 1
        try:
            upload = validate_legacy_upload(
                row["drive_url"], row.get("file_name"), row.get("mime_type"), purpose="SUBMISSION"
            )
            result.eligible += 1
            if not apply:
                continue
            path = storage_object_path("submission", row["student_id"], row["attempt_id"], upload)
            upload_private_object(settings.supabase_submission_bucket, path, upload)
            with connection() as conn:
                updated = conn.execute(
                    """
                    update courseplatform.files
                    set file_name = %s, mime_type = %s, size_bytes = %s,
                        storage_bucket = %s, storage_path = %s,
                        storage_checksum_sha256 = %s, storage_status = 'READY',
                        storage_upload_key = %s
                    where file_id = %s and drive_url = %s
                      and coalesce(storage_status, '') <> 'READY'
                    returning file_id
                    """,
                    (
                        upload.file_name, upload.mime_type, upload.size_bytes,
                        settings.supabase_submission_bucket, path, upload.checksum_sha256,
                        f"legacy:{row['file_id']}:{upload.checksum_sha256}",
                        row["file_id"], row["drive_url"],
                    ),
                ).fetchone()
                if updated:
                    audit(
                        conn,
                        "SYSTEM",
                        "STORAGE_BACKFILL",
                        "SUBMISSION_FILE_STORAGE_BACKFILLED",
                        "FILE",
                        row["file_id"],
                        {"sizeBytes": upload.size_bytes, "mimeType": upload.mime_type},
                    )
                conn.commit()
            result.copied += int(bool(updated))
        except Exception:
            result.failed += 1
    return result


def backfill_receipts(limit: int, apply: bool) -> BackfillResult:
    settings = get_settings()
    result = BackfillResult()
    for row in receipt_rows(limit):
        result.scanned += 1
        try:
            upload = validate_legacy_upload(
                row["payment_receipt_url"],
                row.get("payment_receipt_name"),
                row.get("payment_receipt_mime_type"),
                purpose="PAYMENT_RECEIPT",
            )
            result.eligible += 1
            if not apply:
                continue
            path = storage_object_path("payment-receipt", row["student_id"], row["request_id"], upload)
            upload_private_object(settings.supabase_payment_receipt_bucket, path, upload)
            with connection() as conn:
                updated = conn.execute(
                    """
                    update courseplatform.certificate_requests
                    set payment_receipt_name = %s, payment_receipt_mime_type = %s,
                        payment_receipt_size_bytes = %s, payment_receipt_bucket = %s,
                        payment_receipt_path = %s, payment_receipt_checksum_sha256 = %s,
                        payment_receipt_storage_status = 'READY'
                    where request_id = %s and payment_receipt_url = %s
                      and coalesce(payment_receipt_storage_status, '') <> 'READY'
                    returning request_id
                    """,
                    (
                        upload.file_name, upload.mime_type, upload.size_bytes,
                        settings.supabase_payment_receipt_bucket, path, upload.checksum_sha256,
                        row["request_id"], row["payment_receipt_url"],
                    ),
                ).fetchone()
                if updated:
                    audit(
                        conn,
                        "SYSTEM",
                        "STORAGE_BACKFILL",
                        "PAYMENT_RECEIPT_STORAGE_BACKFILLED",
                        "CERTIFICATE_REQUEST",
                        row["request_id"],
                        {"sizeBytes": upload.size_bytes, "mimeType": upload.mime_type},
                    )
                conn.commit()
            result.copied += int(bool(updated))
        except Exception:
            result.failed += 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Copia Base64 legado para Storage privado.")
    parser.add_argument("--apply", action="store_true", help="Executa uploads e atualiza metadados.")
    parser.add_argument("--limit", type=int, default=100, help="Máximo por tipo nesta execução.")
    args = parser.parse_args()
    limit = max(1, min(args.limit, 1000))
    submissions = backfill_submissions(limit, args.apply)
    receipts = backfill_receipts(limit, args.apply)
    mode = "apply" if args.apply else "dry-run"
    print(
        f"mode={mode} submissions_scanned={submissions.scanned} submissions_eligible={submissions.eligible} "
        f"submissions_copied={submissions.copied} submissions_failed={submissions.failed} "
        f"receipts_scanned={receipts.scanned} receipts_eligible={receipts.eligible} "
        f"receipts_copied={receipts.copied} receipts_failed={receipts.failed}"
    )
    return 1 if submissions.failed or receipts.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
