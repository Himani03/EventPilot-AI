from pathlib import Path
import sqlite3
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "eventpilot.db"

def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            event_date TEXT NOT NULL,
            venue TEXT DEFAULT '',
            description TEXT NOT NULL,
            ticket_url TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            audience TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'Instagram',
            caption TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Draft',
            scheduled_for TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variant_id INTEGER REFERENCES variants(id) ON DELETE SET NULL,
            event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
            clicked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS variant_reviews (
            variant_id INTEGER PRIMARY KEY REFERENCES variants(id) ON DELETE CASCADE,
            reviewer TEXT NOT NULL,
            decision TEXT NOT NULL,
            note TEXT DEFAULT '',
            reviewed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS publish_checklists (
            variant_id INTEGER PRIMARY KEY REFERENCES variants(id) ON DELETE CASCADE,
            caption_checked INTEGER NOT NULL DEFAULT 0,
            media_checked INTEGER NOT NULL DEFAULT 0,
            platform_checked INTEGER NOT NULL DEFAULT 0,
            publish_note TEXT DEFAULT '',
            published_at TEXT
        );
        """)

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def create_event(name, event_date, venue, description, ticket_url):
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO events(name,event_date,venue,description,ticket_url,created_at)
               VALUES(?,?,?,?,?,?)""",
            (name, event_date, venue, description, ticket_url, now_iso())
        )
        return cur.lastrowid

def save_variant(event_id, audience, platform, caption, scheduled_for=None):
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO variants(event_id,audience,platform,caption,status,scheduled_for,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (event_id, audience, platform, caption, "Draft", scheduled_for, now_iso())
        )
        return cur.lastrowid

def list_events():
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM events ORDER BY id DESC")]

def get_event(event_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return dict(row) if row else None

def list_variants(event_id=None):
    with connect() as conn:
        if event_id is None:
            rows = conn.execute("""
                SELECT v.*, e.name AS event_name, e.ticket_url
                FROM variants v JOIN events e ON e.id=v.event_id
                ORDER BY v.id DESC
            """)
        else:
            rows = conn.execute("""
                SELECT v.*, e.name AS event_name, e.ticket_url
                FROM variants v JOIN events e ON e.id=v.event_id
                WHERE v.event_id=? ORDER BY v.id DESC
            """, (event_id,))
        return [dict(r) for r in rows]

def record_click(variant_id, event_id):
    with connect() as conn:
        conn.execute(
            "INSERT INTO clicks(variant_id,event_id,clicked_at) VALUES(?,?,?)",
            (variant_id, event_id, now_iso())
        )

def analytics():
    with connect() as conn:
        rows = conn.execute("""
            SELECT e.name AS event_name, v.audience, v.platform, v.status,
                   COUNT(c.id) AS clicks, v.id AS variant_id, v.created_at
            FROM variants v
            JOIN events e ON e.id=v.event_id
            LEFT JOIN clicks c ON c.variant_id=v.id
            GROUP BY v.id
            ORDER BY clicks DESC, v.id DESC
        """)
        return [dict(r) for r in rows]

def update_variant_status(variant_id, status, scheduled_for=None):
    with connect() as conn:
        conn.execute(
            "UPDATE variants SET status=?, scheduled_for=? WHERE id=?",
            (status, scheduled_for, variant_id)
        )

def review_variant(variant_id, reviewer, decision, note=""):
    """Save the latest review decision and mirror it in the variant workflow status."""
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("Reviewer name is required.")
    if decision not in ("Approved", "Changes requested"):
        raise ValueError("Decision must be Approved or Changes requested.")
    with connect() as conn:
        conn.execute(
            """INSERT INTO variant_reviews(variant_id,reviewer,decision,note,reviewed_at)
               VALUES(?,?,?,?,?) ON CONFLICT(variant_id) DO UPDATE SET
               reviewer=excluded.reviewer, decision=excluded.decision,
               note=excluded.note, reviewed_at=excluded.reviewed_at""",
            (variant_id, reviewer, decision, note.strip(), now_iso())
        )
        conn.execute("UPDATE variants SET status=? WHERE id=?", (decision, variant_id))

def get_variant_review(variant_id):
    """Return the latest review for a variant, or None when it has not been reviewed."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM variant_reviews WHERE variant_id=?", (variant_id,)).fetchone()
        return dict(row) if row else None

def save_publish_checklist(variant_id, caption_checked, media_checked, platform_checked, publish_note=""):
    """Insert or update the pre-publish checklist without clearing publish history."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO publish_checklists
               (variant_id,caption_checked,media_checked,platform_checked,publish_note)
               VALUES(?,?,?,?,?) ON CONFLICT(variant_id) DO UPDATE SET
               caption_checked=excluded.caption_checked, media_checked=excluded.media_checked,
               platform_checked=excluded.platform_checked, publish_note=excluded.publish_note""",
            (variant_id, int(caption_checked), int(media_checked), int(platform_checked), publish_note.strip())
        )

def get_publish_checklist(variant_id):
    """Return checklist fields, or an empty mapping when no checklist has been saved."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM publish_checklists WHERE variant_id=?", (variant_id,)).fetchone()
        return dict(row) if row else {}

def mark_variant_published(variant_id, publish_note=""):
    """Record a manual publish time and update the variant status."""
    with connect() as conn:
        conn.execute("UPDATE variants SET status='Published manually', scheduled_for=NULL WHERE id=?", (variant_id,))
        conn.execute(
            """INSERT INTO publish_checklists(variant_id,published_at,publish_note)
               VALUES(?,?,?) ON CONFLICT(variant_id) DO UPDATE SET
               published_at=excluded.published_at, publish_note=excluded.publish_note""",
            (variant_id, now_iso(), publish_note.strip())
        )

def publishing_history():
    """Return review and manual publishing records for the history page."""
    with connect() as conn:
        rows = conn.execute("""SELECT v.id AS variant_id,e.name AS event_name,v.audience,v.platform,
            v.caption,v.status,v.scheduled_for,c.published_at,c.publish_note,
            r.reviewer,r.decision,r.reviewed_at,r.note AS review_note
            FROM variants v JOIN events e ON e.id=v.event_id
            LEFT JOIN publish_checklists c ON c.variant_id=v.id
            LEFT JOIN variant_reviews r ON r.variant_id=v.id
            WHERE v.status='Published manually' OR r.variant_id IS NOT NULL
            ORDER BY COALESCE(c.published_at,r.reviewed_at) DESC""")
        return [dict(r) for r in rows]

def click_history():
    """Return tracked clicks grouped by date for the analytics trend chart."""
    with connect() as conn:
        rows = conn.execute("""SELECT date(c.clicked_at) AS click_date, COUNT(*) AS clicks
            FROM clicks c GROUP BY date(c.clicked_at) ORDER BY click_date""")
        return [dict(r) for r in rows]
