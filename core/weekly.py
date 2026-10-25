# กิจกรรมประจำ = กิจกรรมที่เกิดซ้ำทุกสัปดาห์ เช่น เรียน ML ทุกจันทร์ 09:00
# ระบบนับเหมือน "นัด" ของวันนั้น (ช่วงเตือนก่อนเวลา + เช็คลิสต์ล่วงหน้า + ของขึ้นในเช็คลิสต์)
# ห้ามใช้ datetime / ห้ามทำ I/O (กติกา core/)
#
# เก็บใน rules.json
#   "weekly":      [{"day": "mon", "time": "09:00", "name": "เรียน ML", "items": ["โน้ตบุ๊ก"]}]
#   "weekly_skip": {"2026-10-26": ["09:00 เรียน ML"]}     งดเฉพาะวันนั้น (สัปดาห์ไหนไม่มีเรียน)

from core.checklist import DAYS


def skip_key(entry):
    # ชื่อที่ใช้จำว่างดอันไหน: "09:00 เรียน ML"
    return entry["time"] + " " + entry["name"]


def weekly_on(weekly, skips, key, weekday):
    # กิจกรรมประจำของวัน key (weekday 0 = จันทร์) ตัดอันที่งดไว้
    # คืน dict แบบเดียวกับนัด + "weekly": True (รู้ว่ามาจากกิจกรรมประจำ)
    day = DAYS[weekday]
    skipped = skips.get(key, [])
    result = []
    for entry in weekly:
        if entry["day"] == day and skip_key(entry) not in skipped:
            result.append({"time": entry["time"], "name": entry["name"],
                           "items": list(entry.get("items", [])), "weekly": True})
    return result


def appointments_on(rules, key, weekday):
    # นัดของวัน key + กิจกรรมประจำของวันนั้น (ใช้ทั้งเช็คลิสต์และช่วงเตือน)
    return (list(rules.get("appointments", {}).get(key, []))
            + weekly_on(rules.get("weekly", []), rules.get("weekly_skip", {}), key, weekday))
