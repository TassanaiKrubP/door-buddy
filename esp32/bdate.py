# วันที่สำหรับบอร์ด (MicroPython ไม่มี datetime) · คำนวณด้วยเลขจำนวนเต็มล้วน
# จึงรันได้ทั้งบนบอร์ดและบนคอม (เทสต์อยู่ใน tests/test_bdate.py)
# วันที่ใช้รูปแบบ key = "YYYY-MM-DD" เหมือนฝั่ง pc

THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
# คำบอกวันแบบนับจากวันนี้ (คำยาวก่อนคำสั้น) · เฟส 2 รองรับแค่นี้ตามสเปก + แบบ 24/10
RELATIVE = [("วันนี้", 0), ("พรุ่งนี้", 1), ("พน.", 1), ("มะรืนนี้", 2), ("มะรืน", 2)]


def days_from_civil(y, m, d):
    # (ปี, เดือน, วัน) -> เลขวันนับจาก 1970-01-01 (สูตรปฏิทินเกรกอเรียน ไม่ต้องใช้ไลบรารี)
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(n):
    # เลขวัน -> (ปี, เดือน, วัน) (ย้อนสูตรด้านบน)
    n += 719468
    era = n // 146097
    doe = n - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return (y + (m <= 2), m, d)


def make_key(y, m, d):
    return "{:04d}-{:02d}-{:02d}".format(y, m, d)


def split_key(key):
    return int(key[0:4]), int(key[5:7]), int(key[8:10])


def add_days(key, days):
    # "2026-10-31" + 1 -> "2026-11-01"
    y, m, d = split_key(key)
    y, m, d = civil_from_days(days_from_civil(y, m, d) + days)
    return make_key(y, m, d)


def weekday(key):
    # 0 = จันทร์ ... 6 = อาทิตย์ (1970-01-01 เป็นวันพฤหัส)
    y, m, d = split_key(key)
    return (days_from_civil(y, m, d) + 3) % 7


def date_tuple(key):
    # key -> tuple แบบที่ core ใช้ (ปี, เดือน, วัน, ชม, นาที, วินาที, วันในสัปดาห์)
    y, m, d = split_key(key)
    return (y, m, d, 0, 0, 0, weekday(key))


def short_day(key, today=None):
    # "2026-10-24" -> "ส.24/10" · ใส่ today = "วันนี้ ส.24/10" / "พรุ่งนี้ อา.25/10"
    y, m, d = split_key(key)
    text = THAI_DAYS[weekday(key)] + str(d) + "/" + str(m)
    if today == key:
        return "วันนี้ " + text
    if today is not None and add_days(today, 1) == key:
        return "พรุ่งนี้ " + text
    return text


def valid(y, m, d):
    # วันที่มีจริงไหม (เช็กโดยแปลงไปกลับแล้วต้องได้ค่าเดิม เช่น 31/02 ไม่ผ่าน)
    if m < 1 or m > 12 or d < 1 or d > 31:
        return False
    return civil_from_days(days_from_civil(y, m, d)) == (y, m, d)


def find_slash_date(text):
    # หา "วว/ดด" ในข้อความ (ไม่ใช้ regex) · คืน (วัน, เดือน, ข้อความที่ใช้) หรือ None
    i = text.find("/")
    while i > 0:
        a = i
        while a > 0 and text[a - 1].isdigit() and i - a < 2:
            a -= 1
        b = i + 1
        while b < len(text) and text[b].isdigit() and b - i <= 2:
            b += 1
        if a < i and b > i + 1:
            return int(text[a:i]), int(text[i + 1:b]), text[a:b]
        i = text.find("/", i + 1)
    return None


def find_date(text, today):
    # หาวันในข้อความ คืน (key, ข้อความที่เหลือ) · ไม่เจอ = (None, text)
    for word, days in RELATIVE:
        if word in text:
            return add_days(today, days), text.replace(word, "", 1).strip()
    found = find_slash_date(text)
    if found:
        d, m, used = found
        y = split_key(today)[0]
        if not valid(y, m, d):
            return None, text
        key = make_key(y, m, d)
        if key < today:                            # วันที่ผ่านไปแล้ว = ปีหน้า
            if not valid(y + 1, m, d):
                return None, text
            key = make_key(y + 1, m, d)
        return key, text.replace(used, "", 1).strip()
    return None, text
