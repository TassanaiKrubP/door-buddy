# เทสต์ฝั่ง pc: class App ใน pc/main.py (คำสั่งแชท + ไฟล์)
# รันในโฟลเดอร์ชั่วคราว ไม่แตะ rules.json / data/ ของจริง
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import pc.main as main
from pc import storage

REAL_ROOT = storage.ROOT

RULES = {
    "always": ["กุญแจห้อง"],
    "by_weekday": {"mon": [], "tue": [], "wed": [], "thu": [], "fri": [], "sat": [], "sun": []},
    "by_subject": {},
    "by_weather": {"rain": ["ร่ม"]},
    "by_date": {"2026-10-20": ["ของเก่า"], "2026-10-26": ["ของวันนี้"]},
    "appointments": {"2026-10-20": [{"time": "08:00", "name": "นัดเก่า"}]},
}


ACTIVITIES = {"_note": "ของเทสต์", "ซ้อมบอล": ["ชุดบอล", "รองเท้า", "ขวดน้ำ"]}

TIMETABLE = [{"day": "mon", "start": "09:00", "end": "12:00", "subject": "วิชาตัวอย่าง A"},
             {"day": "mon", "start": "13:00", "end": "16:00", "subject": "วิชาตัวอย่าง B"},
             {"day": "wed", "start": "10:00", "end": "12:00", "subject": "วิชาตัวอย่าง B"}]


def at(h, m, s=0, day=26):
    # now จำลอง: day 26 = จันทร์ 26 ต.ค. 2026
    return (day * 86400 + h * 3600 + m * 60 + s, (2026, 10, day, h, m, s, (day - 26) % 7))


class AppFixture(unittest.TestCase):
    # ส่วนเตรียม App ในโฟลเดอร์ชั่วคราว (ใช้ร่วมกับ test_bot.py) · ไม่มีเทสต์ในคลาสนี้

    def setUp(self):
        # โฟลเดอร์ชั่วคราว: คัดลอกไฟล์ตั้งค่าจริง + rules ของเทสต์
        self.tmp = tempfile.mkdtemp()
        for name in ["config.json", "suggestions.json"]:
            shutil.copy(os.path.join(REAL_ROOT, name), self.tmp)
        storage.ROOT = self.tmp
        storage.pending_events.clear()
        # ตารางเรียนของเทสต์เอง (ไฟล์จริงผู้ใช้แก้/ล้างได้ เทสต์จะได้ไม่พัง)
        storage.save_json("timetable.json", TIMETABLE)
        # rules / activities ใช้ของเทสต์เอง (ไฟล์จริงเปลี่ยนตามการใช้งาน เทสต์จะได้ไม่พัง)
        storage.save_json("rules.json", RULES)
        storage.save_json("activities.json", ACTIVITIES)
        # เวลาจำลอง + ไม่มี Telegram + ไม่พิมพ์ลงจอระหว่างเทสต์
        self.real_get_now = main.get_now
        main.get_now = lambda: at(7, 40)
        # ไม่ดึงอากาศจากเน็ตจริงระหว่างเทสต์ (เทสต์อากาศอยู่ใน test_weather.py)
        self.real_start_weather = main.start_weather
        main.start_weather = lambda config: None
        # ไม่เปิดพอร์ตรับสัญญาณบอร์ดจริงระหว่างเทสต์ (เทสต์ตัวรับอยู่ใน test_door_link.py)
        self.real_start_door_link = main.start_door_link
        main.start_door_link = lambda: None
        self.real_stdout = sys.stdout
        sys.stdout = io.StringIO()
        self.app = main.App(demo=True)

    def tearDown(self):
        sys.stdout = self.real_stdout
        main.get_now = self.real_get_now
        main.start_weather = self.real_start_weather
        main.start_door_link = self.real_start_door_link
        storage.ROOT = REAL_ROOT
        shutil.rmtree(self.tmp)

    def rules_on_disk(self):
        return storage.load_json("rules.json")

    def events_on_disk(self):
        with open(os.path.join(self.tmp, storage.EVENTS), encoding="utf-8-sig") as f:
            return f.read()

    def say(self, text, now=None):
        # พิมพ์คำสั่งแชท คืนข้อความตอบกลับ
        if now is None:
            now = at(7, 40)
        reply, actions = self.app.run_command(text, now)
        self.app.handle(actions, now)
        return reply


class TestApp(AppFixture):

    def test_clean_old_dates_on_start(self):
        rules = self.rules_on_disk()
        self.assertNotIn("2026-10-20", rules["by_date"])
        self.assertNotIn("2026-10-20", rules["appointments"])
        self.assertIn("2026-10-26", rules["by_date"])          # วันนี้ยังอยู่

    def test_forget_saves_rules_and_csv(self):
        self.assertIn("เพิ่ม", self.say("ลืมร่ม"))
        self.assertIn("ร่ม", self.rules_on_disk()["always"])
        self.assertIn("forget,0,ร่ม", self.events_on_disk())

    def test_manual_edit_not_lost(self):
        # ผู้ใช้แก้ rules.json เองระหว่างโปรแกรมรัน แล้วสั่งคำสั่งแชท -> ค่าที่แก้ต้องไม่หาย
        rules = self.rules_on_disk()
        rules["always"].append("ยาดม")
        storage.save_json("rules.json", rules)
        self.say("ลืมพัดลม")
        always = self.rules_on_disk()["always"]
        self.assertIn("ยาดม", always)
        self.assertIn("พัดลม", always)

    def test_broken_rules_keeps_old(self):
        with open(os.path.join(self.tmp, "rules.json"), "w", encoding="utf-8") as f:
            f.write("{ พัง")
        self.assertIn("กุญแจห้อง", self.say("/list"))       # ยังใช้ค่าเดิมได้ ไม่ล้ม

    def test_appointment_add_list_remove(self):
        self.say("พรุ่งนี้ 5 โมงเย็น ซ้อมบอล")
        rules = self.rules_on_disk()
        self.assertEqual(rules["appointments"]["2026-10-27"][0]["time"], "17:00")
        # ของของนัดเก็บในนัดที่เดียว ไม่ซ้ำใน by_date (บั๊กเดิม: ลบที่หนึ่งแล้วยังโผล่อีกที่)
        self.assertIn("ชุดบอล", rules["appointments"]["2026-10-27"][0]["items"])
        self.assertNotIn("2026-10-27", rules["by_date"])
        self.assertIn("อ.27/10  17:00  ซ้อมบอล", self.say("นัด"))   # วันที่แบบไทย ไม่ใช่ 2026-10-27
        self.assertIn("ลบนัด", self.say("ลบนัด พรุ่งนี้"))
        rules = self.rules_on_disk()
        self.assertNotIn("2026-10-27", rules["appointments"])
        self.assertEqual(self.say("นัด"), "ยังไม่มีนัด")

    def test_old_duplicate_items_cleaned(self):
        # ข้อมูลรุ่นเก่าที่เก็บของของนัดซ้ำใน by_date -> เปิดโปรแกรมแล้วล้างให้
        rules = self.rules_on_disk()
        rules["appointments"]["2026-10-27"] = [{"time": "17:00", "name": "ซ้อมบอล",
                                               "items": ["ชุดบอล"]}]
        rules["by_date"]["2026-10-27"] = ["ชุดบอล", "ร่ม"]
        storage.save_json("rules.json", rules)
        main.App(demo=True)
        self.assertEqual(self.rules_on_disk()["by_date"]["2026-10-27"], ["ร่ม"])

    def test_appointment_items_only_in_appt(self):
        # ลบของสำหรับนัดแล้วต้องหายจากเช็คลิสต์จริง
        self.app.add_appointment("2026-10-27", "17:00", "ซ้อมบอล", ["ชุดบอล", "รองเท้า"])
        self.app.remove_appt_item("2026-10-27", 0, "17:00", "ชุดบอล")
        page = self.app.checklist_page("2026-10-27", main.datetime.date(2026, 10, 26))
        self.assertNotIn("ชุดบอล", page)
        self.assertIn("รองเท้า  (ซ้อมบอล)", page)

    def test_passed_appointment_items_not_in_checklist(self):
        # 07:40 นัด 07:00 ผ่านไปแล้ว -> ของของนัดนั้นไม่ต้องเอาไป
        self.app.add_appointment("2026-10-26", "07:00", "สอบ", ["ปากกา"])
        self.app.add_appointment("2026-10-26", "17:00", "ซ้อมบอล", ["ชุดบอล"])
        page = self.app.checklist_page("2026-10-26", main.datetime.date(2026, 10, 26))
        self.assertNotIn("ปากกา", page)
        self.assertIn("07:00  สอบ  (ผ่านแล้ว)", page)
        self.assertIn("ชุดบอล", page)

    def test_same_time_delete_one(self):
        self.app.add_appointment("2026-10-27", "17:00", "ซ้อมบอล", [])
        self.app.add_appointment("2026-10-27", "17:00", "กินข้าว", [])
        self.app.remove_appointment_at("2026-10-27", 0, "17:00")
        names = [a["name"] for a in self.rules_on_disk()["appointments"]["2026-10-27"]]
        self.assertEqual(names, ["กินข้าว"])
        # ปุ่มเก่าที่ลำดับเลื่อนไปแล้ว (ลำดับ 1 ไม่มีแล้ว) -> ไม่ลบมั่ว
        self.assertIn("ไม่เจอ", self.app.remove_appointment_at("2026-10-27", 1, "17:00"))

    def test_remove_appt_by_time(self):
        self.say("พรุ่งนี้ 8โมง สอบ")
        self.say("พรุ่งนี้ บ่าย2 ประชุม")
        self.say("ลบนัด พรุ่งนี้ 8โมง")
        appts = self.rules_on_disk()["appointments"]["2026-10-27"]
        self.assertEqual([a["name"] for a in appts], ["ประชุม"])

    def test_remove_appt_needs_date(self):
        self.assertIn("บอกวัน", self.say("ลบนัด"))

    def test_state_survives_restart(self):
        self.app.set_mode(False, at(7, 40))                   # จำค่าเฉพาะโหมดใช้งานจริง
        self.say("วันนี้ไม่ต้องเตือน")
        self.app.step(at(7, 41), None)                        # step เขียน state.json
        app2 = main.App(demo=False)                           # เปิดโปรแกรมใหม่วันเดียวกัน (ใช้งานจริง)
        self.assertTrue(app2.guard.no_alert)

    def test_csv_locked_keeps_rows(self):
        # เปิด events.csv ค้างใน Excel (เขียนไม่ได้) -> ไม่ล้ม + เก็บแถวไว้เขียนทีหลัง
        real_open = open
        locked = [True]

        def fake_open(path, *args, **kwargs):
            if locked[0] and str(path).endswith("events.csv"):
                raise PermissionError("locked")
            return real_open(path, *args, **kwargs)

        import builtins
        builtins.open = fake_open
        try:
            self.app.door_event("open", at(7, 40))          # ต้องไม่ล้ม
            self.app.door_event("close", at(7, 40, 5))
        finally:
            builtins.open = real_open
        self.assertEqual(len(storage.pending_events), 2)
        self.app.log(at(7, 41), "door_open")                # ไฟล์ว่างแล้ว -> เขียนที่ค้างด้วย
        self.assertEqual(self.events_on_disk().count("door_"), 3)
        self.assertEqual(storage.pending_events, [])

    def test_demo_writes_separate_files(self):
        # โหมดเดโมเขียนลง data/demo/ ไม่ปนข้อมูลจริง
        self.app.door_event("open", at(7, 40))              # setUp เป็นเดโม
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "data", "demo", "events.csv")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "data", "events.csv")))

    def test_no_alert_tomorrow(self):
        # ปิดเตือนล่วงหน้า: ถึงวันนั้นค่อยปิด
        self.app.guard.tick(at(7, 40))                      # guard จำรอบวันนี้ก่อน
        self.say("พรุ่งนี้ไม่ต้องเตือน")
        self.assertFalse(self.app.guard.no_alert)
        self.assertIn("2026-10-27", self.rules_on_disk()["no_alert_dates"])
        self.app.handle(self.app.guard.tick(at(3, 1, day=27)), at(3, 1, day=27))   # ข้ามคืน
        self.assertTrue(self.app.guard.no_alert)

    def test_demo_does_not_remember(self):
        # โหมดเดโมไม่เขียน state.json (อัดคลิปหลายเทคได้โดยไม่ต้องลบไฟล์)
        self.say("วันนี้ไม่ต้องเตือน")
        self.app.step(at(7, 41), None)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "data", "state.json")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "data", "demo", "state.json")))

    def test_switch_mode_changes_timing(self):
        self.assertEqual(self.app.config["OUT_DELAY"], 10)     # setUp = เดโม
        self.app.toggle_demo(False, at(7, 40))
        self.assertEqual(self.app.config["OUT_DELAY"], self.app.base_config["OUT_DELAY"])
        self.assertFalse(self.app.config.get("ALERT_EVERY_EXIT"))
        self.assertIs(self.app.guard.config, self.app.config)  # guard เห็นค่าใหม่ทันที
        self.app.toggle_demo(True, at(7, 41))
        self.assertTrue(self.app.config["ALERT_EVERY_EXIT"])

    def test_demo_back_to_real_at_night(self):
        # ลืมปิดโหมดเดโม -> ตี 3 กลับเป็นใช้งานจริงเอง
        self.app.handle([{"do": "new_day"}], at(3, 1, day=27))
        self.assertFalse(self.app.demo)

    def test_new_items_after_alert(self):
        # เตือนไปแล้ว -> ฝนเพิ่งมา -> ออกซ้ำ: ส่งเฉพาะ "ร่ม" ที่เพิ่มมา
        class FakeRain:
            fake = None
            prob = 0

            def rain_prob(self, key, now, hours):
                return self.prob

        self.app.weather = FakeRain()
        self.app.handle([{"do": "checklist"}], at(7, 40))     # ตอนนั้นยังไม่มีฝน
        self.assertNotIn("ร่ม", self.app.alerted_items)
        self.app.weather.prob = 80
        self.app.handle([{"do": "skip", "why": "เตือนไปแล้วในช่วงนี้", "code": "window"}],
                        at(8, 0))
        self.assertIn("alert_new,0,ร่ม", self.events_on_disk())
        # ออกอีกรอบ ไม่มีของใหม่แล้ว -> ไม่ส่งซ้ำ
        self.app.handle([{"do": "skip", "why": "เตือนไปแล้วในช่วงนี้", "code": "window"}],
                        at(8, 30))
        self.assertEqual(self.events_on_disk().count("alert_new"), 1)

    def test_status_in_thai(self):
        status = self.say("/status")
        self.assertIn("อยู่ห้อง", status)
        self.assertNotIn("HOME", status)

    def test_prep_message(self):
        # เช็คลิสต์ล่วงหน้า: หัวข้อบอกว่าเตรียมของอะไร อีกกี่นาที + ของที่ต้องพก
        sent = []
        self.app.notify = lambda text, silent=False, buttons=None: sent.append(text)
        self.app.handle([{"do": "prep", "time": "08:40", "name": "สอบย่อย"}], at(7, 40))
        self.assertTrue(sent[0].startswith("🎒 เตรียมของ · สอบย่อย 08:40 (อีก 60 นาที)"))
        self.assertIn("กุญแจห้อง", sent[0])
        self.assertIn("prep", self.events_on_disk())

    def test_door_duplicate_ignored(self):
        self.app.door_event("open", at(7, 40))
        self.app.door_event("open", at(7, 40, 1))             # กดซ้ำ
        self.assertEqual(self.events_on_disk().count("door_open"), 1)


if __name__ == "__main__":
    unittest.main()
