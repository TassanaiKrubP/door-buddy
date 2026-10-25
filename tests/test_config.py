# เทสต์ขั้น 0: ไฟล์ตั้งค่าเปิดได้ และมีหัวข้อครบ
import json
import os
import unittest

# โฟลเดอร์หลักของโปรเจกต์ (อยู่เหนือ tests/ หนึ่งชั้น)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def load(name):
    # อ่านไฟล์ json จากโฟลเดอร์หลัก
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


class TestConfigFiles(unittest.TestCase):

    def test_config_keys(self):
        config = load("config.json")
        need = ["OUT_DELAY", "COOLDOWN_MIN", "BEFORE_CLASS_MIN", "NO_CLASS_WINDOW",
                "OUTSIDE_WINDOW", "RAIN_PROB", "RAIN_HOURS", "NIGHT_RESET",
                "LAT", "LON", "DEMO_MODE", "OPEN_ALERT_SEC", "PREP_MIN"]
        for key in need:
            self.assertIn(key, config)
        self.assertIn(config["OUTSIDE_WINDOW"], ["none", "silent_short"])

    def test_rules_keys(self):
        # ไฟล์ตัวอย่าง (rules.json จริงเป็นข้อมูลส่วนตัว ไม่ขึ้น git · โปรแกรมสร้างจากไฟล์นี้)
        rules = load("rules.example.json")
        for key in ["always", "by_weekday", "by_subject", "by_weather", "by_date"]:
            self.assertIn(key, rules)
        for day in DAYS:
            self.assertIn(day, rules["by_weekday"])

    def test_timetable_rows(self):
        timetable = load("timetable.json")
        for row in timetable:
            for key in ["day", "start", "end", "subject"]:
                self.assertIn(key, row)
            self.assertIn(row["day"], DAYS)
            # เวลาแบบ "HH:MM" เทียบเป็น string ได้เลย
            self.assertLess(row["start"], row["end"])

    def test_activities(self):
        activities = load("activities.example.json")
        for name in activities:
            if name.startswith("_"):   # ข้ามหมายเหตุ
                continue
            self.assertIsInstance(activities[name], list)


if __name__ == "__main__":
    unittest.main()
