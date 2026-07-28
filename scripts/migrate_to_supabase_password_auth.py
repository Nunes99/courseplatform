import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg
except ImportError:
    psycopg = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

from backend.courseplatform.security import generate_access_code


SCHEMA_SQL = """
create extension if not exists pgcrypto;

alter table courseplatform.students add column if not exists password_hash text;
alter table courseplatform.students add column if not exists password_changed_at timestamptz;
alter table courseplatform.students add column if not exists password_reset_required boolean not null default false;
alter table courseplatform.students alter column access_code drop not null;

alter table courseplatform.admins add column if not exists password_hash text;
alter table courseplatform.admins add column if not exists password_changed_at timestamptz;
alter table courseplatform.admins add column if not exists password_reset_required boolean not null default false;

create index if not exists idx_admins_email on courseplatform.admins(email);
"""


def connect():
    if psycopg is None:
        raise SystemExit("Missing psycopg. Install dependencies with: pip install -r requirements.txt")
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Missing DATABASE_URL.")
    return psycopg.connect(database_url, connect_timeout=20)


def scalar(conn, query: str, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return row[0] if row else None


def rows(conn, query: str, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        columns = [column.name for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def mask_password(value: str) -> str:
    if not value:
        return ""
    return value[:2] + "*" * max(4, len(value) - 4) + value[-2:]


def write_secret_file(student_passwords, admin_passwords):
    folder = ROOT / "local-secrets"
    folder.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = folder / f"supabase-password-auth-{stamp}.txt"
    lines = [
        "CoursePlatform Supabase password auth migration",
        f"Generated at UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Admin passwords:",
        "adminId\temail\tpassword",
    ]
    for item in admin_passwords:
        lines.append(f"{item['admin_id']}\t{item['email']}\t{item['password']}")
    lines.extend(["", "Student passwords:", "publicStudentId\tstudentId\tfullName\temail\tpassword"])
    for item in student_passwords:
        lines.append(
            f"{item.get('public_student_id') or ''}\t{item['student_id']}\t{item['full_name']}\t{item['email']}\t{item['password']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def migrate(apply: bool, rotate_existing: bool):
    student_passwords = []
    admin_passwords = []
    with connect() as conn:
        conn.execute(SCHEMA_SQL)

        students = rows(
            conn,
            """
            select student_id, public_student_id, full_name, email, password_hash
            from courseplatform.students
            where status = 'ACTIVE'
            order by full_name, email
            """,
        )
        admins = rows(
            conn,
            """
            select admin_id, full_name, email, password_hash
            from courseplatform.admins
            where status = 'ACTIVE'
            order by full_name, email
            """,
        )

        for student in students:
            if student.get("password_hash") and not rotate_existing:
                continue
            password = generate_access_code(12)
            student_passwords.append({**student, "password": password})
            if apply:
                conn.execute(
                    """
                    update courseplatform.students
                    set password_hash = crypt(%s, gen_salt('bf', 12)),
                        password_changed_at = now(),
                        password_reset_required = true,
                        access_code = null,
                        updated_at = now()
                    where student_id = %s
                    """,
                    (password, student["student_id"]),
                )

        for admin in admins:
            if admin.get("password_hash") and not rotate_existing:
                continue
            password = generate_access_code(16)
            admin_passwords.append({**admin, "password": password})
            if apply:
                conn.execute(
                    """
                    update courseplatform.admins
                    set password_hash = crypt(%s, gen_salt('bf', 12)),
                        password_changed_at = now(),
                        password_reset_required = true,
                        updated_at = now()
                    where admin_id = %s
                    """,
                    (password, admin["admin_id"]),
                )

        if apply:
            conn.execute("update courseplatform.sessions set active = false, revoked_at = now() where active = true")
            conn.execute("update courseplatform.new_credentials set access_code = null where access_code is not null")
            conn.execute("update courseplatform.student_import_results set access_code = null where access_code is not null")
            conn.execute(
                """
                insert into courseplatform.audit_log (log_id, actor_type, actor_id, action, entity_type, entity_id, details_json, created_at)
                values (gen_random_uuid()::text, 'SYSTEM', 'MIGRATION', 'PASSWORD_AUTH_MIGRATED',
                        'AUTH', 'SUPABASE_POSTGRES_BCRYPT', %s, now())
                """,
                (
                    json.dumps(
                        {
                            "studentsUpdated": len(student_passwords),
                            "adminsUpdated": len(admin_passwords),
                            "rotateExisting": rotate_existing,
                        }
                    ),
                ),
            )
            conn.commit()
        else:
            conn.rollback()

    secret_file = None
    if apply:
        secret_file = write_secret_file(student_passwords, admin_passwords)
    return {
        "apply": apply,
        "rotateExisting": rotate_existing,
        "studentsToUpdate": len(student_passwords),
        "adminsToUpdate": len(admin_passwords),
        "secretFile": str(secret_file) if secret_file else "",
        "sampleStudentPassword": mask_password(student_passwords[0]["password"]) if student_passwords else "",
        "sampleAdminPassword": mask_password(admin_passwords[0]["password"]) if admin_passwords else "",
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate CoursePlatform auth to Supabase/Postgres bcrypt passwords.")
    parser.add_argument("--apply", action="store_true", help="Write changes to Supabase. Without this, runs as dry-run.")
    parser.add_argument(
        "--rotate-existing",
        action="store_true",
        help="Generate new passwords even for users that already have password_hash.",
    )
    args = parser.parse_args()
    print(json.dumps(migrate(args.apply, args.rotate_existing), indent=2))


if __name__ == "__main__":
    main()
