# เลือกรายการของที่ต้องพก ตามบริบทของวันนั้น
# ห้ามใช้ datetime / ห้ามทำ I/O (กติกา core/)

from core.items import (Item, PRIORITY_ACTIVITY, PRIORITY_SUBJECT,
                        PRIORITY_WEATHER, PRIORITY_WEEKDAY, PRIORITY_ALWAYS)

# ลำดับตรงกับ "วันในสัปดาห์" ใน tuple เวลา (0 = จันทร์) ทั้ง CPython และ MicroPython
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
THAI_DAY_NAMES = ["วันจันทร์", "วันอังคาร", "วันพุธ", "วันพฤหัสฯ", "วันศุกร์",
                  "วันเสาร์", "วันอาทิตย์"]


def date_key(date_info):
    # (ปี, เดือน, วัน, ...) -> "YYYY-MM-DD" ใช้เป็น key ของ by_date
    return "{:04d}-{:02d}-{:02d}".format(date_info[0], date_info[1], date_info[2])


def subjects_today(timetable, day):
    # คืนชื่อวิชาของวันนั้น เรียงตามเวลาเริ่ม (ไม่ซ้ำ)
    rows = []
    for row in timetable:
        if row["day"] == day:
            rows.append((row["start"], row["subject"]))
    rows.sort()
    result = []
    for start, subject in rows:
        if subject not in result:
            result.append(subject)
    return result


def build_checklist(rules, timetable, weather, date_info, rain_prob=50):
    # rules      = dict จาก rules.json
    # timetable  = list จาก timetable.json
    # weather    = dict เช่น {"rain_prob": 70} หรือ None ถ้าไม่มีข้อมูลอากาศ
    # date_info  = tuple (ปี, เดือน, วัน, ชม, นาที, วินาที, วันในสัปดาห์)
    # rain_prob  = เกณฑ์โอกาสฝน % (RAIN_PROB ใน config.json)
    day = DAYS[date_info[6]]

    # เรียงแหล่งที่มาจากสำคัญมากไปน้อย: (ที่มา, ความสำคัญ, รายการของ)
    # ที่มาเป็นภาษาคน เพราะแสดงในเช็คลิสต์ เช่น "ชุดบอล (ซ้อมบอล)"
    key = date_key(date_info)
    sources = []
    # ของที่มากับนัดวันนั้น -> บอกชื่อนัด (เรียงตามเวลานัด)
    appts = list(rules.get("appointments", {}).get(key, []))
    appts.sort(key=lambda a: a["time"])
    for appt in appts:
        sources.append((appt["name"], PRIORITY_ACTIVITY, appt.get("items", [])))
    # ของที่สั่งไว้เฉพาะวันนี้ ที่ไม่ได้ผูกกับนัด (พกทั้งวัน)
    sources.append(("ทั้งวัน", PRIORITY_ACTIVITY, rules.get("by_date", {}).get(key, [])))
    for subject in subjects_today(timetable, day):
        sources.append((subject, PRIORITY_SUBJECT,
                        rules.get("by_subject", {}).get(subject, [])))
    if weather is not None and weather.get("rain_prob", 0) >= rain_prob:
        # ที่มาบอกเปอร์เซ็นต์ด้วย เช่น "ร่ม (ฝน 70%)"
        sources.append(("ฝน " + str(weather["rain_prob"]) + "%", PRIORITY_WEATHER,
                        rules.get("by_weather", {}).get("rain", [])))
    sources.append(("ทุก" + THAI_DAY_NAMES[date_info[6]], PRIORITY_WEEKDAY,
                    rules.get("by_weekday", {}).get(day, [])))
    sources.append(("พกทุกวัน", PRIORITY_ALWAYS, rules.get("always", [])))

    # ตัดของซ้ำ: เก็บเฉพาะครั้งแรกที่เจอ (= ที่มาที่สำคัญที่สุด)
    seen = set()
    items = []
    for order in range(len(sources)):
        source, priority, names = sources[order]
        for name in names:
            if name not in seen:
                seen.add(name)
                items.append(Item(name, source, priority, order))

    items.sort()
    return items
