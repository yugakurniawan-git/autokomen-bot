"""
python3 main.py               → mode terjadwal (scan tiap 30 menit + outreach tiap 1 jam)
python3 main.py scan          → scan komentar sekali langsung
python3 main.py outreach      → outreach scan sekali langsung
python3 main.py stats         → lihat statistik komentar & leads hari ini
"""
import sys
import time
import schedule
import sqlite3
from database import init_db, count_comments_today, DB_PATH
from scanner import scan_and_comment
from outreach import run_outreach, init_outreach_db, count_leads_today, OUTREACH_DB_PATH
from config import SCAN_INTERVAL_MINUTES, MAX_COMMENTS_PER_DAY


def show_stats():
    today_count = count_comments_today()
    leads_count = count_leads_today()
    print(f"\n📊 Statistik Hari Ini:")
    print(f"   Komentar   : {today_count}/{MAX_COMMENTS_PER_DAY}")
    print(f"   Leads WA   : {leads_count}")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT sought_location, listing_id, comment_text, commented_at
        FROM commented_posts
        ORDER BY commented_at DESC
        LIMIT 10
    """)
    rows = c.fetchall()
    conn.close()

    if rows:
        print("\n   10 komentar terakhir:")
        for r in rows:
            print(f"   [{r[3][:16]}] Lokasi: {r[0] or '-'} → BK-{r[1]}")
            print(f"   \"{r[2][:70]}...\"")
            print()

    try:
        conn2 = sqlite3.connect(OUTREACH_DB_PATH)
        leads = conn2.execute("""
            SELECT poster_name, location, profile_url, notified_at
            FROM outreach_leads
            ORDER BY notified_at DESC
            LIMIT 5
        """).fetchall()
        conn2.close()
        if leads:
            print("   5 leads terakhir:")
            for l in leads:
                print(f"   [{l[3][:16]}] {l[0] or '?'} | {l[1]} → {l[2][:50] or '-'}")
    except Exception:
        pass


def run_scheduled():
    init_db()
    init_outreach_db()
    print("\n🤖 Bantukos AutoKomen Bot dimulai!")
    print(f"   Komentar scan tiap : {SCAN_INTERVAL_MINUTES} menit")
    print(f"   Outreach scan tiap : 60 menit")
    print(f"   Max komentar/hari  : {MAX_COMMENTS_PER_DAY}")
    print("   Tekan Ctrl+C untuk berhenti\n")

    schedule.every(SCAN_INTERVAL_MINUTES).minutes.do(scan_and_comment)
    schedule.every(60).minutes.do(run_outreach)

    # Langsung scan sekali saat start
    scan_and_comment()
    run_outreach()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "scheduled"

    if mode == "scan":
        init_db()
        scan_and_comment()
    elif mode == "outreach":
        init_outreach_db()
        run_outreach()
    elif mode == "stats":
        show_stats()
    else:
        run_scheduled()
