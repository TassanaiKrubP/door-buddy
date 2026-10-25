# เทสต์ตัวรับสถานะประตูจากบอร์ด (pc/door_link.py) + การต่อเข้ากับ App
import json
import unittest

from pc.door_link import DoorTracker
from tests.test_app import AppFixture, at


def msg(seq, door, age=0, boot=111):
    return json.dumps({"boot": boot, "seq": seq, "door": door, "age": age}).encode()


class TestDoorTracker(unittest.TestCase):

    def setUp(self):
        self.t = DoorTracker()

    def test_first_contact_is_sync_only(self):
        self.assertEqual(self.t.feed(msg(5, "close"), 100.0), [("close", 100.0, False)])

    def test_change_uses_real_edge_time(self):
        self.t.feed(msg(0, "close"), 100.0)
        # ประตูเปิดไปแล้ว 300 ms ตอนข้อความมาถึง -> เวลาจริง = 200.0 - 0.3
        self.assertEqual(self.t.feed(msg(1, "open", age=300), 200.0), [("open", 199.7, True)])

    def test_repeat_and_heartbeat_ignored(self):
        self.t.feed(msg(0, "close"), 100.0)
        self.t.feed(msg(1, "open"), 101.0)
        self.assertEqual(self.t.feed(msg(1, "open", age=150), 101.2), [])   # ส่งซ้ำ
        self.assertEqual(self.t.feed(msg(1, "open", age=2000), 103.0), [])  # บอกว่ายังอยู่
        self.assertEqual(self.t.last_seen, 103.0)

    def test_late_old_message_ignored(self):
        self.t.feed(msg(0, "close"), 100.0)
        self.t.feed(msg(2, "close"), 101.0)
        self.assertEqual(self.t.feed(msg(1, "open"), 101.5), [])

    def test_missed_pair_same_state_ignored(self):
        self.t.feed(msg(0, "close"), 100.0)
        self.assertEqual(self.t.feed(msg(2, "close"), 110.0), [])           # พลาด เปิด+ปิด

    def test_board_reboot_is_sync(self):
        self.t.feed(msg(4, "open"), 100.0)
        self.assertEqual(self.t.feed(msg(0, "close", boot=222), 150.0), [("close", 150.0, False)])
        self.assertEqual(self.t.feed(msg(1, "open", boot=222), 160.0), [("open", 160.0, True)])

    def test_bad_message_raises(self):
        with self.assertRaises(ValueError):
            self.t.feed(b"hello", 1.0)
        with self.assertRaises(ValueError):
            self.t.feed(msg(1, "ajar"), 1.0)
        with self.assertRaises(KeyError):
            self.t.feed(b'{"seq": 1}', 1.0)


class FakeLink:
    # แทน DoorLink (ไม่เปิดพอร์ตจริง)
    def __init__(self):
        self.queue = []
        self.is_online = True
        self.ip = "192.168.1.50"

    def get_events(self):
        out, self.queue = self.queue, []
        return out

    def online(self, now_epoch):
        return self.is_online

    def seconds_since_seen(self, now_epoch):
        return 0 if self.is_online else 30


class TestAppBoard(AppFixture):

    def setUp(self):
        super().setUp()
        self.link = FakeLink()
        self.app.link = self.link

    def test_sync_sets_door_without_guard(self):
        self.link.queue = [("open", at(7, 40)[0], False)]
        self.app.check_board(at(7, 40))
        self.assertEqual(self.app.door, "open")
        self.assertEqual(self.app.guard.state, "HOME")

    def test_real_event_goes_to_guard(self):
        self.link.queue = [("open", at(7, 40)[0], True)]
        self.app.check_board(at(7, 40, 1))
        self.assertEqual(self.app.door, "open")
        self.assertEqual(self.app.guard.state, "DOOR_OPEN")

    def test_offline_warn_then_back(self):
        sent = []
        self.app.notify = lambda text, silent=False, buttons=None: sent.append(text)
        self.app.check_board(at(7, 40))                      # ออนไลน์ครั้งแรก: ไม่แจ้ง
        self.assertEqual(sent, [])
        self.link.is_online = False
        self.app.check_board(at(7, 41))
        self.assertIn("ขาดการเชื่อมต่อ", sent[-1])
        self.app.check_board(at(7, 42))                      # ยังหลุด: ไม่แจ้งซ้ำ
        self.assertEqual(len(sent), 1)
        self.link.is_online = True
        self.app.check_board(at(7, 43))
        self.assertIn("กลับมา", sent[-1])

    def test_status_shows_board(self):
        self.assertIn("บอร์ดประตู: ออนไลน์", self.app.status_text())
        self.link.is_online = False
        self.assertIn("ออฟไลน์", self.app.status_text())


if __name__ == "__main__":
    unittest.main()
