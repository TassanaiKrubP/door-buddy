# เทสต์ esp32/bdate.py (วันที่แบบไม่ใช้ datetime สำหรับบอร์ด) · เทียบกับ datetime บนคอม
import datetime
import unittest

from esp32 import bdate


class TestBoardDate(unittest.TestCase):

    def test_matches_datetime(self):
        # สุ่มช่วงยาว ๆ เทียบกับ datetime ของจริง (รวมปีอธิกสุรทิน และข้ามปี)
        start = datetime.date(2024, 1, 1)
        for i in range(0, 1200, 7):
            day = start + datetime.timedelta(days=i)
            key = day.isoformat()
            self.assertEqual(bdate.weekday(key), day.weekday())
            self.assertEqual(bdate.add_days(key, 1),
                             (day + datetime.timedelta(days=1)).isoformat())

    def test_month_and_year_end(self):
        self.assertEqual(bdate.add_days("2026-10-31", 1), "2026-11-01")
        self.assertEqual(bdate.add_days("2026-12-31", 1), "2027-01-01")
        self.assertEqual(bdate.add_days("2028-02-28", 1), "2028-02-29")   # ปีอธิกสุรทิน

    def test_short_day(self):
        self.assertEqual(bdate.short_day("2026-10-24"), "ส.24/10")
        self.assertEqual(bdate.short_day("2026-10-24", "2026-10-24"), "วันนี้ ส.24/10")
        self.assertEqual(bdate.short_day("2026-10-25", "2026-10-24"), "พรุ่งนี้ อา.25/10")

    def test_find_date(self):
        today = "2026-10-24"
        self.assertEqual(bdate.find_date("พรุ่งนี้ ร่ม", today), ("2026-10-25", "ร่ม"))
        self.assertEqual(bdate.find_date("พน. ซ้อมบอล", today), ("2026-10-25", "ซ้อมบอล"))
        self.assertEqual(bdate.find_date("มะรืน ร่ม", today), ("2026-10-26", "ร่ม"))
        self.assertEqual(bdate.find_date("30/10 สอบ", today), ("2026-10-30", "สอบ"))
        self.assertEqual(bdate.find_date("1/1 ร่ม", today), ("2027-01-01", "ร่ม"))   # ผ่านแล้ว = ปีหน้า
        self.assertEqual(bdate.find_date("31/02 ร่ม", today), (None, "31/02 ร่ม"))   # ไม่มีจริง
        self.assertEqual(bdate.find_date("สวัสดี", today), (None, "สวัสดี"))

    def test_date_tuple(self):
        self.assertEqual(bdate.date_tuple("2026-10-26"), (2026, 10, 26, 0, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
