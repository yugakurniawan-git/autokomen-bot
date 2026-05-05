"""
Generate komentar yang natural dan bervariasi menggunakan OpenAI.
"""
import random
from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

# Template fallback kalau OpenAI gagal
FALLBACK_TEMPLATES = [
    "Haii {name}, kebetulan ada kos di {location} nih! Harga sekitar {price}, {facilities}. Kalau minat bisa PM atau cek @bantukos 😊",
    "Hai kak {name}, kami punya info kos di {location}, harga {price}. {facilities} Minat? DM aja ya 🙏",
    "Kak {name} coba cek @bantukos, ada listing kos di {location} harga {price}. {facilities}",
    "Info kos daerah {location}: harga {price}, {facilities}. Bisa PM kalau tertarik kak {name} 😊",
    "Ada nih kak {name}, kos di {location} harga {price}. {facilities} DM @bantukos untuk detail lengkap 🏠",
]


def _extract_facilities(caption: str) -> str:
    """Ambil fasilitas singkat dari caption."""
    keywords = ["AC", "wifi", "kamar mandi dalam", "kamar mandi luar",
                "furnished", "parkir", "dapur", "air panas"]
    found = [k for k in keywords if k.lower() in (caption or "").lower()]
    if found:
        return ", ".join(found[:3]) + "."
    return ""


def generate_comment(
    poster_name: str,
    sought_location: str,
    listing_id: int,
    listing_location: str,
    listing_price: str,
    listing_caption: str,
) -> str:
    """
    Generate komentar natural menggunakan OpenAI.
    Fallback ke template kalau API gagal.
    """
    facilities = _extract_facilities(listing_caption)
    name = poster_name.split()[0] if poster_name else "kak"

    try:
        prompt = f"""Kamu adalah agen properti kos di Bali yang ramah dan natural.
Seseorang mencari kos di area {sought_location or 'Bali'}.
Kamu punya listing kos berikut untuk ditawarkan:
- Lokasi: {listing_location}
- Harga: {listing_price or 'hubungi kami'}
- Fasilitas: {facilities or 'lengkap'}

Tulis 1 komentar Facebook yang:
- Natural seperti orang biasa (bukan iklan)
- Singkat, 2-3 kalimat saja
- Sebutkan nama mereka: {name}
- Sebutkan lokasi dan harga
- Akhiri dengan ajakan PM/DM ke @bantukos
- Pakai 1-2 emoji yang relevan
- Bahasa Indonesia informal/santai
- JANGAN pakai hashtag
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.9,  # lebih variatif
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"⚠️ OpenAI gagal, pakai template: {e}")
        template = random.choice(FALLBACK_TEMPLATES)
        return template.format(
            name=name,
            location=listing_location or sought_location or "Bali",
            price=listing_price or "hubungi kami",
            facilities=facilities,
        )
