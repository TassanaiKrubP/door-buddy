# เทสต์ขั้น 2: DoorGuard (เวลาจำลองทั้งหมด)
import unittest

from core.guard import DoorGuard, HOME, DOOR_OPEN, MAYBE_OUT, OUT, ENTERING, next_day

CONFIG = {
    "OUT_DELAY": 120,
    "COOLDOWN_MIN": 180,
    "BEFORE_CLASS_MIN": 90,
    "NO_CLASS_WINDOW": ["08:00", "11:00"],
    "OUTSIDE_WINDOW": "none",
    "NIGHT_RESET": "03:00",
    "OPEN_ALERT_SEC": 180,
}

# จันทร์ 26 ต.ค. มีเรียน 09:00 -> ช่วงเตือน 07:30-09:00
TIMETABLE = [{"day": "mon", "start": "09:00", "end": "12:00", "subject": "วิชา A"}]


def at(h, m, s=0, day=26):
    # สร้าง now = (epoch, tup) จำลอง: day 26 = จันทร์, 27 = อังคาร
    epoch = day * 86400 + h * 3600 + m * 60 + s
    return (epoch, (2026, 10, day, h, m, s, day - 26))


def kinds(actions):
    # เอาแค่ชนิด action (checklist / short_msg / log)
    return [a["do"] for a in actions]


def events(actions):
    # เอาแค่ชื่อเหตุการณ์ log
    return [a["event"] for a in actions if a["do"] == "log"]


def whys(actions):
    # เอาแค่เหตุผลที่ไม่เตือน
    return [a["why"] for a in actions if a["do"] == "skip"]


def leave(guard, h, m, s=0, day=26):
    # เปิด-ปิดประตูที่เวลา h:m:s (ปิดตอน +5 วิ) คืน action ทั้งหมด
    actions = guard.on_door("open", at(h, m, s, day))
    actions += guard.on_door("close", at(h, m, s + 5, day))
    return actions


class TestGuard(unittest.TestCase):

    def setUp(self):
        self.g = DoorGuard(dict(CONFIG), TIMETABLE)

    def test_short_trip_no_alert(self):
        # ออกแป๊บเดียว (กลับภายใน OUT_DELAY) -> ไม่เตือน
        leave(self.g, 7, 40)
        self.assertEqual(self.g.state, MAYBE_OUT)
        actions = self.g.on_door("open", at(7, 40, 30))
        self.assertNotIn("checklist", kinds(actions))
        self.assertEqual(events(actions), ["short_trip"])
        self.assertEqual(self.g.state, HOME)

    def test_real_exit_alert_once(self):
        # ออกจริง -> เตือนครั้งเดียวหลัง OUT_DELAY
        leave(self.g, 7, 40)
        self.assertEqual(self.g.tick(at(7, 41, 30)), [])        # ยังไม่ครบ
        self.assertEqual(kinds(self.g.tick(at(7, 42, 5))), ["checklist"])
        self.assertEqual(self.g.state, OUT)
        self.assertEqual(self.g.tick(at(7, 42, 6)), [])         # ไม่เตือนซ้ำ

    def test_return_no_alert(self):
        # กลับเข้าห้อง -> ไม่เตือน และบันทึก trip
        leave(self.g, 7, 40)
        self.g.tick(at(7, 43))
        actions = self.g.on_door("open", at(8, 0))
        self.assertEqual(self.g.state, ENTERING)
        actions += self.g.on_door("close", at(8, 0, 5))
        self.assertEqual(self.g.state, HOME)
        self.assertEqual(kinds(actions), ["log"])
        self.assertEqual(events(actions), ["trip"])

    def test_second_exit_after_return_alerts_again(self):
        # ออก 7:40 (เตือน) กลับ 7:50 ยังไม่ถึงคาบ 9:00 -> ออกรอบ 8:00 ต้องเตือนอีก
        # (เดิมไม่เตือน: ออกไปทำธุระก่อน แล้วตอนออกไปเรียนจริงเงียบ)
        leave(self.g, 7, 40)
        self.g.tick(at(7, 43))
        self.g.on_door("open", at(7, 50))
        self.g.on_door("close", at(7, 50, 5))
        leave(self.g, 8, 0)
        self.assertEqual(kinds(self.g.tick(at(8, 3))), ["checklist"])

    def test_buy_food_before_appointment(self):
        # นัด 7:30 ออกไปซื้อข้าว 6:30 กลับ 7:10 ออกไปนัด 7:20 -> เตือนทั้ง 2 รอบ
        appts = {"2026-10-27": [{"time": "07:30", "name": "นัด"}]}
        config = dict(CONFIG)
        config["COOLDOWN_MIN"] = 30
        g = DoorGuard(config, TIMETABLE, appts)
        leave(g, 6, 30, day=27)
        self.assertEqual(kinds(g.tick(at(6, 33, day=27))), ["checklist"])
        g.on_door("open", at(7, 10, day=27))
        g.on_door("close", at(7, 10, 5, day=27))
        leave(g, 7, 20, day=27)
        self.assertEqual(kinds(g.tick(at(7, 23, day=27))), ["checklist"])

    def test_return_after_window_end_no_rearm(self):
        # กลับห้องหลังคาบเริ่มแล้ว (ช่วง 7:30-9:00 จบ) แล้วออกอีก 10:00 -> นอกช่วง ไม่เตือน
        leave(self.g, 7, 40)
        self.g.tick(at(7, 43))
        self.g.on_door("open", at(9, 30))
        self.g.on_door("close", at(9, 30, 5))
        leave(self.g, 10, 0)
        self.assertEqual(whys(self.g.tick(at(10, 3))), ["นอกช่วงเตือน"])

    def test_leave_last_minute_uses_close_time(self):
        # คาบ 9:00 ออก 8:59 -> ยืนยันว่าออกตอน 9:01 (เลยช่วงแล้ว) แต่ปิดประตูก่อน 9:00 -> ต้องเตือน
        leave(self.g, 8, 59)
        self.assertEqual(kinds(self.g.tick(at(9, 1, 10))), ["checklist"])

    def test_overlap_appointment_does_not_eat_class(self):
        # จันทร์เรียน 9:00 + นัด 8:00 · ไปนัด 7:40 กลับ 8:20 ไปเรียน 8:40 -> เตือนทั้ง 2 รอบ
        appts = {"2026-10-26": [{"time": "08:00", "name": "นัด"}]}
        g = DoorGuard(dict(CONFIG), TIMETABLE, appts)
        leave(g, 7, 40)
        self.assertEqual(kinds(g.tick(at(7, 43))), ["checklist"])
        self.assertEqual(g.alerted_windows, [(390, 480)])        # นับเป็นช่วงของนัด 8:00
        g.on_door("open", at(8, 20))
        g.on_door("close", at(8, 20, 5))
        leave(g, 8, 40)
        self.assertEqual(kinds(g.tick(at(8, 43))), ["checklist"])

    def test_appointment_after_midnight(self):
        # นัด 00:30 วันพรุ่งนี้ ออก 23:40 คืนนี้ -> อยู่ในช่วงเตือน 23:00-00:30
        appts = {"2026-10-27": [{"time": "00:30", "name": "รับเพื่อน"}]}
        g = DoorGuard(dict(CONFIG), TIMETABLE, appts)
        leave(g, 23, 40)
        self.assertEqual(kinds(g.tick(at(23, 43))), ["checklist"])

    def prep_guard(self, appts=None):
        config = dict(CONFIG)
        config["PREP_MIN"] = 60
        return DoorGuard(config, TIMETABLE, appts or {})

    def test_prep_before_first_class_once(self):
        # จันทร์คาบแรก 9:00 -> 8:00 ส่งเช็คลิสต์ล่วงหน้า ครั้งเดียว
        g = self.prep_guard()
        self.assertEqual(g.tick(at(7, 59, 59)), [])
        self.assertEqual(g.tick(at(8, 0)), [{"do": "prep", "time": "09:00", "name": "วิชา A"}])
        self.assertEqual(g.tick(at(8, 0, 1)), [])
        self.assertEqual(g.tick(at(8, 30)), [])

    def test_prep_for_appointment(self):
        # อังคาร (ไม่มีเรียน) นัด 7:30 -> 6:30 ส่ง
        g = self.prep_guard({"2026-10-27": [{"time": "07:30", "name": "หาหมอ"}]})
        self.assertEqual(kinds(g.tick(at(6, 30, day=27))), ["prep"])

    def test_prep_late_start_still_sends(self):
        # เปิดโปรแกรม 8:40 (คาบ 9:00) -> ส่งทันที · เลยเวลาคาบแล้ว = ไม่ส่ง
        g = self.prep_guard()
        self.assertEqual(kinds(g.tick(at(8, 40))), ["prep"])
        g2 = self.prep_guard()
        self.assertEqual(g2.tick(at(9, 0)), [])

    def test_prep_skipped_when_out_or_no_alert(self):
        g = self.prep_guard()
        leave(g, 7, 40)
        g.tick(at(7, 43))                                        # ออกไปแล้ว
        self.assertNotIn("prep", kinds(g.tick(at(8, 0))))
        g2 = self.prep_guard()
        g2.set_no_alert()
        self.assertEqual(g2.tick(at(8, 0)), [])

    def test_prep_off_by_default_and_new_day(self):
        self.assertEqual(self.g.tick(at(8, 0)), [])               # ไม่มี PREP_MIN = ปิด
        g = self.prep_guard()
        g.tick(at(8, 0))
        g.tick(at(3, 1, day=27))                                  # วันใหม่
        g.tick(at(8, 0, day=27))                                  # อังคารไม่มีเรียน
        self.assertEqual(g.prepped, [])
        data = self.prep_guard()
        data.tick(at(8, 0))
        g3 = self.prep_guard()
        g3.load_dict(data.to_dict(), at(8, 10))                   # รีสตาร์ทโปรแกรม = ไม่ส่งซ้ำ
        self.assertEqual(g3.tick(at(8, 10)), [])

    def test_next_day(self):
        self.assertEqual(next_day((2026, 10, 26)), (2026, 10, 27))
        self.assertEqual(next_day((2026, 10, 31)), (2026, 11, 1))
        self.assertEqual(next_day((2026, 12, 31)), (2027, 1, 1))
        self.assertEqual(next_day((2028, 2, 28)), (2028, 2, 29))   # ปีอธิกสุรทิน
        self.assertEqual(next_day((2026, 2, 28)), (2026, 3, 1))

    def test_still_home_rearms_but_cooldown_holds(self):
        # เตือนผิด -> กด "ยังไม่ได้ออก" -> ออกจริงทีหลังยังเตือนได้ แต่ไม่ภายใน cooldown
        config = dict(CONFIG)
        config["COOLDOWN_MIN"] = 30
        g = DoorGuard(config, TIMETABLE)
        leave(g, 7, 40)
        g.tick(at(7, 43))
        g.still_home(at(7, 44))
        leave(g, 7, 50)
        self.assertEqual(whys(g.tick(at(7, 53))), ["ยังไม่ครบ cooldown"])
        g.still_home(at(7, 54))
        leave(g, 8, 20)
        self.assertEqual(kinds(g.tick(at(8, 23))), ["checklist"])

    def test_normal_return_no_quiet_checklist(self):
        # กลับห้องปกติในช่วงเตือนที่ยังไม่เตือน -> ไม่ส่งเช็คลิสต์เงียบ (ส่งเฉพาะวันที่อาจกลับด้าน)
        appts = {"2026-10-26": [{"time": "18:00", "name": "นัด"}]}
        g = DoorGuard(dict(CONFIG), TIMETABLE, appts)
        leave(g, 12, 0)
        g.tick(at(12, 3))
        g.on_door("open", at(17, 0))
        self.assertEqual(kinds(g.on_door("close", at(17, 0, 5))), ["log"])

    def test_no_alert_today(self):
        # สั่งไม่ต้องเตือน -> ไม่เตือน
        self.g.set_no_alert()
        leave(self.g, 7, 40)
        self.assertEqual(kinds(self.g.tick(at(7, 43))), ["skip"])

    def test_outside_window_none(self):
        # นอกช่วงเตือน + OUTSIDE_WINDOW = none -> ไม่ส่งอะไร (บอกแค่เหตุผล)
        leave(self.g, 12, 0)
        self.assertEqual(whys(self.g.tick(at(12, 3))), ["นอกช่วงเตือน"])

    def test_outside_window_silent_short(self):
        # นอกช่วงเตือน + silent_short -> ข้อความบรรทัดเดียว
        self.g.config["OUTSIDE_WINDOW"] = "silent_short"
        leave(self.g, 12, 0)
        self.assertEqual(kinds(self.g.tick(at(12, 3))), ["short_msg"])

    def test_still_home(self):
        # "ยังอยู่ห้อง" -> HOME + false_alert
        leave(self.g, 7, 40)
        self.g.tick(at(7, 43))
        self.assertEqual(self.g.state, OUT)
        actions = self.g.still_home()
        self.assertEqual(self.g.state, HOME)
        self.assertEqual(events(actions), ["false_alert"])

    def test_night_reset(self):
        # ข้ามเวลา NIGHT_RESET -> HOME และเตือนได้ใหม่ในวันถัดไป
        leave(self.g, 7, 40)
        self.g.tick(at(7, 43))
        self.assertEqual(self.g.state, OUT)
        self.g.tick(at(2, 59, day=27))
        self.assertEqual(self.g.state, OUT)                     # ยังไม่ถึง 03:00
        self.g.tick(at(3, 1, day=27))
        self.assertEqual(self.g.state, HOME)
        # อังคารไม่มีเรียน ช่วงเตือน 08:00-11:00
        leave(self.g, 9, 0, 0, day=27)
        self.assertEqual(kinds(self.g.tick(at(9, 3, day=27))), ["checklist"])

    def test_open_too_long_once(self):
        # เปิดค้างเกิน OPEN_ALERT_SEC -> เตือนครั้งเดียว
        self.g.on_door("open", at(12, 0))
        self.assertEqual(self.g.tick(at(12, 2, 59)), [])         # ยังไม่ถึง 3 นาที
        self.assertEqual(kinds(self.g.tick(at(12, 3))), ["open_long"])
        self.assertEqual(self.g.tick(at(12, 10)), [])            # ไม่เตือนซ้ำ
        # ปิดแล้วเปิดใหม่ -> เตือนได้อีกรอบ
        self.g.on_door("close", at(12, 11))
        self.g.on_door("open", at(12, 12))
        self.assertEqual(kinds(self.g.tick(at(12, 15))), ["open_long"])

    def test_close_after_long_open_is_inside(self):
        # เปิดค้างจนเตือนลืมปิด แล้วค่อยปิด -> ถือว่าปิดจากในห้อง ไม่เตือนเช็คลิสต์
        self.g.on_door("open", at(7, 40))
        self.g.tick(at(7, 43))                                   # เตือนลืมปิด
        actions = self.g.on_door("close", at(7, 44))
        self.assertEqual(self.g.state, HOME)
        self.assertEqual(events(actions), ["closed_inside"])
        self.assertEqual(self.g.tick(at(7, 50)), [])             # ไม่มีเช็คลิสต์
        # ครั้งต่อไปเปิด-ปิดปกติ -> ออกจริงยังเตือนได้
        leave(self.g, 8, 0)
        self.assertEqual(kinds(self.g.tick(at(8, 3))), ["checklist"])

    def test_appointment_window(self):
        # อังคาร 27 ไม่มีเรียน (ช่วงปกติ 08:00-11:00) มีนัด 08:00 -> เตือนได้ตั้งแต่ 06:30
        appts = {"2026-10-27": [{"time": "08:00", "name": "มีนัด"}]}
        g = DoorGuard(dict(CONFIG), TIMETABLE, appts)
        leave(g, 7, 0, day=27)
        self.assertEqual(kinds(g.tick(at(7, 3, day=27))), ["checklist"])

    def test_appointment_added_later(self):
        # เพิ่มนัดหลังสร้าง guard (dict เดียวกัน) -> guard เห็นนัดใหม่ทันที
        appts = {}
        g = DoorGuard(dict(CONFIG), TIMETABLE, appts)
        appts["2026-10-27"] = [{"time": "07:00", "name": "นัด"}]
        leave(g, 6, 0, day=27)
        self.assertEqual(kinds(g.tick(at(6, 3, day=27))), ["checklist"])

    def test_alert_once_per_window(self):
        # จันทร์: เช้ามีเรียน 09:00 + เย็นมีนัด 18:00 -> เตือนได้ทั้ง 2 ช่วง
        appts = {"2026-10-26": [{"time": "18:00", "name": "กินข้าว"}]}
        g = DoorGuard(dict(CONFIG), TIMETABLE, appts)
        leave(g, 7, 40)
        self.assertEqual(kinds(g.tick(at(7, 43))), ["checklist"])
        g.on_door("open", at(12, 0))
        g.on_door("close", at(12, 0, 5))                         # กลับห้อง
        leave(g, 17, 0)
        self.assertEqual(kinds(g.tick(at(17, 3))), ["checklist"])

    def test_late_return_quiet_checklist(self):
        # กลับห้องหลังตี 3 -> สถานะกลับด้าน -> เช้าออกไปเรียนต้องยังได้เช็คลิสต์ (แบบเงียบ)
        leave(self.g, 20, 0, day=25)
        self.g.tick(at(20, 3, day=25))
        self.g.tick(at(3, 1, day=26))                            # NIGHT_RESET -> HOME
        leave(self.g, 3, 30, day=26)                             # กลับถึงห้อง (ระบบคิดว่าออก)
        self.g.tick(at(3, 33, day=26))
        self.assertEqual(self.g.state, OUT)                      # กลับด้าน
        actions = self.g.on_door("open", at(7, 45, day=26))
        actions += self.g.on_door("close", at(7, 45, 5, day=26))
        self.assertIn("checklist_quiet", kinds(actions))
        # แก้สถานะด้วย "ออกแล้ว"
        self.assertEqual(events(self.g.force_out(at(7, 46, day=26))), ["false_return"])
        self.assertEqual(self.g.state, OUT)

    def test_quiet_does_not_block_real_alert(self):
        # วันที่อาจกลับด้าน: ได้เช็คลิสต์เงียบตอน "กลับห้อง" แล้วออกจริงทีหลัง -> ยังเตือนปกติ
        leave(self.g, 20, 0, day=25)
        self.g.tick(at(20, 3, day=25))
        self.g.tick(at(3, 1, day=26))                            # รีเซ็ตตอนยังอยู่ข้างนอก
        self.g.force_out(at(7, 30))
        self.g.on_door("open", at(7, 35))
        actions = self.g.on_door("close", at(7, 35, 5))
        self.assertIn("checklist_quiet", kinds(actions))
        leave(self.g, 8, 0)
        self.assertEqual(kinds(self.g.tick(at(8, 3))), ["checklist"])

    def test_return_outside_window_no_quiet(self):
        # กลับห้องนอกช่วงเตือน -> ไม่ส่งอะไร
        leave(self.g, 12, 0)
        self.g.tick(at(12, 3))
        self.g.on_door("open", at(13, 0))
        self.assertEqual(kinds(self.g.on_door("close", at(13, 0, 5))), ["log"])

    def test_new_day_action(self):
        self.g.tick(at(23, 0, day=26))
        self.assertEqual(kinds(self.g.tick(at(3, 0, day=27))), ["new_day"])

    def test_save_load_state(self):
        # จำค่าข้ามการปิด/เปิดโปรแกรม เฉพาะรอบวันเดียวกัน
        leave(self.g, 7, 40)
        self.g.tick(at(7, 43))
        self.g.set_no_alert()
        data = self.g.to_dict()
        g2 = DoorGuard(dict(CONFIG), TIMETABLE)
        self.assertTrue(g2.load_dict(data, at(10, 0)))
        self.assertEqual((g2.alerted, g2.no_alert), (True, True))
        self.assertEqual(g2.alerted_windows, [(450, 540)])        # 07:30-09:00 เป็น tuple
        g3 = DoorGuard(dict(CONFIG), TIMETABLE)
        self.assertFalse(g3.load_dict(data, at(10, 0, day=27)))  # วันใหม่ = ไม่โหลด
        self.assertEqual(g3.alerted, False)

    def test_cooldown_30_allows_appointment_alert(self):
        # B3: COOLDOWN_MIN 180 เคยบล็อกการเตือนก่อนนัด -> config ใหม่ 30 นาที ต้องเตือนได้
        config = dict(CONFIG)
        config["COOLDOWN_MIN"] = 30
        appts = {"2026-10-26": [{"time": "11:00", "name": "หาหมอ"}]}
        g = DoorGuard(config, TIMETABLE, appts)
        leave(g, 8, 0)
        self.assertEqual(kinds(g.tick(at(8, 3))), ["checklist"])
        g.on_door("open", at(9, 50))
        g.on_door("close", at(9, 50, 5))
        leave(g, 10, 15)
        self.assertEqual(kinds(g.tick(at(10, 18))), ["checklist"])

    def test_alert_every_exit_option(self):
        # ALERT_EVERY_EXIT (โหมดเดโม): ออกครั้งที่ 2 ในช่วงเดียวกันก็เตือน ถ้าพ้น cooldown
        config = dict(CONFIG)
        config["ALERT_EVERY_EXIT"] = True
        config["COOLDOWN_MIN"] = 1
        g = DoorGuard(config, TIMETABLE)
        leave(g, 7, 40)
        self.assertEqual(kinds(g.tick(at(7, 43))), ["checklist"])
        g.on_door("open", at(7, 44))
        g.on_door("close", at(7, 44, 5))
        leave(g, 7, 50)
        self.assertEqual(kinds(g.tick(at(7, 53))), ["checklist"])

    def test_skip_has_code(self):
        leave(self.g, 12, 0)
        self.assertEqual(self.g.tick(at(12, 3))[0]["code"], "outside")

    def test_float_epoch(self):
        # epoch จริงจาก time.time() เป็นทศนิยม -> ต้องไม่ถือว่าข้ามวันใหม่
        self.g.on_door("open", (at(7, 40)[0] + 0.7, at(7, 40)[1]))
        self.g.tick((at(7, 40)[0] + 1.2, at(7, 40, 1)[1]))
        self.assertEqual(self.g.state, DOOR_OPEN)

    def test_open_door_states(self):
        # เปิดประตูค้าง -> DOOR_OPEN ไม่เตือนอะไร
        self.g.on_door("open", at(7, 40))
        self.assertEqual(self.g.state, DOOR_OPEN)
        self.assertEqual(self.g.tick(at(7, 41)), [])


if __name__ == "__main__":
    unittest.main()
