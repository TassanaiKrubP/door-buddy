# เทสต์ขั้น 7: analyze.py (สรุปผล + แนะนำ OUT_DELAY + กราฟ)
import os
import shutil
import tempfile
import unittest

import analyze


def event(name, secs=0, detail="", date="2026-10-01"):
    return {"date": date, "time": "08:00:00", "event": name, "secs": secs, "detail": detail}


class TestAnalyze(unittest.TestCase):

    def test_suggest_needs_enough_data(self):
        value, reason = analyze.suggest_delay([30, 40], [], 120)
        self.assertIsNone(value)
        self.assertIn("ยังน้อย", reason)

    def test_suggest_from_short_trips(self):
        # ออกแป๊บเดียว 95% ไม่เกิน 60 วิ -> 60 + 20 = 80
        shorts = [20, 30, 40, 50, 60, 60, 45, 35, 25, 55]
        value, reason = analyze.suggest_delay(shorts, [600, 900], 120)
        self.assertEqual(value, 80)
        self.assertIn("95%", reason)

    def test_suggest_warns_near_limit_and_quick_trips(self):
        # ออกแป๊บเดียวหลายครั้งเกือบถึง 120 -> เตือนว่าค่าตอนนี้อาจสั้นไป
        shorts = [110, 115, 112, 118, 30, 40]
        value, reason = analyze.suggest_delay(shorts, [100], 120)
        self.assertIn("เกือบถึง 120", reason)
        self.assertIn("การออกจริงที่สั้นกว่านี้", reason)          # trip 100 วิ < ค่าแนะนำ

    def test_summarize_counts(self):
        events = [event("alert"), event("alert"), event("false_alert"),
                  event("short_trip", 30), event("trip", 600),
                  event("forget", detail="ร่ม"), event("forget", detail="ร่ม"),
                  event("alert", date="2026-10-02")]
        s = analyze.summarize(events, 120)
        self.assertEqual(s["alerts"], 3)
        self.assertEqual(round(s["false_rate"]), 33)
        self.assertEqual(s["forget"], {"ร่ม": 2})
        self.assertEqual(s["per_day"]["2026-10-01"], {"alert": 2, "false_alert": 1})
        self.assertEqual(s["days"], ["2026-10-01", "2026-10-02"])

    def test_report_labels_sample(self):
        # ข้อมูลจำลองต้องกำกับไว้ (สเปก)
        s = analyze.summarize([event("alert")], 120)
        lines = analyze.report_lines(s, " (ข้อมูลจำลอง)")
        self.assertIn("ข้อมูลจำลอง", lines[0])

    def test_sample_is_repeatable(self):
        self.assertEqual(analyze.make_sample(), analyze.make_sample())
        names = set(row[2] for row in analyze.make_sample())
        self.assertTrue({"short_trip", "trip", "alert"} <= names)

    def test_load_events(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "events.csv")
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write("date,time,event,secs,detail\n2026-10-01,08:00:00,short_trip,30,\n")
            rows = analyze.load_events(path)
            self.assertEqual(rows[0]["secs"], 30)
        finally:
            shutil.rmtree(tmp)

    def test_draw_png_or_skip(self):
        # มี matplotlib = ได้ไฟล์ PNG · ไม่มี = คืน False (ไม่ล้ม)
        tmp = tempfile.mkdtemp()
        try:
            rows = analyze.make_sample()
            events = [{"date": r[0], "time": r[1], "event": r[2], "secs": r[3], "detail": r[4]}
                      for r in rows]
            path = os.path.join(tmp, "report.png")
            if analyze.draw(analyze.summarize(events, 120), path, " (ข้อมูลจำลอง)"):
                self.assertGreater(os.path.getsize(path), 1000)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
