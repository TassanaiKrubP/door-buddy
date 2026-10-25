# เทสต์ขั้น 1: เลือกรายการของ (checklist)
# ใช้กฎตัวอย่างในไฟล์นี้เอง เทสต์จะได้ไม่พังเมื่อผู้ใช้แก้ rules.json
import unittest

from core.items import Item, PRIORITY_SUBJECT, PRIORITY_ALWAYS
from core.checklist import build_checklist

RULES = {
    "always": ["กุญแจห้อง", "บัตรนักศึกษา"],
    "by_weekday": {"mon": ["ชุดพละ"], "tue": [], "wed": [], "thu": [],
                   "fri": [], "sat": [], "sun": []},
    "by_subject": {"วิชา A": ["โน้ตบุ๊ก", "บัตรนักศึกษา"],
                   "วิชา B": ["เครื่องคิดเลข"]},
    "by_weather": {"rain": ["ร่ม"]},
    "by_date": {"2026-10-26": ["ชุดบอล", "ขวดน้ำ"]},
}

TIMETABLE = [
    {"day": "mon", "start": "09:00", "end": "12:00", "subject": "วิชา A"},
    {"day": "wed", "start": "10:00", "end": "12:00", "subject": "วิชา B"},
]

# (ปี, เดือน, วัน, ชม, นาที, วินาที, วันในสัปดาห์) 0 = จันทร์
MON = (2026, 10, 26, 8, 0, 0, 0)    # จันทร์ มีวิชา A + มีกิจกรรม
MON2 = (2026, 11, 2, 8, 0, 0, 0)    # จันทร์ถัดไป ไม่มีกิจกรรม
SAT = (2026, 10, 31, 8, 0, 0, 5)    # เสาร์ ไม่มีเรียน


def names(items):
    return [item.name for item in items]


class TestItem(unittest.TestCase):

    def test_str(self):
        self.assertEqual(str(Item("ร่ม", "ฝน", 3)), "ร่ม (ฝน)")

    def test_lt(self):
        self.assertTrue(Item("ข", "วิชา", PRIORITY_SUBJECT) < Item("ก", "ทุกวัน", PRIORITY_ALWAYS))


class TestChecklist(unittest.TestCase):

    def test_monday_subject_rain(self):
        # วันจันทร์ มีวิชา A ฝน 70% -> รายการถูก เรียงถูก ไม่ซ้ำ
        items = build_checklist(RULES, TIMETABLE, {"rain_prob": 70}, MON, rain_prob=50)
        self.assertEqual(names(items),
                         ["ขวดน้ำ", "ชุดบอล",          # กิจกรรม
                          "บัตรนักศึกษา", "โน้ตบุ๊ก",   # วิชา A
                          "ร่ม",                       # ฝน
                          "ชุดพละ",                    # วันจันทร์
                          "กุญแจห้อง"])                # ทุกวัน

    def test_group_by_subject(self):
        # 2 วิชาในวันเดียว -> ของวิชาคาบแรกอยู่ติดกันก่อน แล้วค่อยวิชาถัดไป (ไม่ปนกัน)
        timetable = [
            {"day": "mon", "start": "13:00", "end": "15:00", "subject": "วิชา B"},
            {"day": "mon", "start": "09:00", "end": "12:00", "subject": "วิชา A"},
        ]
        rules = dict(RULES)
        rules["by_subject"] = {"วิชา A": ["โน้ตบุ๊ก", "ก้อนหิน"], "วิชา B": ["เครื่องคิดเลข"]}
        items = build_checklist(rules, timetable, None, MON2)
        self.assertEqual([item.source for item in items[:3]], ["วิชา A", "วิชา A", "วิชา B"])

    def test_no_class_day(self):
        items = build_checklist(RULES, TIMETABLE, {"rain_prob": 0}, SAT)
        self.assertEqual(names(items), ["กุญแจห้อง", "บัตรนักศึกษา"])

    def test_rain_below_threshold(self):
        items = build_checklist(RULES, TIMETABLE, {"rain_prob": 49}, MON, rain_prob=50)
        self.assertNotIn("ร่ม", names(items))

    def test_no_weather_data(self):
        # ดึงอากาศไม่ได้ -> ไม่ใช้กฎอากาศ แต่ไม่ล้ม
        items = build_checklist(RULES, TIMETABLE, None, MON)
        self.assertNotIn("ร่ม", names(items))
        self.assertIn("โน้ตบุ๊ก", names(items))

    def test_duplicate_keeps_one(self):
        # "บัตรนักศึกษา" อยู่ทั้ง always และวิชา A -> เหลือ 1 และนับเป็นของวิชา
        items = build_checklist(RULES, TIMETABLE, None, MON)
        self.assertEqual(names(items).count("บัตรนักศึกษา"), 1)
        for item in items:
            if item.name == "บัตรนักศึกษา":
                self.assertEqual(item.source, "วิชา A")

    def test_by_date_only_that_day(self):
        self.assertIn("ชุดบอล", names(build_checklist(RULES, TIMETABLE, None, MON)))
        self.assertNotIn("ชุดบอล", names(build_checklist(RULES, TIMETABLE, None, MON2)))


if __name__ == "__main__":
    unittest.main()
