"""Turso / LibSQL database layer.

Provides persistent storage for debates, comments, and reactions.
Falls back gracefully to no-op when TURSO_DATABASE_URL is not configured.
"""

import json
import logging
import os

log = logging.getLogger("database")

_conn = None


def init_db():
    """Initialize database connection. Call once at app startup."""
    global _conn
    url = os.getenv("TURSO_DATABASE_URL", "")
    token = os.getenv("TURSO_AUTH_TOKEN", "")
    if not url or not token:
        log.info("Turso not configured — using file-based fallback")
        return

    try:
        import libsql_experimental as libsql

        _conn = libsql.connect(
            "local.db",
            sync_url=url,
            auth_token=token,
        )
        _conn.sync()

        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS debates (
                id             TEXT PRIMARY KEY,
                topic          TEXT NOT NULL,
                golden_quote   TEXT DEFAULT '',
                warmth_message TEXT DEFAULT '',
                ts             REAL NOT NULL,
                likes          INTEGER DEFAULT 0,
                pin_token      TEXT,
                script         TEXT,
                chars          TEXT,
                consensus_items TEXT
            );
            CREATE TABLE IF NOT EXISTS comments (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                debate_id    TEXT DEFAULT '',
                debate_topic TEXT DEFAULT '',
                text         TEXT NOT NULL,
                nickname     TEXT DEFAULT '匿名旁听',
                source       TEXT DEFAULT 'human',
                ts           REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name   TEXT NOT NULL,
                user_avatar TEXT DEFAULT '',
                reaction    TEXT NOT NULL,
                topic       TEXT DEFAULT '',
                ts          REAL NOT NULL
            );
        """)
        _conn.commit()
        _conn.sync()
        log.info("Turso database initialized")
    except Exception as e:
        log.warning("Failed to init Turso database: %s", e)
        _conn = None


def is_enabled() -> bool:
    return _conn is not None


# ── Debates ──────────────────────────────────────────────

def save_debate(d: dict):
    if not _conn:
        return
    _conn.execute(
        """INSERT OR REPLACE INTO debates
           (id, topic, golden_quote, warmth_message, ts, likes, pin_token, script, chars, consensus_items)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d.get("id", ""),
            d.get("topic", ""),
            d.get("golden_quote", ""),
            d.get("warmth_message", ""),
            d.get("ts", 0),
            d.get("likes", 0),
            d.get("pin_token"),
            json.dumps(d.get("script", []), ensure_ascii=False) if d.get("script") else None,
            json.dumps(d.get("chars", {}), ensure_ascii=False) if d.get("chars") else None,
            json.dumps(d.get("consensus_items", []), ensure_ascii=False) if d.get("consensus_items") else None,
        ),
    )
    _conn.commit()


def get_debates(limit: int = 100) -> list[dict]:
    """Get debates without heavy fields (script/chars/consensus)."""
    if not _conn:
        return []
    rows = _conn.execute(
        "SELECT id, topic, golden_quote, warmth_message, ts, likes, pin_token FROM debates ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r[0], "topic": r[1], "golden_quote": r[2],
            "warmth_message": r[3], "ts": r[4], "likes": r[5],
            "pin_token": r[6], "comments": [],
        }
        for r in rows
    ]


def get_debate(debate_id: str) -> dict | None:
    """Get a single debate with all fields including heavy ones."""
    if not _conn:
        return None
    row = _conn.execute("SELECT * FROM debates WHERE id = ?", (debate_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "topic": row[1], "golden_quote": row[2],
        "warmth_message": row[3], "ts": row[4], "likes": row[5],
        "pin_token": row[6],
        "script": json.loads(row[7]) if row[7] else [],
        "chars": json.loads(row[8]) if row[8] else {},
        "consensus_items": json.loads(row[9]) if row[9] else [],
        "comments": [],
    }


def update_likes(debate_id: str, likes: int):
    if not _conn:
        return
    _conn.execute("UPDATE debates SET likes = ? WHERE id = ?", (likes, debate_id))
    _conn.commit()


def update_pin_token(debate_id: str, pin_token: str):
    if not _conn:
        return
    _conn.execute("UPDATE debates SET pin_token = ? WHERE id = ?", (pin_token, debate_id))
    _conn.commit()


# ── Comments ─────────────────────────────────────────────

def add_comment(c: dict):
    if not _conn:
        return
    _conn.execute(
        "INSERT INTO comments (debate_id, debate_topic, text, nickname, source, ts) VALUES (?, ?, ?, ?, ?, ?)",
        (c.get("debate_id", ""), c.get("debate_topic", ""), c.get("text", ""),
         c.get("nickname", "匿名旁听"), c.get("source", "human"), c.get("ts", 0)),
    )
    _conn.commit()


def get_debate_comments(debate_id: str) -> list[dict]:
    if not _conn:
        return []
    rows = _conn.execute(
        "SELECT debate_id, debate_topic, text, nickname, source, ts FROM comments WHERE debate_id = ? ORDER BY ts",
        (debate_id,),
    ).fetchall()
    return [
        {"debate_id": r[0], "debate_topic": r[1], "text": r[2],
         "nickname": r[3], "source": r[4], "ts": r[5]}
        for r in rows
    ]


def get_plaza_comments(limit: int = 50) -> list[dict]:
    """Get free comments (debate_id = '')."""
    if not _conn:
        return []
    rows = _conn.execute(
        "SELECT debate_id, debate_topic, text, nickname, source, ts FROM comments WHERE debate_id = '' ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {"debate_id": r[0], "debate_topic": r[1], "text": r[2],
         "nickname": r[3], "source": r[4], "ts": r[5]}
        for r in rows
    ]


def get_all_comments(limit: int = 50) -> list[dict]:
    if not _conn:
        return []
    rows = _conn.execute(
        "SELECT debate_id, debate_topic, text, nickname, source, ts FROM comments ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {"debate_id": r[0], "debate_topic": r[1], "text": r[2],
         "nickname": r[3], "source": r[4], "ts": r[5]}
        for r in rows
    ]


# ── Reactions ────────────────────────────────────────────

def add_reaction(r: dict):
    if not _conn:
        return
    _conn.execute(
        "INSERT INTO reactions (user_name, user_avatar, reaction, topic, ts) VALUES (?, ?, ?, ?, ?)",
        (r.get("user_name", ""), r.get("user_avatar", ""),
         r.get("reaction", ""), r.get("topic", ""), r.get("ts", 0)),
    )
    _conn.commit()


def get_reactions(limit: int = 50) -> list[dict]:
    if not _conn:
        return []
    rows = _conn.execute(
        "SELECT user_name, user_avatar, reaction, topic, ts FROM reactions ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {"user_name": r[0], "user_avatar": r[1], "reaction": r[2],
         "topic": r[3], "ts": r[4]}
        for r in rows
    ]


# ── Sync ─────────────────────────────────────────────────

def sync():
    """Push local changes to Turso remote."""
    if _conn:
        try:
            _conn.sync()
        except Exception as e:
            log.warning("Turso sync failed: %s", e)
