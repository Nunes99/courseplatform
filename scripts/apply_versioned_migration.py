"""Apply one reviewed migration and record it in Supabase migration history."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.courseplatform.db import connection


MIGRATION_NAME = re.compile(r"^(?P<version>\d{14})_(?P<name>[a-z0-9_]+)\.sql$")
MIGRATIONS = (ROOT / "supabase" / "migrations").resolve()


def migration_metadata(path: Path) -> tuple[Path, str, str, str]:
    resolved = path.resolve()
    if resolved.parent != MIGRATIONS:
        raise ValueError("A migração deve estar diretamente em supabase/migrations.")
    match = MIGRATION_NAME.fullmatch(resolved.name)
    if not match:
        raise ValueError("O nome da migração não segue TIMESTAMP_nome.sql.")
    sql = resolved.read_text(encoding="utf-8")
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest().upper()
    return resolved, match.group("version"), match.group("name"), digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("migration", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.apply:
        parser.error("A alteração externa exige --apply.")

    try:
        path, version, name, digest = migration_metadata(args.migration)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    if digest != args.expected_sha256.strip().upper():
        parser.error("O checksum da migração difere do valor revisto.")

    sql = path.read_text(encoding="utf-8")
    with connection() as conn:
        preflight = conn.execute(
            """
            select current_user as role,
                   has_schema_privilege(current_user, 'courseplatform', 'CREATE') as can_create,
                   exists (
                     select 1 from supabase_migrations.schema_migrations where version = %s
                   ) as recorded
            """,
            (version,),
        ).fetchone()
        if not preflight or not preflight["can_create"]:
            raise RuntimeError("A ligação configurada não possui privilégio de migração.")
        if preflight["recorded"]:
            raise RuntimeError(f"A migração {version} já consta no histórico remoto.")

        conn.execute(sql)
        conn.execute(
            """
            insert into supabase_migrations.schema_migrations
              (version, statements, name)
            values (%s, %s, %s)
            """,
            (version, [sql], name),
        )
        conn.commit()

    print(json.dumps({
        "applied": True,
        "version": version,
        "name": name,
        "sha256": digest,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
