import sqlite3
from datetime import datetime, timedelta
from config import DB_PATH, BANTUKOS_DB_PATH


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS commented_posts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            fb_post_id       TEXT UNIQUE,
            post_url         TEXT,
            sought_location  TEXT,
            listing_id       INTEGER,
            comment_text     TEXT,
            commented_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Database autokomen siap.")


def already_commented(fb_post_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM commented_posts WHERE fb_post_id = ?", (fb_post_id,))
    result = c.fetchone()
    conn.close()
    return result is not None


def count_comments_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM commented_posts WHERE commented_at >= ?",
        (today + " 00:00:00",)
    )
    count = c.fetchone()[0]
    conn.close()
    return count


def save_comment(fb_post_id: str, post_url: str, sought_location: str,
                 listing_id: int, comment_text: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO commented_posts
                (fb_post_id, post_url, sought_location, listing_id, comment_text)
            VALUES (?, ?, ?, ?, ?)
        """, (fb_post_id, post_url, sought_location, listing_id, comment_text))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def find_matching_listings(sought_location: str, limit: int = 3) -> list:
    """
    Cari listing di bantukos.db yang lokasinya cocok dengan yang dicari.
    Return list of (id, location, price, contact, image_paths, caption).
    """
    try:
        conn = sqlite3.connect(BANTUKOS_DB_PATH)
        c = conn.cursor()

        if sought_location:
            area = sought_location.lower().split()[0] if sought_location else ""
            c.execute("""
                SELECT id, location, price, contact, image_paths, caption
                FROM posts
                WHERE status IN ('captioned', 'posted')
                  AND contact IS NOT NULL AND contact != ''
                  AND LOWER(location) LIKE ?
                ORDER BY COALESCE(verified, 0) DESC, RANDOM()
                LIMIT ?
            """, (f"%{area}%", limit))
        else:
            c.execute("""
                SELECT id, location, price, contact, image_paths, caption
                FROM posts
                WHERE status IN ('captioned', 'posted')
                  AND contact IS NOT NULL AND contact != ''
                ORDER BY COALESCE(verified, 0) DESC, RANDOM()
                LIMIT ?
            """, (limit,))

        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"⚠️ Gagal akses bantukos DB: {e}")
        return []
