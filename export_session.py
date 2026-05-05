"""
Export session login Facebook ke fb_session.json.
Jalankan sekali dari laptop sebelum deploy ke server.

python3 export_session.py
"""
import os
import time
from playwright.sync_api import sync_playwright

SESSION_PATH = "data/fb_session.json"
os.makedirs("data", exist_ok=True)

print("🔐 Export Session Facebook — Bantukos AutoKomen Bot")
print("=" * 50)
print("   Browser Chromium akan terbuka.")
print("   1. Login ke akun Facebook bot di browser itu")
print("   2. Pastikan sudah masuk ke beranda")
print("   3. Kembali ke terminal ini dan tekan Enter")
print()

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir="data/browser_session",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = ctx.new_page()
    page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    input("   ✋ Sudah login? Tekan Enter untuk export session...")
    ctx.storage_state(path=SESSION_PATH)
    ctx.close()

size = os.path.getsize(SESSION_PATH) / 1024
print(f"\n✅ Session disimpan: {SESSION_PATH} ({size:.1f} KB)")
print("\nLangkah selanjutnya:")
print("   python3 main.py scan   → test scan sekali")
print("   python3 main.py        → mode terjadwal")
