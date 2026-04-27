"""
MMM — Database Layer
=====================
SQLite-backed identity and token storage.

Designed as a foundation that evolves from API key management
into full user accounts without migration:

    Phase now:  identities with API keys only
    Phase 4:    add username/password_hash/email to same records
    Phase 5:    add sessions table for OAuth/SSO tokens

Schema is intentionally forward-compatible — all user account
columns exist from day one, just empty until needed.

Database file: mmm.db (same directory as proxy.py)
Backup: just copy mmm.db — it's the single source of truth.

Security:
    - API keys are stored as SHA-256 hashes
    - Plain key is returned ONCE on generation, never stored
    - MMM_API_KEY in .env acts as master override (bootstrap)
    - Master override key is never written to the database
"""

import hashlib
import logging
import os
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("mmm.database")

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
DB_PATH = Path(os.getenv("MMM_DB_PATH", Path(__file__).parent / "mmm.db"))

# ─────────────────────────────────────────────
#  IDENTITY MODEL
#  Works as API key record today.
#  Works as user account tomorrow.
#  Same table, same record, just more fields.
# ─────────────────────────────────────────────
@dataclass
class Identity:
    id:            str
    key_hash:      str        # SHA-256 hash of API key — never plain
    label:         str        # human name: "gerald" or "n8n-bi-workflow"
    type:          str        # "user" or "service"
    created_at:    str
    active:        bool = True
    last_used:     Optional[str] = None

    # Phase 4 user account fields — empty until needed
    username:      Optional[str] = None
    password_hash: Optional[str] = None
    email:         Optional[str] = None
    role:          str = "user"   # "user" or "admin"


# ─────────────────────────────────────────────
#  SCHEMA
# ─────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS identities (
    id            TEXT PRIMARY KEY,
    key_hash      TEXT UNIQUE NOT NULL,
    label         TEXT NOT NULL,
    type          TEXT NOT NULL DEFAULT 'service',
    created_at    TEXT NOT NULL,
    last_used     TEXT,
    active        INTEGER NOT NULL DEFAULT 1,

    -- Phase 4: user account fields (empty until needed)
    username      TEXT UNIQUE,
    password_hash TEXT,
    email         TEXT UNIQUE,
    role          TEXT NOT NULL DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS request_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    identity_id   TEXT,
    identity_label TEXT,
    character     TEXT,
    model         TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    response_tokens INTEGER DEFAULT 0,
    thinking_tokens INTEGER DEFAULT 0,
    stripped_chars INTEGER DEFAULT 0,
    injected_chars INTEGER DEFAULT 0,
    char_delta    INTEGER DEFAULT 0,
    tokens_per_second REAL DEFAULT 0,
    time_to_first_token_ms REAL DEFAULT 0,
    FOREIGN KEY (identity_id) REFERENCES identities(id)
);

CREATE INDEX IF NOT EXISTS idx_request_log_identity
    ON request_log(identity_id);
CREATE INDEX IF NOT EXISTS idx_request_log_timestamp
    ON request_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_request_log_character
    ON request_log(character);
"""


# ─────────────────────────────────────────────
#  CONNECTION
# ─────────────────────────────────────────────
@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrent access
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema. Safe to call multiple times."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(SCHEMA)
    log.info(f"Database initialized: {DB_PATH}")


# ─────────────────────────────────────────────
#  KEY UTILITIES
# ─────────────────────────────────────────────
def generate_key() -> str:
    """Generate a cryptographically secure API key."""
    return f"mmm_{secrets.token_urlsafe(32)}"

def hash_key(key: str) -> str:
    """Hash an API key for storage. One-way — plain key is never stored."""
    return hashlib.sha256(key.encode()).hexdigest()

def generate_id() -> str:
    """Generate a UUID for identity records."""
    import uuid
    return str(uuid.uuid4())


# ─────────────────────────────────────────────
#  IDENTITY OPERATIONS
# ─────────────────────────────────────────────
def create_identity(label: str, type: str = "service",
                    role: str = "user") -> tuple[Identity, str]:
    """
    Create a new identity with a generated API key.

    Returns:
        Tuple of (Identity record, plain API key)
        The plain key is returned ONCE and never stored.
        If the user loses it, generate a new one.
    """
    plain_key = generate_key()
    identity = Identity(
        id         = generate_id(),
        key_hash   = hash_key(plain_key),
        label      = label,
        type       = type,
        created_at = datetime.now(timezone.utc).isoformat(),
        role       = role,
    )

    with get_db() as conn:
        conn.execute("""
            INSERT INTO identities
                (id, key_hash, label, type, created_at, active, role)
            VALUES
                (:id, :key_hash, :label, :type, :created_at, :active, :role)
        """, {
            "id":         identity.id,
            "key_hash":   identity.key_hash,
            "label":      identity.label,
            "type":       identity.type,
            "created_at": identity.created_at,
            "active":     1,
            "role":       identity.role,
        })

    log.info(f"Created identity: label='{label}' type='{type}' id={identity.id}")
    return identity, plain_key


def lookup_key(plain_key: str) -> Optional[Identity]:
    """
    Look up an identity by plain API key.
    Hashes the key and checks against stored hashes.
    Returns None if not found or inactive.
    """
    key_hash = hash_key(plain_key)
    with get_db() as conn:
        row = conn.execute("""
            SELECT * FROM identities
            WHERE key_hash = ? AND active = 1
        """, (key_hash,)).fetchone()

        if not row:
            return None

        # Update last_used timestamp
        conn.execute("""
            UPDATE identities SET last_used = ?
            WHERE id = ?
        """, (datetime.now(timezone.utc).isoformat(), row["id"]))

        return Identity(
            id            = row["id"],
            key_hash      = row["key_hash"],
            label         = row["label"],
            type          = row["type"],
            created_at    = row["created_at"],
            active        = bool(row["active"]),
            last_used     = row["last_used"],
            username      = row["username"],
            password_hash = row["password_hash"],
            email         = row["email"],
            role          = row["role"],
        )


def list_identities() -> list[Identity]:
    """List all identities. Never returns key hashes in API responses."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, label, type, created_at, last_used, active, role,
                   username, email
            FROM identities
            ORDER BY created_at DESC
        """).fetchall()
        return [
            Identity(
                id         = r["id"],
                key_hash   = "",   # never exposed in listings
                label      = r["label"],
                type       = r["type"],
                created_at = r["created_at"],
                active     = bool(r["active"]),
                last_used  = r["last_used"],
                username   = r["username"],
                email      = r["email"],
                role       = r["role"],
            )
            for r in rows
        ]


def revoke_identity(identity_id: str) -> bool:
    """Deactivate an identity. Requests with its key will be rejected."""
    with get_db() as conn:
        cursor = conn.execute("""
            UPDATE identities SET active = 0 WHERE id = ?
        """, (identity_id,))
        if cursor.rowcount:
            log.info(f"Revoked identity: {identity_id}")
            return True
        return False


def rotate_key(identity_id: str) -> Optional[str]:
    """
    Generate a new API key for an existing identity.
    Old key is immediately invalidated.
    Returns new plain key, or None if identity not found.
    """
    plain_key = generate_key()
    with get_db() as conn:
        cursor = conn.execute("""
            UPDATE identities
            SET key_hash = ?, last_used = NULL
            WHERE id = ? AND active = 1
        """, (hash_key(plain_key), identity_id))
        if cursor.rowcount:
            log.info(f"Rotated key for identity: {identity_id}")
            return plain_key
        return None


# ─────────────────────────────────────────────
#  REQUEST LOG
#  Persistent audit trail — complements the
#  in-memory StatsCollector in router.py
#  In-memory: fast, rolling window, lost on restart
#  Database: persistent, full history, queryable
# ─────────────────────────────────────────────
def log_request(record, identity: Optional[Identity] = None):
    """
    Write a RequestRecord to the persistent audit log.
    Called after every completed request.
    """
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO request_log (
                    timestamp, identity_id, identity_label,
                    character, model,
                    prompt_tokens, response_tokens, thinking_tokens,
                    stripped_chars, injected_chars, char_delta,
                    tokens_per_second, time_to_first_token_ms
                ) VALUES (
                    :timestamp, :identity_id, :identity_label,
                    :character, :model,
                    :prompt_tokens, :response_tokens, :thinking_tokens,
                    :stripped_chars, :injected_chars, :char_delta,
                    :tokens_per_second, :time_to_first_token_ms
                )
            """, {
                "timestamp":              record.timestamp.isoformat(),
                "identity_id":            identity.id if identity else None,
                "identity_label":         identity.label if identity else "anonymous",
                "character":              record.character,
                "model":                  record.model,
                "prompt_tokens":          record.prompt_tokens,
                "response_tokens":        record.response_tokens,
                "thinking_tokens":        record.thinking_tokens,
                "stripped_chars":         record.stripped_prompt_chars,
                "injected_chars":         record.injected_prompt_chars,
                "char_delta":             record.prompt_char_delta,
                "tokens_per_second":      record.tokens_per_second,
                "time_to_first_token_ms": record.time_to_first_token_ms,
            })
    except Exception as e:
        log.warning(f"Failed to write request log: {e}")


def query_request_log(identity_id: Optional[str] = None,
                      character: Optional[str] = None,
                      limit: int = 100) -> list[dict]:
    """Query the persistent request log with optional filters."""
    conditions = []
    params = []

    if identity_id:
        conditions.append("identity_id = ?")
        params.append(identity_id)
    if character:
        conditions.append("character = ?")
        params.append(character)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT * FROM request_log
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
        """, params + [limit]).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
#  BOOTSTRAP
#  Creates initial admin key from MMM_API_KEY
#  env var if database is empty on first run.
#  After that, manage keys via API endpoints.
# ─────────────────────────────────────────────
def bootstrap_from_env() -> Optional[str]:
    """
    On first run, if MMM_API_KEY is set and DB has no identities,
    create an initial admin identity using that key value.

    This gives operators a known key to use for the first
    /mmm/keys/generate call. After that, manage via API.

    Returns the label of the bootstrapped identity, or None.
    """
    env_key = os.getenv("MMM_API_KEY", "")
    if not env_key or env_key == "CHANGE_ME":
        return None

    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM identities"
        ).fetchone()[0]

    if count > 0:
        return None  # DB already has identities — don't bootstrap

    # First run — create admin identity from env key
    with get_db() as conn:
        identity_id = generate_id()
        conn.execute("""
            INSERT INTO identities
                (id, key_hash, label, type, created_at, active, role)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (
            identity_id,
            hash_key(env_key),
            "admin",
            "user",
            datetime.now(timezone.utc).isoformat(),
            "admin",
        ))

    log.info("Bootstrapped admin identity from MMM_API_KEY env var")
    log.info("Use POST /mmm/keys/generate to create additional keys")
    return "admin"
