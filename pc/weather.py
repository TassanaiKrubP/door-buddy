# ดึงพยากรณ์ฝนรายชั่วโมงจาก Open-Meteo (ฟรี ไม่ต้องใช้ key)
# ทำงานใน thread แยก ดึงใหม่ทุก 1 ชม. -> ลูปหลักไม่ต้องรอเน็ต
# ดึงไม่ได้ / ข้อมูลเก่าเกิน = ไม่มีข้อมูลอากาศ (checklist ไม่ใช้กฎฝน แต่โปรแกรมไม่ล้ม)
import json
import threading
import time
import urllib.parse
import urllib.request

from pc import storage

URL = "https://api.open-meteo.com/v1/forecast"
CACHE = "data/weather.json"
REFRESH_SEC = 3600      # ดึงใหม่ทุก 1 ชม.
RETRY_SEC = 300         # ดึงไม่ได้ ลองใหม่ใน 5 นาที
MAX_AGE_SEC = 3 * 3600  # ข้อมูลเก่ากว่า 3 ชม. ถือว่าใช้ไม่ได้
DAY_HOURS = (6, 20)     # ดูเช็คลิสต์วันอื่น: ใช้โอกาสฝนช่วง 06:00-20:00 ของวันนั้น


def fetch(lat, lon):
    # ดึงพยากรณ์ 7 วัน คืน {"times": ["2026-10-26T14:00", ...], "probs": [70, ...]} หรือ None
    params = {"latitude": lat, "longitude": lon,
              "hourly": "precipitation_probability",
              "timezone": "Asia/Bangkok", "forecast_days": 7}
    try:
        url = URL + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=10) as resp:
            hourly = json.loads(resp.read().decode("utf-8"))["hourly"]
        return {"times": hourly["time"], "probs": hourly["precipitation_probability"]}
    except Exception:
        return None


def hour_key(tup):
    # tuple เวลาแบบ core -> "YYYY-MM-DDTHH:00" (รูปแบบเวลาของ Open-Meteo)
    return "{:04d}-{:02d}-{:02d}T{:02d}:00".format(tup[0], tup[1], tup[2], tup[3])


def max_prob(data, start, hours):
    # โอกาสฝนสูงสุดตั้งแต่ชั่วโมง start ไปอีก hours ชั่วโมง · ไม่มีข้อมูลช่วงนั้น = None
    if start not in data["times"]:
        return None
    i = data["times"].index(start)
    probs = [p for p in data["probs"][i:i + hours] if p is not None]
    return max(probs) if probs else None


def day_prob(data, key):
    # โอกาสฝนสูงสุดของวัน key ช่วง DAY_HOURS · ไม่มีข้อมูล = None
    probs = []
    for t, p in zip(data["times"], data["probs"]):
        if t.startswith(key) and DAY_HOURS[0] <= int(t[11:13]) <= DAY_HOURS[1] and p is not None:
            probs.append(p)
    return max(probs) if probs else None


class WeatherWorker:
    # ดึงอากาศใน thread แยก · ลูปหลักเรียก rain_prob() ซึ่งใช้ข้อมูลที่ดึงไว้แล้ว (ไม่รอเน็ต)

    def __init__(self, lat, lon, start=True):
        self.lat = lat
        self.lon = lon
        self.data = None          # ข้อมูลล่าสุด
        self.fetched_at = 0       # epoch ที่ดึงได้ล่าสุด
        self.fake = None          # ค่าจำลองฝน % (ไว้ทดสอบ/อัดคลิป) · None = ใช้ของจริง
        self.running = True
        self.load_cache()
        if start:
            threading.Thread(target=self.loop, daemon=True).start()

    def __str__(self):
        if self.fake is not None:
            return "อากาศ(จำลองฝน " + str(self.fake) + "%)"
        if not self.ready():
            return "อากาศ(ไม่มีข้อมูล)"
        return "อากาศ(อัปเดต " + time.strftime("%H:%M", time.localtime(self.fetched_at)) + ")"

    def load_cache(self):
        # ใช้ข้อมูลที่เคยดึงไว้ (เปิดโปรแกรมใหม่ไม่ต้องรอ) ถ้ายังไม่เก่าเกิน
        try:
            cache = storage.load_json(CACHE)
            if cache["lat"] == self.lat and cache["lon"] == self.lon:
                self.data = cache["data"]
                self.fetched_at = cache["fetched_at"]
        except (OSError, ValueError, KeyError):
            pass

    def update(self):
        # ดึงใหม่ 1 ครั้ง · คืน True ถ้าได้
        data = fetch(self.lat, self.lon)
        if data is None:
            return False
        self.data = data
        self.fetched_at = time.time()
        try:
            storage.save_json(CACHE, {"lat": self.lat, "lon": self.lon,
                                      "fetched_at": self.fetched_at, "data": data})
        except OSError:
            pass
        return True

    def loop(self):
        # thread: ดึงทันทีถ้าข้อมูลเก่า แล้ววนดึงทุก REFRESH_SEC (ดึงไม่ได้ลองใหม่ใน RETRY_SEC)
        while self.running:
            wait = REFRESH_SEC - (time.time() - self.fetched_at)
            if wait <= 0:
                wait = REFRESH_SEC if self.update() else RETRY_SEC
            # หลับทีละ 1 วินาที จะได้หยุดได้เร็วเมื่อ running = False
            end = time.time() + wait
            while self.running and time.time() < end:
                time.sleep(1)

    def stop(self):
        self.running = False

    def ready(self):
        return self.data is not None and time.time() - self.fetched_at <= MAX_AGE_SEC

    def rain_prob(self, key, now, hours):
        # โอกาสฝน % สำหรับเช็คลิสต์ของวัน key · ไม่มีข้อมูล = None
        #   วันนี้   = สูงสุดในอีก hours ชั่วโมงจากตอนนี้ (ตอนออกจากห้อง)
        #   วันอื่น = สูงสุดช่วง 06:00-20:00 ของวันนั้น
        if self.fake is not None:
            return self.fake
        if not self.ready():
            return None
        today = hour_key(now[1])[:10]
        if key == today:
            return max_prob(self.data, hour_key(now[1]), hours)
        return day_prob(self.data, key)
