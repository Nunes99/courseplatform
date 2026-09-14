"""Retire verified legacy Base64 values after the retention window.

Dry-run is the default. Apply mode requires explicit backup and stability
confirmations and never removes rows, object metadata, or Storage objects.
"""

import argparse
import hashlib
import hmac
import sys
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.courseplatform.actions import audit
from backend.courseplatform.db import connection
from backend.courseplatform.storage import (
    StorageError,
    download_private_object,
    validate_legacy_upload,
)


MINIMUM_APPLY_RETENTION_DAYS = 30


@dataclass
class CleanupResult:
    scanned: int = 0
    verified: int = 0
    cleared: int = 0
    failed: int = 0
    errors: dict[str, int] = field(default_factory=dict)

    def record_failure(self, error: Exception) -> None:
        self.failed += 1
        code = str(getattr(error, "code", error.__class__.__name__) or "UNKNOWN_ERROR")
        safe_code = "".join(char for char in code.upper() if char.isalnum() or char == "_")
        safe_code = safe_code or "UNKNOWN_ERROR"
        self.errors[safe_code] = self.errors.get(safe_code, 0) + 1


def verified_submission_candidates(limit: int, retention_days: int):
    with connection() as conn:
        return conn.execute(
            """
            select f.file_id, f.file_name, f.mime_type, f.size_bytes, f.drive_url,
                   f.storage_bucket, f.storage_path, f.storage_checksum_sha256
            from courseplatform.files f
            where f.drive_url like 'data:%%;base64,%%'
              and f.storage_status = 'READY'
              and f.storage_bucket is not null
              and f.storage_path is not null
              and f.storage_checksum_sha256 is not null
              and exists (
                select 1 from courseplatform.audit_log a
                where a.action = 'SUBMISSION_FILE_STORAGE_BACKFILLED'
                  and a.entity_type = 'FILE'
                  and a.entity_id = f.file_id
                  and a.created_at <= now() - (%s * interval '1 day')
              )
            order by f.uploaded_at nulls first, f.file_id
            limit %s
            """,
            (retention_days, limit),
        ).fetchall()


def verified_receipt_candidates(limit: int, retention_days: int):
    with connection() as conn:
        return conn.execute(
            """
            select r.request_id, r.payment_receipt_name, r.payment_receipt_mime_type,
                   r.payment_receipt_size_bytes, r.payment_receipt_url,
                   r.payment_receipt_bucket, r.payment_receipt_path,
                   r.payment_receipt_checksum_sha256
            from courseplatform.certificate_requests r
            where r.payment_receipt_url like 'data:%%;base64,%%'
              and r.payment_receipt_storage_status = 'READY'
              and r.payment_receipt_bucket is not null
              and r.payment_receipt_path is not null
              and r.payment_receipt_checksum_sha256 is not null
              and exists (
                select 1 from courseplatform.audit_log a
                where a.action = 'PAYMENT_RECEIPT_STORAGE_BACKFILLED'
                  and a.entity_type = 'CERTIFICATE_REQUEST'
                  and a.entity_id = r.request_id
                  and a.created_at <= now() - (%s * interval '1 day')
              )
            order by r.submitted_at nulls first, r.request_id
            limit %s
            """,
            (retention_days, limit),
        ).fetchall()


def verify_copy(row, *, purpose: str, legacy_field: str, name_field: str, mime_field: str,
                size_field: str, bucket_field: str, path_field: str, checksum_field: str) -> None:
    upload = validate_legacy_upload(
        row[legacy_field], row.get(name_field), row.get(mime_field), purpose=purpose
    )
    expected_checksum = str(row.get(checksum_field) or "")
    expected_size = int(row.get(size_field) or 0)
    if not hmac.compare_digest(upload.checksum_sha256, expected_checksum):
        raise StorageError("LEGACY_STORAGE_CHECKSUM_MISMATCH", "Os checksums não correspondem.")
    if expected_size and upload.size_bytes != expected_size:
        raise StorageError("LEGACY_STORAGE_SIZE_MISMATCH", "Os tamanhos não correspondem.")
    stored = download_private_object(row[bucket_field], row[path_field], max(upload.size_bytes, 1))
    if len(stored) != upload.size_bytes or not hmac.compare_digest(
        hashlib.sha256(stored).hexdigest(), expected_checksum
    ):
        raise StorageError("LEGACY_STORAGE_DOWNLOAD_MISMATCH", "O objeto armazenado diverge da origem.")


def cleanup_submissions(limit: int, retention_days: int, apply: bool) -> CleanupResult:
    result = CleanupResult()
    for row in verified_submission_candidates(limit, retention_days):
        result.scanned += 1
        try:
            verify_copy(
                row, purpose="SUBMISSION", legacy_field="drive_url", name_field="file_name",
                mime_field="mime_type", size_field="size_bytes", bucket_field="storage_bucket",
                path_field="storage_path", checksum_field="storage_checksum_sha256",
            )
            result.verified += 1
            if not apply:
                continue
            with connection() as conn:
                updated = conn.execute(
                    """
                    update courseplatform.files
                    set drive_url = ''
                    where file_id = %s and drive_url = %s and storage_status = 'READY'
                      and storage_checksum_sha256 = %s
                    returning file_id
                    """,
                    (row["file_id"], row["drive_url"], row["storage_checksum_sha256"]),
                ).fetchone()
                if updated:
                    audit(conn, "SYSTEM", "STORAGE_RETENTION", "LEGACY_SUBMISSION_BASE64_CLEARED",
                          "FILE", row["file_id"], {"retentionDays": retention_days})
                conn.commit()
            result.cleared += int(bool(updated))
        except Exception as error:
            result.record_failure(error)
    return result


def cleanup_receipts(limit: int, retention_days: int, apply: bool) -> CleanupResult:
    result = CleanupResult()
    for row in verified_receipt_candidates(limit, retention_days):
        result.scanned += 1
        try:
            verify_copy(
                row, purpose="PAYMENT_RECEIPT", legacy_field="payment_receipt_url",
                name_field="payment_receipt_name", mime_field="payment_receipt_mime_type",
                size_field="payment_receipt_size_bytes", bucket_field="payment_receipt_bucket",
                path_field="payment_receipt_path", checksum_field="payment_receipt_checksum_sha256",
            )
            result.verified += 1
            if not apply:
                continue
            with connection() as conn:
                updated = conn.execute(
                    """
                    update courseplatform.certificate_requests
                    set payment_receipt_url = ''
                    where request_id = %s and payment_receipt_url = %s
                      and payment_receipt_storage_status = 'READY'
                      and payment_receipt_checksum_sha256 = %s
                    returning request_id
                    """,
                    (row["request_id"], row["payment_receipt_url"], row["payment_receipt_checksum_sha256"]),
                ).fetchone()
                if updated:
                    audit(conn, "SYSTEM", "STORAGE_RETENTION", "LEGACY_RECEIPT_BASE64_CLEARED",
                          "CERTIFICATE_REQUEST", row["request_id"], {"retentionDays": retention_days})
                conn.commit()
            result.cleared += int(bool(updated))
        except Exception as error:
            result.record_failure(error)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove Base64 legado depois da retenção segura.")
    parser.add_argument("--apply", action="store_true", help="Limpa apenas valores já verificados.")
    parser.add_argument("--limit", type=int, default=25, help="Máximo por tipo nesta execução.")
    parser.add_argument("--retention-days", type=int, default=MINIMUM_APPLY_RETENTION_DAYS)
    parser.add_argument("--confirm-backup", action="store_true")
    parser.add_argument("--confirm-stability", action="store_true")
    args = parser.parse_args()
    limit = max(1, min(args.limit, 100))
    retention_days = max(0, args.retention_days)
    if args.apply and retention_days < MINIMUM_APPLY_RETENTION_DAYS:
        parser.error(f"--apply exige pelo menos {MINIMUM_APPLY_RETENTION_DAYS} dias de retenção.")
    if args.apply and not (args.confirm_backup and args.confirm_stability):
        parser.error("--apply exige --confirm-backup e --confirm-stability.")

    submissions = cleanup_submissions(limit, retention_days, args.apply)
    receipts = cleanup_receipts(limit, retention_days, args.apply)
    errors = {
        f"submission_{code}": count for code, count in submissions.errors.items()
    } | {
        f"receipt_{code}": count for code, count in receipts.errors.items()
    }
    error_text = ",".join(f"{code}:{count}" for code, count in sorted(errors.items())) or "none"
    print(
        f"mode={'apply' if args.apply else 'dry-run'} retention_days={retention_days} "
        f"submissions_scanned={submissions.scanned} submissions_verified={submissions.verified} "
        f"submissions_cleared={submissions.cleared} submissions_failed={submissions.failed} "
        f"receipts_scanned={receipts.scanned} receipts_verified={receipts.verified} "
        f"receipts_cleared={receipts.cleared} receipts_failed={receipts.failed} errors={error_text}"
    )
    return 1 if submissions.failed or receipts.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
