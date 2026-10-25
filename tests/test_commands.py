# เทสต์ขั้น 5: แยกคำสั่ง (core/commands.py) + หาวัน (pc/thai_dt.py)
import datetime
import unittest

from core.commands import parse_command
from pc.thai_dt import find_date, find_time, date_key

ACTIVITIES = {"_note": "หมายเหตุ", "ซ้อมบอล": ["ชุดบอล", "รองเท้า", "ขวดน้ำ"]}
TODAY = datetime.date(2026, 10, 23)   # ศุกร์


def parse(text):
    # ทำแบบเดียวกับฝั่ง pc: หาเวลา -> หาวัน (มีเวลาแต่ไม่มีวัน = วันนี้) -> ส่งให้ core
    time, rest = find_time(text)
    date, rest = find_date(rest, TODAY)
    if date is None and time is not None:
        date = TODAY
    found = None
    if date is not None:
        found = (date_key(date), rest)
    return parse_command(text, found, ACTIVITIES, time)


class TestThaiDate(unittest.TestCase):

    def test_relative(self):
        self.assertEqual(find_date("วันนี้ซ้อมบอล", TODAY), (TODAY, "ซ้อมบอล"))
        self.assertEqual(find_date("พรุ่งนี้ซ้อมบอล", TODAY)[0], datetime.date(2026, 10, 24))
        self.assertEqual(find_date("พน. ซ้อมบอล", TODAY), (datetime.date(2026, 10, 24), "ซ้อมบอล"))
        self.assertEqual(find_date("มะรืนนี้ ร่ม", TODAY), (datetime.date(2026, 10, 25), "ร่ม"))

    def test_day_month(self):
        self.assertEqual(find_date("30/10 สอบ", TODAY), (datetime.date(2026, 10, 30), "สอบ"))
        # วันที่ผ่านไปแล้ว = ปีหน้า
        self.assertEqual(find_date("1/1 ร่ม", TODAY)[0], datetime.date(2027, 1, 1))
        # วันที่ไม่มีจริง
        self.assertEqual(find_date("31/02 ร่ม", TODAY)[0], None)

    def test_day_name(self):
        self.assertEqual(find_date("วันจันทร์ ซ้อมบอล", TODAY), (datetime.date(2026, 10, 26), "ซ้อมบอล"))
        self.assertEqual(find_date("ศุกร์ ร่ม", TODAY)[0], TODAY)

    def test_day_name_suffix(self):
        # "นี้" / "หน้า" ต้องไม่ติดไปในชื่อของ (เดิมได้ "หน้า ซ้อมบอล", "นี้ ร่ม")
        self.assertEqual(find_date("อาทิตย์หน้า ซ้อมบอล", TODAY),
                         (datetime.date(2026, 10, 25), "ซ้อมบอล"))
        self.assertEqual(find_date("เสาร์นี้ ร่ม", TODAY), (datetime.date(2026, 10, 24), "ร่ม"))
        # วันนี้วันศุกร์: "ศุกร์หน้า" = อีก 7 วัน · "ศุกร์นี้" = วันนี้
        self.assertEqual(find_date("ศุกร์หน้า สอบ", TODAY)[0], datetime.date(2026, 10, 30))
        self.assertEqual(find_date("ศุกร์นี้ สอบ", TODAY)[0], TODAY)

    def test_no_date(self):
        self.assertEqual(find_date("สวัสดี", TODAY), (None, "สวัสดี"))

    def test_day_of_month(self):
        self.assertEqual(find_date("วันที่25มีนัด", TODAY), (datetime.date(2026, 10, 25), "มีนัด"))
        # วันที่ผ่านไปแล้ว = เดือนหน้า
        self.assertEqual(find_date("วันที่ 5 สอบ", TODAY)[0], datetime.date(2026, 11, 5))

    def test_time(self):
        self.assertEqual(find_time("8โมง วันที่25มีนัด"), ("08:00", "วันที่25มีนัด"))
        self.assertEqual(find_time("14:30 สอบ")[0], "14:30")
        self.assertEqual(find_time("8.30 สอบ")[0], "08:30")
        self.assertEqual(find_time("บ่ายโมง")[0], "13:00")
        self.assertEqual(find_time("บ่าย 2 โมงครึ่ง")[0], "14:30")
        self.assertEqual(find_time("5 โมงเย็น")[0], "17:00")
        self.assertEqual(find_time("4โมง")[0], "16:00")
        self.assertEqual(find_time("2 ทุ่ม")[0], "20:00")
        self.assertEqual(find_time("เที่ยง")[0], "12:00")
        self.assertEqual(find_time("ซ้อมบอล"), (None, "ซ้อมบอล"))
        # เวลาที่ไม่มีจริง / ไม่ใช่เวลา -> None (เดิมได้ 27:00, 25:00, 12:00, 02:50)
        self.assertEqual(find_time("บ่าย 15")[0], None)
        self.assertEqual(find_time("7 ทุ่ม")[0], None)
        self.assertEqual(find_time("6 ทุ่ม")[0], "00:00")
        self.assertEqual(find_time("เที่ยงคืน")[0], "00:00")
        self.assertEqual(find_time("ซื้อน้ำ 2.50 บาท")[0], None)
        self.assertEqual(find_time("25:00")[0], None)
        # "น." ต้องไม่ติดไปในชื่อนัด · แต่ "นัด" ต้องไม่โดนตัด
        self.assertEqual(find_time("10.30 น. หาหมอ"), ("10:30", "หาหมอ"))
        self.assertEqual(find_time("10.30 นัดหมอ"), ("10:30", "นัดหมอ"))
        # ช่วงเวลากว้าง ๆ -> เดาเวลา
        self.assertEqual(find_time("ตอนเย็น ซ้อมบอล"), ("17:00", "ซ้อมบอล"))
        self.assertEqual(find_time("ตอนเช้า สอบ")[0], "08:00")


class TestCommands(unittest.TestCase):

    def test_tomorrow_activity(self):
        cmd = parse("พรุ่งนี้ซ้อมบอล")
        self.assertEqual(cmd["cmd"], "add_activity")
        self.assertEqual(cmd["date"], "2026-10-24")
        self.assertEqual(cmd["items"], ["ชุดบอล", "รองเท้า", "ขวดน้ำ"])

    def test_short_tomorrow(self):
        cmd = parse("พน. ซ้อมบอล")
        self.assertEqual(cmd["cmd"], "add_activity")
        self.assertEqual(cmd["date"], "2026-10-24")

    def test_single_item(self):
        # ไม่ตรงกิจกรรม = ของ 1 ชิ้น
        cmd = parse("พรุ่งนี้ ร่ม")
        self.assertEqual(cmd, {"cmd": "add_item", "date": "2026-10-24", "items": ["ร่ม"]})

    def test_appointment(self):
        self.assertEqual(parse("8โมง วันที่25มีนัด"),
                         {"cmd": "add_appointment", "date": "2026-10-25", "time": "08:00",
                          "name": "มีนัด", "items": []})
        # นัดที่ตรงกับกิจกรรม -> แนบของไปด้วย
        cmd = parse("พรุ่งนี้ 5 โมงเย็น ซ้อมบอล")
        self.assertEqual(cmd["time"], "17:00")
        self.assertEqual(cmd["items"], ["ชุดบอล", "รองเท้า", "ขวดน้ำ"])
        # มีเวลาไม่มีวัน = วันนี้ · ไม่มีชื่อ = "นัด"
        cmd = parse("บ่าย 2")
        self.assertEqual((cmd["date"], cmd["name"]), ("2026-10-23", "นัด"))

    def test_appointment_commands(self):
        self.assertEqual(parse("นัด"), {"cmd": "list_appts"})
        self.assertEqual(parse("ลบนัด 25/10"),
                         {"cmd": "remove_appt", "date": "2026-10-25", "time": None})
        self.assertEqual(parse("ลบนัด วันที่25 8โมง"),
                         {"cmd": "remove_appt", "date": "2026-10-25", "time": "08:00"})
        # ไม่บอกวัน -> date None (ฝั่ง pc ตอบให้บอกวัน)
        self.assertEqual(parse("ลบนัด")["date"], None)
        # ต้องไม่กลายเป็น "ลบ X"
        self.assertEqual(parse("ลบนัด พรุ่งนี้")["cmd"], "remove_appt")

    def test_forget(self):
        self.assertEqual(parse("ลืมสายชาร์จ"), {"cmd": "forget", "item": "สายชาร์จ"})
        self.assertEqual(parse("ลืมเอาร่ม"), {"cmd": "forget", "item": "ร่ม"})   # ตัด "เอา"

    def test_add_remove(self):
        self.assertEqual(parse("เพิ่ม ยาดม ทุกวัน"), {"cmd": "add_always", "item": "ยาดม"})
        self.assertEqual(parse("ลบ ยาดม"), {"cmd": "remove", "item": "ยาดม"})

    def test_fixed_commands(self):
        self.assertEqual(parse("วันนี้ไม่ต้องเตือน"), {"cmd": "no_alert", "date": "2026-10-23"})
        self.assertEqual(parse("วันนี้ไม่ต้องเตือนนะ")["cmd"], "no_alert")       # ไม่กลายเป็นของ
        self.assertEqual(parse("พรุ่งนี้ไม่ต้องเตือน"), {"cmd": "no_alert", "date": "2026-10-24"})
        self.assertEqual(parse("ไม่ต้องเตือน"), {"cmd": "no_alert", "date": None})
        self.assertEqual(parse("/List"), {"cmd": "list", "date": None})
        self.assertEqual(parse("/list 99/99"), {"cmd": "bad_date"})
        self.assertEqual(parse("ยังอยู่ห้อง"), {"cmd": "still_home"})
        self.assertEqual(parse("ออกแล้ว"), {"cmd": "out_now"})
        self.assertEqual(parse("เปิดเตือน"), {"cmd": "alert_on"})
        self.assertEqual(parse("/status"), {"cmd": "status"})
        self.assertEqual(parse("/help"), {"cmd": "help"})
        self.assertEqual(parse("/list"), {"cmd": "list", "date": None})
        self.assertEqual(parse("/list พรุ่งนี้"), {"cmd": "list", "date": "2026-10-24"})

    def test_not_command(self):
        # ข้อความที่ไม่ใช่คำสั่ง -> ไม่ทำอะไร
        self.assertEqual(parse("สวัสดี"), {"cmd": "none"})
        self.assertEqual(parse("ลืม"), {"cmd": "none"})
        self.assertEqual(parse("พรุ่งนี้"), {"cmd": "none"})


if __name__ == "__main__":
    unittest.main()
