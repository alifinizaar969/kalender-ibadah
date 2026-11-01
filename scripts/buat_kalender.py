import json, os, time, urllib.request
from datetime import date, datetime, timedelta

KOTA_ID = "289dff07669d7a23de0ef88d2f7129e7"  # KAB. SLEMAN
JUMLAH_BULAN = 2
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
FILE_OUTPUT = "ibadah.ics"

WAKTU = [
    ("imsak", "Imsak", False),
    ("subuh", "Subuh", True),
    ("terbit", "Terbit", False),
    ("dhuha", "Dhuha", False),
    ("dzuhur", "Dzuhur", True),
    ("ashar", "Ashar", True),
    ("maghrib", "Maghrib", True),
    ("isya", "Isya", True),
]

HARI_BESAR = {
    (1, 10): "Hari Asyura (perkiraan)",
    (8, 15): "Nisfu Sya'ban (perkiraan)",
    (9, 1): "Awal Ramadan (perkiraan – ikuti sidang isbat)",
    (12, 9): "Hari Arafah (perkiraan)",
}

peringatan = []


def ambil_json(url, percobaan=3):
    for i in range(percobaan):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kalender-ibadah"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == percobaan - 1:
                raise
            time.sleep(3)


def daftar_bulan(mulai):
    th, bl = mulai.year, mulai.month
    for _ in range(JUMLAH_BULAN):
        yield th, bl
        th, bl = (th + 1, 1) if bl == 12 else (th, bl + 1)


def ambil_jadwal(th, bl):
    data = ambil_json(f"https://api.myquran.com/v3/sholat/jadwal/{KOTA_ID}/{th}-{bl:02d}?tz=Asia/Jakarta")
    return data["data"]["jadwal"]


def ambil_hijriah(tgl):
    h = ambil_json(f"https://api.myquran.com/v3/cal/hijr/{tgl.isoformat()}")["data"]["hijr"]
    return h["day"], h["month"], h["monthName"], h["year"]


def ambil_libur(tahun):
    try:
        data = ambil_json(f"https://liburin.vercel.app/api?year={tahun}")
    except Exception as e:
        peringatan.append(f"Data libur {tahun} gagal diambil ({e}).")
        return []
    if not data:
        peringatan.append(f"Data libur nasional {tahun} belum tersedia.")
    return data


def esc(teks):
    return teks.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def acara_waktu(uid, judul, mulai_wib, notifikasi):
    mulai = mulai_wib - timedelta(hours=7)
    baris = ["BEGIN:VEVENT", f"UID:{uid}@kalender-ibadah",
             f"DTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}",
             f"DTSTART:{mulai:%Y%m%dT%H%M%SZ}",
             f"DTEND:{mulai + timedelta(minutes=10):%Y%m%dT%H%M%SZ}",
             f"SUMMARY:{esc(judul)}", "TRANSP:TRANSPARENT"]
    if notifikasi:
        baris += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(judul)}",
                  "TRIGGER:PT0M", "END:VALARM"]
    return baris + ["END:VEVENT"]


def acara_seharian(uid, judul, tgl, keterangan="", ingatkan_malam_sebelumnya=False):
    baris = ["BEGIN:VEVENT", f"UID:{uid}@kalender-ibadah",
             f"DTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}",
             f"DTSTART;VALUE=DATE:{tgl:%Y%m%d}",
             f"DTEND;VALUE=DATE:{tgl + timedelta(days=1):%Y%m%d}",
             f"SUMMARY:{esc(judul)}", "TRANSP:TRANSPARENT"]
    if keterangan:
        baris.append(f"DESCRIPTION:{esc(keterangan)}")
    if ingatkan_malam_sebelumnya:
        baris += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:Besok {esc(judul)}",
                  "TRIGGER:-PT4H", "END:VALARM"]
    return baris + ["END:VEVENT"]


def puasa_sunnah(tgl, h_hari, h_bulan):
    if h_bulan == 9 or (h_bulan == 10 and h_hari == 1) or (h_bulan == 12 and 10 <= h_hari <= 13):
        return None
    if h_hari in (13, 14, 15):
        return "Puasa Ayyamul Bidh"
    if tgl.weekday() == 0:
        return "Puasa Senin"
    if tgl.weekday() == 3:
        return "Puasa Kamis"
    return None


def main():
    hari_ini = datetime.utcnow() + timedelta(hours=7)
    bulan = list(daftar_bulan(hari_ini.date().replace(day=1)))
    acara = []

    libur = {}
    for th in sorted({th for th, _ in bulan}):
        for item in ambil_libur(th):
            libur.setdefault(item["date"], []).append(item)

    for th, bl in bulan:
        for tgl_str, waktu in sorted(ambil_jadwal(th, bl).items()):
            tgl = date.fromisoformat(tgl_str)

            for kunci, nama, notif in WAKTU:
                jam, menit = map(int, waktu[kunci].split(":"))
                mulai = datetime(tgl.year, tgl.month, tgl.day, jam, menit)
                ikon = "🕌" if notif else "🕰️"
                acara += acara_waktu(f"{tgl_str}-{kunci}", f"{ikon} {nama}", mulai, notif)

            h_hari, h_bulan, h_nama, h_tahun = ambil_hijriah(tgl)
            time.sleep(0.2)
            acara += acara_seharian(f"{tgl_str}-hijriah", f"📅 {h_hari} {h_nama} {h_tahun} H", tgl,
                                    "Tanggal Hijriah hasil hisab (perkiraan).")

            puasa = puasa_sunnah(tgl, h_hari, h_bulan)
            if puasa:
                acara += acara_seharian(f"{tgl_str}-puasa", f"🌙 {puasa}", tgl,
                                        "Pengingat puasa sunnah. Jangan lupa sahur.", True)

            if (h_bulan, h_hari) in HARI_BESAR:
                acara += acara_seharian(f"{tgl_str}-haribesar", f"⭐ {HARI_BESAR[(h_bulan, h_hari)]}", tgl)

            for i, item in enumerate(libur.get(tgl_str, [])):
                ikon = "🏖️ Cuti Bersama" if item["type"] == "Cuti Bersama" else "🇮🇩 Libur"
                acara += acara_seharian(f"{tgl_str}-libur{i}", f"{ikon}: {item['name']}", tgl)

    isi = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//alifinizaar//kalender-ibadah//ID",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Kalender Ibadah",
           "X-WR-TIMEZONE:Asia/Jakarta", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
           "X-PUBLISHED-TTL:PT12H"] + acara + ["END:VCALENDAR"]
    with open(FILE_OUTPUT, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(isi) + "\r\n")
    print(f"{FILE_OUTPUT} dibuat: {sum(1 for b in acara if b == 'BEGIN:VEVENT')} acara.")

    if peringatan:
        pesan = "\n".join(peringatan) + "\nJadwal sholat tetap diperbarui."
        print(pesan)
        if NTFY_TOPIC:
            req = urllib.request.Request("https://ntfy.sh/" + NTFY_TOPIC, data=pesan.encode("utf-8"),
                                         method="POST", headers={"Title": "Kalender Ibadah: perlu dicek"})
            urllib.request.urlopen(req, timeout=30)


if __name__ == "__main__":
    main()
