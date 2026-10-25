# หา "วัน" จากข้อความภาษาไทย (เขียนใหม่ แทนไฟล์จากงานจดนัดที่หายไป)
# ใช้ datetime จึงอยู่ฝั่ง pc (core ห้ามใช้)
import datetime
import re

# คำบอกวันแบบนับจากวันนี้ (คำยาวต้องอยู่ก่อนคำสั้น เช่น มะรืนนี้ ก่อน มะรืน)
RELATIVE = [("วันนี้", 0), ("พรุ่งนี้", 1), ("พน.", 1), ("มะรืนนี้", 2), ("มะรืน", 2)]

# ชื่อวัน ลำดับตรงกับ weekday() (0 = จันทร์) · แต่ละวันมีหลายแบบ ยาวก่อนสั้น
DAY_NAMES = [
    ["วันจันทร์", "จันทร์"],
    ["วันอังคาร", "อังคาร"],
    ["วันพุธ", "พุธ"],
    ["วันพฤหัสบดี", "วันพฤหัส", "พฤหัสบดี", "พฤหัส"],
    ["วันศุกร์", "ศุกร์"],
    ["วันเสาร์", "เสาร์"],
    ["วันอาทิตย์", "อาทิตย์"],
]


def cut(text, word):
    # ตัดคำที่เจอออกจากข้อความ แล้วตัดช่องว่างหัวท้าย
    return text.replace(word, "", 1).strip()


def find_date(text, today):
    # คืน (date, ข้อความที่เหลือ) · ไม่เจอวัน = (None, text)
    for word, days in RELATIVE:
        if word in text:
            return today + datetime.timedelta(days=days), cut(text, word)

    # แบบ 24/10 (ไม่ใส่ปี = ปีนี้ ถ้าวันนั้นผ่านไปแล้ว = ปีหน้า)
    match = re.search(r"(\d{1,2})/(\d{1,2})", text)
    if match:
        try:
            day = int(match.group(1))
            month = int(match.group(2))
            date = datetime.date(today.year, month, day)
            if date < today:
                date = datetime.date(today.year + 1, month, day)
            return date, cut(text, match.group(0))
        except ValueError:       # เช่น 31/02
            return None, text

    # แบบ "วันที่ 25" (เดือนนี้ ถ้าผ่านไปแล้ว = เดือนหน้า)
    match = re.search(r"วันที่\s*(\d{1,2})", text)
    if match:
        day = int(match.group(1))
        year = today.year
        month = today.month
        try:
            date = datetime.date(year, month, day)
            if date < today:
                if month == 12:
                    year, month = year + 1, 1
                else:
                    month = month + 1
                date = datetime.date(year, month, day)
            return date, cut(text, match.group(0))
        except ValueError:       # เช่น วันที่ 31 ในเดือนที่มี 30 วัน
            return None, text

    # ชื่อวัน = วันนั้นที่ใกล้ที่สุด (ถ้าตรงกับวันนี้ = วันนี้)
    # "เสาร์นี้" = แบบเดียวกัน · "เสาร์หน้า" = ไม่นับวันนี้ (ถ้าวันนี้วันเสาร์ = อีก 7 วัน)
    # ตัดคำ นี้/หน้า ทิ้งด้วย ชื่อของจะได้ไม่เป็น "นี้ ร่ม"
    for weekday in range(7):
        for word in DAY_NAMES[weekday]:
            if word in text:
                days = (weekday - today.weekday()) % 7
                for suffix in ["หน้า", "นี้"]:
                    if word + suffix in text:
                        if suffix == "หน้า" and days == 0:
                            days = 7
                        word = word + suffix
                        break
                return today + datetime.timedelta(days=days), cut(text, word)

    return None, text


def hhmm(hour, minute):
    # ชม, นาที -> "HH:MM"
    return "{:02d}:{:02d}".format(hour, minute)


def find_time(text):
    # คืน ("HH:MM", ข้อความที่เหลือ) · ไม่เจอเวลา / เวลาไม่มีจริง = (None, text)
    # แบบ 14:00 / 8.30 / 10.30 น. (ถ้าตามด้วย "บาท" = ราคา ไม่ใช่เวลา) · ตัด "น." / "นาฬิกา" ทิ้งด้วย
    match = re.search(r"(\d{1,2})[:.](\d{2})(?!\d)(?!\s*บาท)\s*(น\.|นาฬิกา|น(?=\s|$))?", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour < 24 and minute < 60:
            return hhmm(hour, minute), cut(text, match.group(0))
        return None, text

    # บ่ายโมง = 13:00 · บ่าย 2 (โมง) = 14:00 · ใช้ได้แค่บ่าย 1-5
    match = re.search(r"บ่าย\s*(\d{1,2})?\s*(โมง)?(ครึ่ง)?", text)
    if match and (match.group(1) or match.group(2)):
        hour = 1
        if match.group(1):
            hour = int(match.group(1))
        if hour < 1 or hour > 5:
            return None, text
        minute = 30 if match.group(3) else 0
        return hhmm(hour + 12, minute), cut(text, match.group(0))

    # 1-5 ทุ่ม = 19:00-23:00 · 6 ทุ่ม = เที่ยงคืน
    match = re.search(r"(\d{1,2})\s*ทุ่ม(ครึ่ง)?", text)
    if match:
        count = int(match.group(1))
        if count < 1 or count > 6:
            return None, text
        minute = 30 if match.group(2) else 0
        return hhmm((count + 18) % 24, minute), cut(text, match.group(0))

    # 8 โมง(เช้า) = 08:00 · 5 โมงเย็น = 17:00 · 1-5 โมงเฉย ๆ = บ่าย (คนไทยมักหมายถึงบ่าย)
    match = re.search(r"(\d{1,2})\s*โมง(เช้า|เย็น)?(ครึ่ง)?", text)
    if match:
        hour = int(match.group(1))
        if hour < 1 or hour > 12:
            return None, text
        if match.group(2) == "เย็น" or (match.group(2) is None and hour <= 5):
            hour = hour + 12
        minute = 30 if match.group(3) else 0
        if hour < 24:
            return hhmm(hour, minute), cut(text, match.group(0))
        return None, text

    if "เที่ยงคืน" in text:                  # ต้องเช็กก่อน "เที่ยง"
        return "00:00", cut(text, "เที่ยงคืน")
    if "เที่ยง" in text:
        return "12:00", cut(text, "เที่ยง")

    # ช่วงเวลากว้าง ๆ ไม่บอกโมง -> เดาเวลาให้ (ตอบกลับจะบอกเวลาที่เดา ผู้ใช้เห็นและแก้ได้)
    for word, guess in [("ตอนเช้า", "08:00"), ("ตอนบ่าย", "13:00"),
                        ("ตอนเย็น", "17:00"), ("ตอนค่ำ", "19:00")]:
        if word in text:
            return guess, cut(text, word)

    return None, text


THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]


def short_day(key, today=None):
    # "2026-10-24" -> "ส.24/10" · ใส่ today ด้วย = "วันนี้ ศ.23/10" / "พรุ่งนี้ ส.24/10"
    # ใช้กับทุกข้อความที่คนอ่าน (ไม่โชว์ 2026-10-24 ให้คนเห็น)
    date = key_to_date(key)
    text = THAI_DAYS[date.weekday()] + str(date.day) + "/" + str(date.month)
    if today is not None:
        if date == today:
            return "วันนี้ " + text
        if date == today + datetime.timedelta(days=1):
            return "พรุ่งนี้ " + text
    return text


def date_key(date):
    # date -> "YYYY-MM-DD" (key ของ by_date ใน rules.json)
    return "{:04d}-{:02d}-{:02d}".format(date.year, date.month, date.day)


def date_tuple(date):
    # date -> tuple แบบที่ core ใช้ (ปี, เดือน, วัน, ชม, นาที, วินาที, วันในสัปดาห์)
    return (date.year, date.month, date.day, 0, 0, 0, date.weekday())


def key_to_date(key):
    # "YYYY-MM-DD" -> date
    return datetime.date(int(key[0:4]), int(key[5:7]), int(key[8:10]))
