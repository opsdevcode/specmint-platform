"""Apply SQL migrations for the durable platform store."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations" / "platform"


def load_database_url() -> str:
    url = os.environ.get("SPECMINT_DATABASE_URL", "").strip()
    if not url:
        raise ValueError("set SPECMINT_DATABASE_URL to a PostgreSQL connection string")
    return url


def list_migration_files(directory: Path | None = None) -> tuple[Path, ...]:
    root = directory or MIGRATIONS_DIR
    if not root.is_dir():
        raise ValueError(f"missing migrations directory: {root}")
    return tuple(sorted(root.glob("*.sql")))


def apply_migrations(
    database_url: str,
    *,
    directory: Path | None = None,
) -> list[str]:
    psycopg = _import_psycopg()
    applied: list[str] = []
    files = list_migration_files(directory)
    with psycopg.connect(database_url) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            for path in files:
                name = path.name
                cur.execute("SELECT 1 FROM platform_migrations WHERE name = %s", (name,))
                if cur.fetchone():
                    continue
                sql = path.read_text(encoding="utf-8")
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO platform_migrations (name) VALUES (%s)",
                    (name,),
                )
                applied.append(name)
        conn.commit()
    return applied


def main(argv: Sequence[str] | None = None) -> int:
    _ = argv
    try:
        applied = apply_migrations(load_database_url())
    except ValueError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(f"migration failed: {exc}")
        return 1
    if applied:
        print("applied:", ", ".join(applied))
    else:
        print("no pending migrations")
    return 0


def _import_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise ValueError(
            "install durable extra: uv pip install -e '.[durable]' for psycopg"
        ) from exc
    return psycopg


if __name__ == "__main__":
    raise SystemExit(main())
