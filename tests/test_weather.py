# เทสต์ขั้น 6: อากาศ (pc/weather.py + เช็คลิสต์) · ไม่ต่อเน็ตจริง ใช้ข้อมูลปลอมทั้งหมด
import time
import unittest

from pc import weather
from tests.test_app import AppFixture, at


def fake_data():
    # พยากรณ์ปลอม 2 วัน: วันที่ 26 ฝน 10% ทั้งวัน ยกเว้น 10:00-11:00 = 70% · วันที่ 27 = 40%
    times, probs = [], []
    for day, base in [(26, 10), (27, 40)]:
        for hour in range(24):
            times.append("2026-10-{:02d}T{:02d}:00".format(day, hour))
            probs.append(70 if day == 26 and hour in (10, 11) else base)
    return {"times": times, "probs": probs}


def worker(data=None, age=0):
    # WeatherWorker ที่ไม่เปิด thread (ไม่ดึงเน็ต) แล้วใส่ข้อมูลเอง
    w = weather.WeatherWorker(13.75, 100.5, start=False)
    w.data = data
    w.fetched_at = time.time() - age
    return w


class TestWeather(unittest.TestCase):

    def test_max_prob_next_hours(self):
        data = fake_data()
        self.assertEqual(weather.max_prob(data, "2026-10-26T07:00", 6), 70)   # 07-12 เจอ 10:00
        self.assertEqual(weather.max_prob(data, "2026-10-26T13:00", 6), 10)
        self.assertEqual(weather.max_prob(data, "2025-01-01T00:00", 6), None)  # ไม่มีข้อมูล

    def test_day_prob(self):
        self.assertEqual(weather.day_prob(fake_data(), "2026-10-27"), 40)
        self.assertEqual(weather.day_prob(fake_data(), "2026-11-30"), None)

    def test_rain_prob_today_and_other_day(self):
        w = worker(fake_data())
        self.assertEqual(w.rain_prob("2026-10-26", at(7, 40), 6), 70)
        self.assertEqual(w.rain_prob("2026-10-27", at(7, 40), 6), 40)

    def test_no_data_or_too_old(self):
        # ดึงไม่ได้ / ข้อมูลเก่าเกิน 3 ชม. -> None (ไม่ใช้กฎฝน ไม่ล้ม)
        self.assertIsNone(worker(None).rain_prob("2026-10-26", at(7, 40), 6))
        self.assertIsNone(worker(fake_data(), age=4 * 3600).rain_prob("2026-10-26", at(7, 40), 6))

    def test_fetch_offline_returns_none(self):
        # ปิดเน็ต (จำลองด้วย URL ที่ต่อไม่ได้) -> fetch คืน None ไม่ล้ม
        real = weather.URL
        weather.URL = "http://127.0.0.1:9/ไม่มีจริง"
        try:
            self.assertIsNone(weather.fetch(13.75, 100.5))
        finally:
            weather.URL = real

    def test_fake_rain(self):
        w = worker(None)
        w.fake = 80
        self.assertEqual(w.rain_prob("2026-10-26", at(7, 40), 6), 80)


class TestChecklistWeather(AppFixture):

    def test_umbrella_when_rain(self):
        self.app.weather = worker(fake_data())               # 07:40 อีก 6 ชม. ฝน 70%
        page = self.app.checklist_page("2026-10-26", None)
        self.assertIn("โอกาสฝน 70% ในอีก 6 ชม.", page)
        self.assertIn("ร่ม  (ฝน 70%)", page)

    def test_no_umbrella_below_threshold(self):
        self.app.weather = worker(fake_data())               # วันที่ 27 = 40% < 50%
        page = self.app.checklist_page("2026-10-27", None)
        self.assertIn("โอกาสฝน 40% ช่วงกลางวัน", page)
        self.assertNotIn("ร่ม", page)

    def test_no_weather_data_still_works(self):
        self.app.weather = worker(None)
        page = self.app.checklist_page("2026-10-26", None)
        self.assertIn("ยังไม่มีข้อมูลอากาศ", page)
        self.assertIn("กุญแจห้อง", page)                       # ส่วนอื่นยังทำงาน

    def test_key_w_cycles_fake_rain(self):
        self.app.weather = worker(None)
        self.app.step(at(7, 41), "w")
        self.assertEqual(self.app.weather.fake, 80)
        self.app.step(at(7, 42), "w")
        self.assertEqual(self.app.weather.fake, 0)
        self.app.step(at(7, 43), "w")
        self.assertIsNone(self.app.weather.fake)


if __name__ == "__main__":
    unittest.main()
