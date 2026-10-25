# เทสต์เมนูปุ่มซ้อนชั้น + ถามทีละขั้น (pc/bot.py) · ใช้ App ในโฟลเดอร์ชั่วคราว
import unittest

from pc import storage
from tests.test_app import AppFixture, at

MID = 42    # message_id ของเมนูที่ถูกกด (ปลอม)


def buttons_data(out):
    # data ของทุกปุ่มใน out
    return [data for row in (out.get("buttons") or []) for label, data in row]


def buttons_label(out):
    return [label for row in (out.get("buttons") or []) for label, data in row]


class TestBot(AppFixture):

    def text(self, text, now=None):
        return self.app.bot.on_text(text, now or at(7, 40))

    def press(self, data, now=None, message_text=""):
        return self.app.bot.on_button(data, MID, message_text, now or at(7, 40))

    def add_appt_until_items(self, day="2026-10-27", hour="17", name_button="an:0"):
        self.press("a:new")
        self.press("ad:" + day)
        self.press("ah:" + hour)
        return self.press(name_button)[0]

    # ----- โครงเมนู -----

    def test_main_buttons_open_menus(self):
        out = self.text("นัด")[0]
        self.assertIn("send", out)                       # ปุ่มล่าง = ส่งเมนูใหม่
        self.assertEqual(buttons_data(out), ["m:appts", "a:new", "m:appdel", "m:names"])
        out = self.text("ประจำสัปดาห์")[0]                 # ปุ่มล่างแยกจากนัด
        self.assertIn("send", out)
        self.assertIn("wk:new", buttons_data(out))
        out = self.text("ของ")[0]
        self.assertEqual(buttons_data(out), ["m:iview", "m:iadd", "m:idel"])

    def test_menu_edits_same_message_and_back(self):
        out = self.press("m:list")[0]
        self.assertEqual(out["edit"], MID)               # ปุ่มเมนู = แก้ข้อความเดิม
        self.assertIn("m:list", buttons_data(self.press("m:lday")[0]))   # มีปุ่มกลับ
        self.assertIn("กุญแจห้อง", self.press("l:2026-10-27")[0]["text"])

    def test_menu_word_brings_keyboard_back(self):
        # ปุ่มล่างหาย: พิมพ์ เมนู / /menu / ปุ่ม -> ข้อความธรรมดา (ไม่มีปุ่มติดข้อความ = แนบปุ่มล่าง)
        for word in ["เมนู", "/menu", "/MENU", "ปุ่ม"]:
            out = self.text(word)[0]
            self.assertIn("ปุ่มเมนูกลับมาแล้ว", out["send"])
            self.assertIsNone(out["buttons"])
        self.press("a:new")
        self.text("เมนู")
        self.assertIsNone(self.app.bot.wizard)                # ยกเลิกที่ถามค้างด้วย

    def test_no_emoji_in_buttons(self):
        # ปุ่มทุกหน้าเป็นตัวหนังสือล้วน ไม่ใส่อีโมจิ (อ่านง่าย ไม่รก · ยกเว้น ✓ ตอนเลือกของ)
        pages = ["m:list", "m:lday", "m:appt", "m:appts", "m:appdel", "m:items", "m:iview",
                 "m:iadd", "m:adday", "m:idel", "m:delalw", "m:delday", "m:acts", "m:wkdel", "m:wkskip",
                 "m:names", "m:apadd", "m:wkadd", "m:apdel", "m:wkidel", "m:wkview",
                 "m:other", "m:clear", "sa:2026-10-26", "d:2026-10-26"]
        for data in pages:
            for label in buttons_label(self.press(data)[0]):
                for ch in label:
                    self.assertLess(ord(ch), 0x2190, data + " -> " + label)

    # ----- เพิ่มนัด -----

    def test_add_appointment_by_buttons(self):
        # วัน -> ชม. -> กิจกรรมเดิม (ของเลือกไว้ให้แล้ว) -> บันทึก
        out = self.add_appt_until_items()
        self.assertIn("ชุดบอล", out["text"])
        self.assertIn("ai:done", buttons_data(out))
        out = self.press("ai:done")[0]
        self.assertIn("บันทึกนัดแล้ว", out["text"])
        self.assertIn("x:a:2026-10-27:0:1700", buttons_data(out))  # ปุ่มยกเลิกนัดนี้
        self.assertIn("d:2026-10-27", buttons_data(out))           # ปุ่มแก้ของ -> หน้าของวันนั้น
        appt = self.rules_on_disk()["appointments"]["2026-10-27"][0]
        self.assertEqual((appt["time"], appt["name"]), ("17:00", "ซ้อมบอล"))
        self.assertIn("ชุดบอล", appt["items"])
        self.assertNotIn("2026-10-27", self.rules_on_disk()["by_date"])   # ไม่เก็บซ้ำ

    def test_new_event_suggest_and_choose_items(self):
        # นัดใหม่ "หาหมอฟัน" -> เดาของจาก suggestions.json -> กดเลือก + พิมพ์เพิ่ม -> จำกิจกรรมไว้
        self.press("a:new")
        self.press("ad:2026-10-27")
        self.press("ah:10")
        out = self.text("หาหมอฟัน")[0]
        self.assertIn("บัตรประชาชน", buttons_label(out))  # เดาจากคำว่า หมอ / ฟัน
        self.assertIn("ยังไม่ได้เลือก", out["send"])
        out = self.press("ai:0")[0]                         # เลือกชิ้นแรก
        self.assertIn("✓ บัตรประชาชน", buttons_label(out))
        self.text("ใบนัด, ยาที่กินอยู่")                     # พิมพ์ของเพิ่มเอง
        out = self.press("ai:done")[0]
        appt = self.rules_on_disk()["appointments"]["2026-10-27"][0]
        self.assertEqual(appt["items"], ["บัตรประชาชน", "ใบนัด", "ยาที่กินอยู่"])
        # ระบบจำชื่อนัด + ของไว้เอง (ไม่ต้องกด) ครั้งหน้ามีปุ่มชื่อนี้ให้เลือก
        self.assertNotIn("r:2026-10-27:0:1000", buttons_data(out))
        self.assertEqual(storage.load_json("activities.json")["หาหมอฟัน"],
                         ["บัตรประชาชน", "ใบนัด", "ยาที่กินอยู่"])

    def test_items_limit(self):
        # พิมพ์ของ 15 ชิ้น -> รับแค่ 10 และบอกว่าเต็ม (ไม่เงียบ)
        self.press("a:new")
        self.press("ad:2026-10-27")
        self.press("ah:10")
        self.text("นัดใหม่")
        out = self.text(", ".join("ของ" + str(i) for i in range(15)))[0]
        self.assertIn("ครบ 10 ชิ้น", out["send"])
        self.assertEqual(len(self.app.bot.wizard["chosen"]), 10)
        self.assertLessEqual(len(buttons_data(out)), 20)
        # เพิ่มของทุกวันครั้งละเกิน 10 ก็ไม่รับ
        self.press("w:always")
        self.assertIn("ไม่เกิน 10", self.text(", ".join("x" + str(i) for i in range(11)))[0]["send"])

    def test_recent_activities_only(self):
        # จำไว้ 8 กิจกรรม -> ขั้นเลือกชื่อแสดง 6 อันล่าสุด ล่าสุดอยู่ก่อน
        for i in range(8):
            self.app.remember_activity("กิจกรรม" + str(i), ["ของ"])
        self.press("a:new")
        self.press("ad:2026-10-27")
        out = self.press("ah:10")[0]
        names = [label for label in buttons_label(out) if label != "ยกเลิก"]
        self.assertEqual(names, ["กิจกรรม7", "กิจกรรม6", "กิจกรรม5",
                                 "กิจกรรม4", "กิจกรรม3", "กิจกรรม2"])
        self.press("an:5")                                   # กด กิจกรรม2 -> ขึ้นเป็นล่าสุดหลังบันทึก
        self.press("ai:done")
        self.assertEqual(self.app.bot.recent_activities()[0], "กิจกรรม2")

    # ----- กิจกรรมประจำ (ซ้ำทุกสัปดาห์) -----

    def add_weekly_ml(self):
        # เรียน ML ทุกจันทร์ 09:00 พกโน้ตบุ๊ก (ผ่านปุ่มทั้งหมด + พิมพ์ชื่อ/ของ)
        self.press("wk:new")
        self.press("wd:mon")
        self.press("ah:09")
        self.text("เรียน ML")
        self.text("โน้ตบุ๊ก")
        return self.press("ai:done")[0]

    def test_weekly_own_menu(self):
        # ประจำสัปดาห์ มีปุ่มล่างของตัวเอง แยกจากนัด (นัด = ครั้งเดียว)
        from pc.telegram import MAIN_BUTTONS
        self.assertIn("ประจำสัปดาห์", [b for row in MAIN_BUTTONS for b in row])
        self.assertNotIn("m:acts", buttons_data(self.text("นัด")[0]))
        # หน้าตาเหมือนเมนูนัด: ดู / เพิ่ม / ลบ + งดบางสัปดาห์
        self.assertEqual(buttons_data(self.press("m:acts")[0]),
                         ["m:wkview", "wk:new", "m:wkdel", "m:wkskip"])
        out = self.press("m:wkview")[0]
        self.assertIn("ยังไม่มีกิจกรรมประจำ", out["text"])
        self.assertIn("wk:new", buttons_data(out))

    def test_add_weekly_by_buttons(self):
        out = self.add_weekly_ml()
        self.assertIn("บันทึกกิจกรรมประจำแล้ว", out["text"])
        self.assertIn("ทุกจันทร์", out["text"])
        self.assertEqual(self.rules_on_disk()["weekly"],
                         [{"day": "mon", "time": "09:00", "name": "เรียน ML",
                           "items": ["โน้ตบุ๊ก"]}])
        page = self.press("m:wkview")[0]["text"]               # ดูทีละวัน จันทร์-อาทิตย์
        self.assertIn("จันทร์:\n- 09:00  เรียน ML (พก โน้ตบุ๊ก)", page)
        self.assertIn("อังคาร: -", page)

    def test_add_weekly_typed_day_and_time(self):
        self.press("wk:new")
        self.text("ทุกวันพุธ")
        self.text("13.30")
        self.text("เรียน IoT")
        self.press("ai:done")
        entry = self.rules_on_disk()["weekly"][0]
        self.assertEqual((entry["day"], entry["time"], entry["name"]), ("wed", "13:30", "เรียน IoT"))
        self.press("wk:new")
        self.assertIn("ไม่เข้าใจวัน", self.text("พรุ่งนี้")[0]["send"])   # ต้องเป็นชื่อวัน

    def test_weekly_counts_as_appointment(self):
        # จันทร์ 2/11 (สัปดาห์หน้า) มีเรียน ML -> เช็คลิสต์มีโน้ตบุ๊ก (เรียน ML) + guard มีช่วงเตือน
        self.add_weekly_ml()
        page = self.press("l:2026-11-02")[0]["text"]
        self.assertIn("09:00  เรียน ML  (ประจำ)", page)
        self.assertIn("โน้ตบุ๊ก  (เรียน ML)", page)
        tup = (2026, 11, 2, 8, 0, 0, 0)
        self.assertIn((450, 540), self.app.guard.windows(tup))        # 07:30-09:00
        self.assertEqual(self.app.guard.events_today(tup)[-1], (540, "09:00", "เรียน ML"))
        self.assertNotIn("เรียน ML", self.press("l:2026-11-03")[0]["text"])   # อังคารไม่มี

    def test_skip_one_week(self):
        # สัปดาห์ไหนไม่มีเรียน: งดเฉพาะครั้งนั้น ครั้งอื่นยังอยู่ · กดซ้ำ = ยกเลิกงด
        self.add_weekly_ml()
        out = self.press("m:wkskip")[0]
        self.assertIn("ws:2026-11-02:0:1", buttons_data(out))
        out = self.press("ws:2026-11-02:0:1")[0]
        self.assertIn("งดแล้ว", out["text"])
        self.assertIn("(งดแล้ว)", " ".join(buttons_label(out)))
        self.assertEqual(self.rules_on_disk()["weekly_skip"], {"2026-11-02": ["09:00 เรียน ML"]})
        self.assertNotIn("โน้ตบุ๊ก  (เรียน ML)", self.press("l:2026-11-02")[0]["text"])
        self.assertNotIn((450, 540), self.app.guard.windows((2026, 11, 2, 8, 0, 0, 0)))
        self.assertIn("โน้ตบุ๊ก  (เรียน ML)", self.press("l:2026-11-09")[0]["text"])
        self.assertIn("งดไว้", self.press("m:wkview")[0]["text"])
        self.press("ws:2026-11-02:0:1")                                  # ยกเลิกงด
        self.assertEqual(self.rules_on_disk()["weekly_skip"], {})

    def test_weekly_items_add_and_delete(self):
        # ของ > เพิ่มของ > ของสำหรับประจำสัปดาห์ > เลือกกิจกรรม > เลือก/พิมพ์ของ
        self.add_weekly_ml()
        self.assertIn("wi:0:1", buttons_data(self.press("m:wkadd")[0]))
        out = self.press("wi:0:1")[0]
        self.assertIn("มีอยู่แล้ว: โน้ตบุ๊ก", out["text"])
        self.text("ปากกา, เครื่องคิดเลข")
        out = self.press("ai:done")[0]
        self.assertIn("เพิ่มของให้", out["text"])
        self.assertEqual(self.rules_on_disk()["weekly"][0]["items"],
                         ["โน้ตบุ๊ก", "ปากกา", "เครื่องคิดเลข"])
        # ดูของ: แยกหัวข้อ
        view = self.press("m:iview")[0]["text"]
        self.assertIn("# ของสำหรับประจำสัปดาห์\n- ทุกจันทร์ 09:00 เรียน ML: โน้ตบุ๊ก, ปากกา", view)
        # ลบ: ของ > ลบของ > ของสำหรับประจำสัปดาห์ > เลือกกิจกรรม > กดชิ้น
        self.assertIn("wx:0:1", buttons_data(self.press("m:wkidel")[0]))
        out = self.press("wx:0:1")[0]
        self.assertIn("x:wi:0:1:3", buttons_data(out))
        self.press("x:wi:0:1:3")                                         # ลบ ปากกา
        self.assertEqual(self.rules_on_disk()["weekly"][0]["items"], ["โน้ตบุ๊ก", "เครื่องคิดเลข"])
        self.assertIn("รายการเปลี่ยน", self.press("x:wi:0:1:3")[0]["text"])

    def test_remembered_names_page(self):
        # ชื่อนัดที่เคยใช้: ระบบจำเองตอนบันทึกนัด · ลบชื่อได้ นัดยังอยู่
        self.app.add_appointment("2026-10-27", "17:00", "ซ้อมบอล", ["ชุดบอล"])
        out = self.press("m:names")[0]
        self.assertIn("ซ้อมบอล", buttons_label(out))
        self.assertIn("x:t:0:1", buttons_data(out))
        self.press("x:t:0:1")
        self.assertNotIn("ซ้อมบอล", storage.load_json("activities.json"))
        self.assertIn("2026-10-27", self.rules_on_disk()["appointments"])
        self.assertIn("ยังไม่มีนัดที่บันทึกไว้", self.press("m:names")[0]["text"])

    def test_weekly_name_not_mixed_with_appointments(self):
        # เพิ่มกิจกรรมประจำ ไม่เอาชื่อไปปนกับชื่อนัด และขั้นตั้งชื่อไม่โชว์ชื่อนัด
        self.press("wk:new")
        self.press("wd:mon")
        out = self.press("ah:09")[0]
        self.assertEqual(buttons_data(out), ["w:cancel"])
        self.text("เรียน ML")
        self.press("ai:done")
        self.assertNotIn("เรียน ML", storage.load_json("activities.json"))

    def test_delete_weekly(self):
        self.add_weekly_ml()
        out = self.press("m:wkdel")[0]
        self.assertIn("x:w:0:1", buttons_data(out))
        out = self.press("x:w:0:1")[0]
        self.assertIn("ลบแล้ว", out["text"])
        self.assertEqual(self.rules_on_disk()["weekly"], [])
        self.assertIn("รายการเปลี่ยนไปแล้ว", self.press("x:w:0:1")[0]["text"])   # ปุ่มเก่า

    def test_old_skip_dates_cleaned(self):
        self.add_weekly_ml()
        self.press("ws:2026-11-02:0:1")
        self.app.clean_old_dates((0, (2026, 11, 3, 8, 0, 0, 1)))
        self.assertEqual(self.rules_on_disk()["weekly_skip"], {})

    def test_toggle_item_off(self):
        self.add_appt_until_items()                         # ซ้อมบอล: เลือกไว้ 3 ชิ้น
        self.press("ai:0")                                  # เอาชิ้นแรกออก
        self.press("ai:done")
        appt = self.rules_on_disk()["appointments"]["2026-10-27"][0]
        self.assertEqual(len(appt["items"]), 2)

    def test_add_appointment_by_typing_answers(self):
        # ตอบคำถามด้วยการพิมพ์แทนปุ่มก็ได้ · พิมพ์ผิดถามซ้ำ
        self.press("a:new")
        self.assertIn("ไม่เข้าใจวันที่", self.text("เมื่อไรก็ได้")[0]["send"])
        self.text("วันศุกร์")
        self.assertIn("ไม่เข้าใจเวลา", self.text("บ่าย 15")[0]["send"])   # 27:00 ไม่รับ
        self.text("บ่าย2ครึ่ง")
        self.text("ประชุม")
        self.press("ai:done")
        appt = self.rules_on_disk()["appointments"]["2026-10-30"][0]
        self.assertEqual((appt["time"], appt["name"]), ("14:30", "ประชุม"))

    def test_today_hides_past_hours(self):
        # วันนี้ 07:40 -> ปุ่มเริ่มที่ 08 · พิมพ์/กดเวลาที่ผ่านแล้ว = ไม่รับ
        self.press("a:new")
        out = self.press("ad:2026-10-26")[0]
        hours = [d for d in buttons_data(out) if d.startswith("ah:")]
        self.assertEqual(hours[0], "ah:08")
        self.assertIn("ผ่านไปแล้ว", self.text("7.00")[0]["send"])
        self.assertIn("ผ่านไปแล้ว", self.press("ah:07")[0]["text"])
        # ดึกแล้ว ไม่มีปุ่มชั่วโมงเหลือ -> บอกให้พิมพ์เอง
        self.press("a:new", at(22, 30))
        out = self.press("ad:2026-10-26", at(22, 30))[0]
        self.assertIn("พิมพ์เวลาเอง", out["text"])

    def test_wizard_cancel_and_timeout(self):
        self.press("a:new")
        self.assertEqual(self.press("w:cancel")[0]["text"], "ยกเลิกแล้ว")
        self.assertIsNone(self.app.bot.wizard)
        # ถามค้างเกิน 5 นาที -> ข้อความที่พิมพ์ถือเป็นคำสั่งปกติ
        self.press("a:new")
        self.assertIn("สถานะ", self.text("/status", at(7, 50))[0]["send"])
        self.assertIsNone(self.app.bot.wizard)

    def test_old_wizard_button_expired(self):
        self.assertIn("หมดอายุ", self.press("ah:17")[0]["text"])

    def test_main_button_cancels_wizard(self):
        self.press("a:new")
        self.text("เช็คลิสต์")
        self.assertIsNone(self.app.bot.wizard)

    # ----- ดู / ลบนัด -----

    def test_view_and_delete_appointments(self):
        self.app.add_appointment("2026-10-27", "08:00", "สอบ", [])
        self.app.add_appointment("2026-10-28", "09:00", "ประชุม", [])
        out = self.press("m:appts")[0]
        self.assertIn("สอบ", out["text"])
        self.assertNotIn("x:a:2026-10-27:0:0800", buttons_data(out))  # หน้าดู ไม่มีปุ่มลบ
        out = self.press("m:appdel")[0]
        self.assertIn("x:a:2026-10-27:0:0800", buttons_data(out))
        self.press("x:a:2026-10-27:0:0800")
        self.assertNotIn("2026-10-27", self.rules_on_disk()["appointments"])
        self.assertIn("x:aall!", buttons_data(self.press("x:aall")[0]))   # ถามยืนยัน
        self.assertIn("2026-10-28", self.rules_on_disk()["appointments"])
        self.press("x:aall!")
        self.assertEqual(self.rules_on_disk()["appointments"], {})

    # ----- ดู / เพิ่ม / ลบของ -----

    def test_view_items(self):
        text = self.press("m:iview")[0]["text"]
        self.assertIn("กุญแจห้อง", text)
        self.assertIn("ของวันนี้", text)                    # by_date ของวันที่ 26

    def test_add_and_delete_always_items(self):
        self.press("w:always")
        self.text("ร่ม, ยาดม")
        self.assertEqual(self.rules_on_disk()["always"], ["กุญแจห้อง", "ร่ม", "ยาดม"])
        out = self.press("m:delalw")[0]
        self.assertIn("x:i:1:3", buttons_data(out))
        self.press("x:i:1:3")                               # ลบ ร่ม
        self.assertEqual(self.rules_on_disk()["always"], ["กุญแจห้อง", "ยาดม"])
        # ปุ่มเก่า (ตอนมี 3 ชิ้น) -> รายการเปลี่ยนแล้ว ไม่ลบผิดชิ้น
        self.assertIn("รายการเปลี่ยน", self.press("x:i:1:3")[0]["text"])

    def test_day_items_add_and_delete(self):
        # ของ > เพิ่มของ > เฉพาะวัน > เลือกวัน > ทั้งวัน หรือนัดในวันนั้น (ลบของไม่ไปลบนัด)
        self.app.add_appointment("2026-10-27", "17:00", "ซ้อมบอล", ["ชุดบอล"])
        out = self.press("m:iadd")[0]                          # แยก 4 แบบ
        for page in ["w:always", "m:adday", "m:apadd", "m:wkadd"]:
            self.assertIn(page, buttons_data(out))
        self.assertIn("w:date:2026-10-27", buttons_data(self.press("m:adday")[0]))   # พกทั้งวัน
        self.assertIn("w:appt:2026-10-27:0:1700", buttons_data(self.press("m:apadd")[0]))
        out = self.press("sa:2026-10-27")[0]                   # วันนั้นมีนัด -> ถามว่าให้อะไร
        self.assertIn("w:date:2026-10-27", buttons_data(out))
        self.assertIn("w:appt:2026-10-27:0:1700", buttons_data(out))
        # วันที่ไม่มีนัด -> ถามชื่อของเลย
        self.assertIn("พิมพ์ชื่อของ", self.press("sa:2026-10-28")[0]["text"])
        # ใส่ของให้นัด: กดของที่เดา / พิมพ์ -> บันทึก
        out = self.press("w:appt:2026-10-27:0:1700")[0]
        self.assertIn("มีอยู่แล้ว: ชุดบอล", out["text"])
        self.assertIn("รองเท้า", buttons_label(out))          # เดาจากกิจกรรมซ้อมบอล (ยังไม่มี)
        self.assertNotIn("ชุดบอล", buttons_label(out))        # มีแล้ว ไม่เสนอซ้ำ
        self.press("ai:0")
        self.text("ร่ม")
        self.press("ai:done")
        items = self.rules_on_disk()["appointments"]["2026-10-27"][0]["items"]
        self.assertEqual(items, ["ชุดบอล", "รองเท้า", "ร่ม"])
        # ทั้งวัน: ร่มกันฝน
        self.press("w:date:2026-10-27")
        self.text("เสื้อกันฝน")
        # ลบ: เลือกวัน -> เห็นของทั้งวัน + ของของนัดในหน้าเดียว -> กดชิ้นที่จะลบ
        self.assertIn("d:2026-10-27", buttons_data(self.press("m:delday")[0]))
        out = self.press("d:2026-10-27")[0]
        self.assertIn("ทั้งวัน: เสื้อกันฝน", out["text"])
        self.assertIn("17:00 ซ้อมบอล: ชุดบอล, รองเท้า, ร่ม", out["text"])
        self.assertIn("x:d:2026-10-27:0:1", buttons_data(out))
        self.assertIn("x:p:2026-10-27:0:1700:0:3", buttons_data(out))
        self.press("x:p:2026-10-27:0:1700:0:3")                # ลบ ชุดบอล
        appt = self.rules_on_disk()["appointments"]["2026-10-27"][0]
        self.assertEqual(appt["items"], ["รองเท้า", "ร่ม"])     # นัดยังอยู่ ลบแค่ของ
        self.assertIn("รายการเปลี่ยน", self.press("x:p:2026-10-27:0:1700:0:3")[0]["text"])
        # เช็คลิสต์: ของทั้งวันเขียนว่า (ทั้งวัน) · ของของนัดเขียนชื่อนัด
        page = self.press("l:2026-10-27")[0]["text"]
        self.assertIn("เสื้อกันฝน  (ทั้งวัน)", page)
        self.assertIn("รองเท้า  (ซ้อมบอล)", page)

    def test_clear_menu_in_other(self):
        # ปุ่มเคลียร์อยู่ในเมนู อื่น ๆ เท่านั้น · ถามยืนยันก่อน
        self.assertIn("m:clear", buttons_data(self.press("m:other")[0]))
        for page in ["m:appt", "m:appdel", "m:items", "m:idel", "m:delalw", "m:delday"]:
            self.assertFalse([d for d in buttons_data(self.press(page)[0])
                              if d in ["x:aall", "x:call", "x:cdall", "x:tall"]], page)
        self.app.add_appointment("2026-10-27", "17:00", "ซ้อมบอล", ["ชุดบอล"])
        out = self.press("x:call")[0]
        self.assertIn("x:call!", buttons_data(out))
        self.assertEqual(self.rules_on_disk()["always"], ["กุญแจห้อง"])   # ยังไม่ลบจนกดยืนยัน
        self.press("x:call!")
        self.assertEqual(self.rules_on_disk()["always"], [])
        self.press("x:cdall!")                                 # ของเฉพาะวันหาย นัดยังอยู่
        rules = self.rules_on_disk()
        self.assertEqual(rules["by_date"], {})
        self.assertEqual(rules["appointments"]["2026-10-27"][0]["items"], [])
        self.app.add_weekly("mon", "09:00", "เรียน ML", [])
        self.press("x:tall!")                                  # กิจกรรมประจำ (ทุกสัปดาห์) หาย
        self.assertEqual(self.rules_on_disk()["weekly"], [])
        self.press("x:aall!")
        self.assertEqual(self.rules_on_disk()["appointments"], {})

    def test_appointment_items_limit_counts_existing(self):
        # มีของอยู่แล้ว 9 ชิ้น -> เพิ่มได้อีกแค่ 1
        self.app.add_appointment("2026-10-27", "17:00", "นัด", ["x" + str(i) for i in range(9)])
        self.press("w:appt:2026-10-27:0:1700")
        out = self.text("a, b")[0]
        self.assertIn("ครบ 10 ชิ้น", out["send"])
        self.press("ai:done")
        self.assertEqual(len(self.rules_on_disk()["appointments"]["2026-10-27"][0]["items"]), 10)

    def test_long_list_capped(self):
        # ของทุกวัน 60 ชิ้น -> หน้าลบแสดงแค่ 40 ปุ่ม + บอกว่ามีอีก
        for i in range(60):
            self.app.add_always("ของ" + str(i))
        out = self.press("m:delalw")[0]
        self.assertLessEqual(len(buttons_data(out)), 41)
        self.assertIn("แสดง 40 อันแรก", out["text"])

    def test_add_and_delete_date_items(self):
        self.press("w:date:2026-10-27")
        self.text("ชุดว่ายน้ำ")
        self.assertEqual(self.rules_on_disk()["by_date"]["2026-10-27"], ["ชุดว่ายน้ำ"])
        self.assertIn("d:2026-10-27", buttons_data(self.press("m:delday")[0]))
        self.press("x:d:2026-10-27:0:1")
        self.assertNotIn("2026-10-27", self.rules_on_disk()["by_date"])

    # ----- อื่น ๆ / ปุ่มใต้ข้อความเตือน -----

    def test_no_alert_and_turn_back_on(self):
        out = self.press("o:noalert")[0]
        self.assertTrue(self.app.guard.no_alert)
        self.assertIn("o:alerton", buttons_data(out))       # มีปุ่มเปิดเตือนกลับ
        self.assertIn("o:alerton", buttons_data(self.press("m:other")[0]))
        self.press("o:alerton")
        self.assertFalse(self.app.guard.no_alert)
        self.assertIn("o:noalert", buttons_data(self.press("m:other")[0]))
        self.assertIn("เปิดเตือน", self.text("เปิดเตือน")[0]["send"])   # พิมพ์ก็ได้

    def test_demo_toggle_button(self):
        # setUp = เดโม -> ปุ่มปิดได้ทันที · เปิดต้องยืนยันก่อน
        self.assertIn("โหมดเดโม: เปิด", buttons_label(self.press("m:other")[0]))
        self.press("o:demo")
        self.assertFalse(self.app.demo)
        out = self.press("o:demo")[0]
        self.assertIn("o:demo!", buttons_data(out))
        self.assertFalse(self.app.demo)                       # ยังไม่เปิดจนกดยืนยัน
        self.press("o:demo!")
        self.assertTrue(self.app.demo)
        self.assertIn("โหมด: เดโม", self.press("o:status")[0]["text"])

    def test_alert_buttons_fix_state(self):
        self.app.guard.force_out(at(7, 40))
        out = self.press("o:home", message_text="ออกจากห้องแล้ว")[0]
        self.assertEqual(self.app.guard.state, "HOME")
        self.assertIsNone(out["buttons"])                # เอาปุ่มออก กันกดซ้ำ
        self.assertIn("แก้แล้ว", out["text"])
        self.press("o:out")
        self.assertEqual(self.app.guard.state, "OUT")

    def test_typing_still_works(self):
        self.assertIn("เพิ่ม", self.text("ลืมพัดลม")[0]["send"])
        self.assertIn("พัดลม", self.rules_on_disk()["always"])

    def test_all_button_data_short(self):
        # Telegram จำกัด callback_data 64 byte
        self.app.add_appointment("2026-10-27", "08:00", "ชื่อนัดยาวมากมากมากมากมาก", [])
        pages = ["m:list", "m:lday", "m:appt", "m:appts", "m:appdel", "m:items", "m:iview",
                 "m:iadd", "m:adday", "m:idel", "m:delalw", "m:delday", "m:other",
                 "a:new", "d:2026-10-26"]
        for data in pages:
            for button in buttons_data(self.press(data)[0]):
                self.assertLessEqual(len(button.encode("utf-8")), 64, button)


if __name__ == "__main__":
    unittest.main()
