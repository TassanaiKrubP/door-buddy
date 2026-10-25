# เทสต์ชุด 3: TelegramWorker (thread แยก) · ไม่ต่อเน็ตจริง ใช้ฟังก์ชันปลอมแทน
import time
import unittest

from pc import telegram

REAL_DELIVER = telegram.deliver
REAL_GET = telegram.get_updates


def wait_until(check, timeout=3.0):
    # รอจน check() เป็น True (thread ทำงานเสร็จ) หรือหมดเวลา
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return False


def message(update_id, chat_id, text, date):
    return {"update_id": update_id,
            "message": {"chat": {"id": chat_id}, "text": text, "date": date}}


def press(update_id, chat_id, data, message_id=7):
    return {"update_id": update_id,
            "callback_query": {"id": "cb" + str(update_id), "data": data,
                               "message": {"chat": {"id": chat_id}, "message_id": message_id,
                                           "text": "เมนู"}}}


class TestTelegramWorker(unittest.TestCase):

    def setUp(self):
        self.sent = []          # รายการที่ "ส่งสำเร็จ"
        self.updates = []       # update ที่ get_updates ปลอมจะคืน (ครั้งเดียว)
        self.results = []       # ผลที่ deliver ปลอมจะคืนตามลำดับ (หมดแล้ว = OK)
        self.slow = 0           # ให้ deliver ช้ากี่วินาที (จำลองเน็ตช้า)

        def fake_deliver(token, chat_id, item):
            time.sleep(self.slow)
            result = self.results.pop(0) if self.results else telegram.OK
            if result == telegram.OK:
                self.sent.append(item)
            return result

        def fake_get(token, offset, wait=0):
            time.sleep(0.02)
            result = self.updates
            self.updates = []
            return result

        telegram.deliver = fake_deliver
        telegram.get_updates = fake_get
        self.worker = None

    def tearDown(self):
        if self.worker is not None:
            self.worker.stop()
            time.sleep(0.6)     # รอ thread หยุดก่อนคืนฟังก์ชันจริง (กันยิงเน็ตจริง)
        telegram.deliver = REAL_DELIVER
        telegram.get_updates = REAL_GET

    def start(self):
        self.worker = telegram.TelegramWorker("token-ปลอม", "1", retry_sec=0.05, set_menu=False)
        return self.worker

    def texts(self):
        return [item["text"] for item in self.sent if "text" in item]

    def test_receive_only_new_messages_from_user(self):
        w = self.start()
        self.updates = [message(1, 1, "เก่าก่อนเปิดโปรแกรม", w.start_time - 60),
                        message(2, 999, "คนอื่นทัก", w.start_time + 1),
                        message(3, 1, "/list", w.start_time + 1)]
        got = []
        self.assertTrue(wait_until(lambda: got.extend(w.receive()) or len(got) > 0))
        self.assertEqual(got, [{"kind": "text", "text": "/list"}])

    def test_receive_button_press(self):
        # กดปุ่ม -> ได้ data + message_id · ตอบ answerCallbackQuery ให้ปุ่มหยุดหมุน · คนอื่นกด = ไม่สน
        w = self.start()
        self.updates = [press(1, 999, "m:list"), press(2, 1, "m:appt", 42)]
        got = []
        self.assertTrue(wait_until(lambda: got.extend(w.receive()) or len(got) > 0))
        self.assertEqual(got, [{"kind": "button", "data": "m:appt", "message_id": 42,
                                "text": "เมนู"}])
        self.assertTrue(wait_until(lambda: {"answer": "cb2"} in self.sent))

    def test_send_retry_keeps_order(self):
        # เน็ตหลุด 2 ครั้งแรก -> ลองใหม่ได้ ลำดับข้อความไม่สลับ
        self.results = [telegram.NET, telegram.NET]
        w = self.start()
        w.send("ข้อความ 1")
        w.send("ข้อความ 2")
        self.assertTrue(wait_until(lambda: len(self.sent) == 2))
        self.assertEqual(self.texts(), ["ข้อความ 1", "ข้อความ 2"])

    def test_rejected_message_does_not_block_queue(self):
        # Telegram ไม่รับข้อความแรก (BAD) -> ข้าม ไม่ลองซ้ำตลอดกาล ข้อความถัดไปยังส่งได้
        self.results = [telegram.BAD]
        w = self.start()
        w.send("ยาวเกิน")
        w.edit(5, "เมนูใหม่")
        self.assertTrue(wait_until(lambda: len(self.sent) == 1))
        self.assertEqual(self.sent[0]["edit"], 5)

    def test_send_does_not_block_main_loop(self):
        # เน็ตช้า (ส่ง 1 รายการใช้ 1 วิ) -> send()/edit() ของลูปหลักต้องกลับทันที
        self.slow = 1.0
        w = self.start()
        t0 = time.time()
        w.send("a")
        w.edit(1, "b")
        self.assertLess(time.time() - t0, 0.1)
        self.assertEqual(w.receive(), [])     # receive ก็ไม่รอ

    def test_format_html(self):
        # หัวข้อตัวหนา · "# " ตัวหนา · "- " เป็นจุด · (หมายเหตุ) ตัวเอียง · escape < > &
        text = "เช็คลิสต์\n# อย่าลืม\n- ร่ม\n(หมายเหตุ)\nA<B & C"
        self.assertEqual(telegram.format_html(text),
                         "<b>เช็คลิสต์</b>\n<b>อย่าลืม</b>\n• ร่ม\n<i>(หมายเหตุ)</i>\n"
                         "A&lt;B &amp; C")
        self.assertEqual(telegram.format_html("<script>"), "<b>&lt;script&gt;</b>")

    def test_long_message_and_buttons_cut(self):
        # ยาวเกิน -> ตัดพร้อมบอก (ไม่ให้ Telegram ปฏิเสธแล้วบอทเงียบ) · ปุ่มเกิน -> เก็บแถวสุดท้ายไว้
        text = "หัวข้อ\n" + "\n".join("บรรทัด " + str(i) for i in range(1000))
        short = telegram.shorten(text)
        self.assertLessEqual(len(short), telegram.MAX_TEXT)
        self.assertIn("ยาวเกินที่ส่งได้", short)
        buttons = [[("ก", "x")] for i in range(150)] + [[("กลับ", "m:items")]]
        cut = telegram.limit_buttons(buttons)
        self.assertLessEqual(sum(len(r) for r in cut), telegram.MAX_BUTTONS)
        self.assertEqual(cut[-1], [("กลับ", "m:items")])

    def test_inline_buttons_format(self):
        # ปุ่ม -> json ที่ Telegram ต้องการ
        self.assertEqual(telegram.inline([[("ก", "m:list")]]),
                         '{"inline_keyboard": [[{"text": "ก", "callback_data": "m:list"}]]}')


if __name__ == "__main__":
    unittest.main()
