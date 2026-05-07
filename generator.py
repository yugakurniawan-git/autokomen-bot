"""
Generate komentar yang natural dan bervariasi menggunakan OpenAI.
"""
import random
from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

UPSELL_LINES = [
    "btw kalo butuh pengecekan kos sebelum dp, cek bantukos.com",
    "kalau mau dicekkan dulu kondisi kosnya, info di bantukos.com",
    "btw bisa minta disurvey dulu kosnya, cek bantukos.com aja",
    "kalau mau tau kondisi aslinya sebelum bayar, ada di bantukos.com",
    "btw ada jasa cek kos dulu sebelum dp di bantukos.com",
]

FALLBACK_TEMPLATES = [
    "ada nih kak di {location}, sekitar {price} dapet yang {facilities}. dm aja\n\n{upsell}",
    "eh kebetulan tau yang di {location} kak, fasilitasnya {facilities}. dm aja kak\n\n{upsell}",
    "kemarin liat ada kos di {location} harga {price}an, dm kalau mau info\n\n{upsell}",
    "ada info kos di {location} nih {price}, {facilities}. dm aja\n\n{upsell}",
    "kalau mau yang di {location} ada kok kak harga {price}. dm aja\n\n{upsell}",
]


def _extract_facilities(caption: str) -> str:
    keywords = ["AC", "wifi", "kamar mandi dalam", "kamar mandi luar",
                "furnished", "parkir", "dapur", "air panas"]
    found = [k for k in keywords if k.lower() in (caption or "").lower()]
    if found:
        return ", ".join(found[:3])
    return "lumayan lengkap"


def generate_comment(
    poster_name: str,
    sought_location: str,
    listing_id: int,
    listing_location: str,
    listing_price: str,
    listing_caption: str,
) -> str:
    facilities = _extract_facilities(listing_caption)
    name = poster_name.split()[0] if poster_name and poster_name.lower() != "kak" else ""
    name_part = f" {name}" if name else ""

    try:
        prompt = f"""Kamu orang biasa yang kebetulan tau info kos dan lagi baca komentar Facebook.
Ada orang yang lagi cari kos di {sought_location or 'Bali'}.
Kamu mau kasih info kos ini:
- Lokasi: {listing_location}
- Harga: {listing_price or 'bisa nego'}
- Fasilitas: {facilities}

Tulis 1 komentar Facebook yang:
- Terasa seperti komentar orang nyata, bukan iklan atau agen properti
- Sangat singkat, 1-2 kalimat saja, maksimal 25 kata
- Kasual dan santai, boleh tidak pakai huruf kapital
- Boleh singkat seperti: "ada nih di Sesetan, wa 089506585454 kak"
- Akhiri dengan ajakan "dm aja" atau "dm kak" — JANGAN sebut nomor WA atau link apapun
- Boleh sebut nama{name_part} kalau terasa natural, boleh juga tidak
- Tidak perlu emoji, atau paling banyak 1
- JANGAN sebut @bantukos, jangan pakai hashtag, jangan terdengar seperti sales

Contoh gaya yang benar:
"ada nih kak di sesetan, sekitar 750rb dapet yang AC wifi. dm aja"
"eh kebetulan tau yang di kerobokan, fasilitasnya lumayan. dm kalau mau info"
"kalau mau daerah {sought_location or 'sana'} ada kok, dm aja kak"

Tulis hanya komentar-nya saja, tanpa penjelasan apapun."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=1.0,
        )
        main = response.choices[0].message.content.strip().strip('"').strip("'")
        upsell = random.choice(UPSELL_LINES)
        return f"{main}\n\n{upsell}"

    except Exception as e:
        print(f"⚠️ OpenAI gagal, pakai template: {e}")
        template = random.choice(FALLBACK_TEMPLATES)
        return template.format(
            location=listing_location or sought_location or "Bali",
            price=listing_price or "harga oke",
            facilities=facilities,
            upsell=random.choice(UPSELL_LINES),
        )
