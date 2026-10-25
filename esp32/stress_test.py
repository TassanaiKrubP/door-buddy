# ขั้น B3: ทดสอบว่าบอร์ดไหวไหม (สเปกเฟส 2) — รันเหมือนใช้งานจริงบนบอร์ด 1-2 ชั่วโมง
#   - อ่านประตู (D32) + core/guard.py ตัดสินว่าออกจริงไหม -> ส่งเช็คลิสต์ (core/checklist.py) เข้า Telegram
#   - ถาม Telegram ทุก 3 วิ (ใครพิมพ์อะไรมา บอร์ดตอบกลับพร้อมหน่วยความจำที่เหลือ)
#   - ดึงอากาศ Open-Meteo ทุก 1 ชม.
#   - พิมพ์ gc.mem_free() + สถิติทุก 5 นาที (ดูว่าหน่วยความจำลดลงเรื่อย ๆ ไหม)
# ผ่านเมื่อ: รันครบ 1-2 ชม. ไม่ค้าง ไม่รีสตาร์ท และ mem_free ไม่ลดลงเรื่อย ๆ
#
# ไฟล์ที่ต้องอัปโหลดขึ้นบอร์ดก่อน: secrets.json (มี WIFI_SSID / WIFI_PASS), config.json,
#   rules.json, timetable.json, โฟลเดอร์ core/
# รันจากคอม: python -m mpremote connect COM3 run esp32/stress_test.py   (หยุดด้วย Ctrl+C)
# ** ปิดโปรแกรม pc.main ก่อน ** (ถ้าคอมกับบอร์ดถาม Telegram พร้อมกัน จะแย่งข้อความกัน)
# ข้อความบนจอเป็นภาษาอังกฤษ (หน้าจอ Windows อาจแสดงภาษาไทยจากบอร์ดเพี้ยน) · ข้อความใน Telegram เป็นไทยได้
import gc
import json
import time

import network
import ntptime
from machine import Pin

try:
    import requests                    # MicroPython รุ่นใหม่
except ImportError:
    import urequests as requests       # รุ่นเก่า

from core.checklist import build_checklist
from core.guard import DoorGuard

DOOR_PIN = 32
DEBOUNCE_MS = 500
POLL_MS = 3000           # ถาม Telegram ทุก 3 วิ (ตามสเปก)
MEM_MS = 5 * 60 * 1000   # พิมพ์หน่วยความจำทุก 5 นาที
WEATHER_MS = 60 * 60 * 1000
TZ = 7 * 3600            # เวลาไทย UTC+7 (บอร์ดตั้งเวลาจากเน็ตเป็น UTC)


def load(name):
    with open(name) as f:
        return json.load(f)


def now():
    # now แบบที่ core ต้องการ: (epoch, (ปี, เดือน, วัน, ชม, นาที, วินาที, วันในสัปดาห์))
    epoch = time.time() + TZ
    return (epoch, time.localtime(epoch)[:7])


def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        for _ in range(30):              # รอไม่เกิน 15 วิ
            if wlan.isconnected():
                break
            time.sleep_ms(500)
    return wlan


secrets = load("secrets.json")
config = load("config.json")
rules = load("rules.json")
timetable = load("timetable.json")
API = "https://api.telegram.org/bot" + secrets["TELEGRAM_TOKEN"] + "/"
CHAT = secrets["TELEGRAM_CHAT_ID"]

stats = {"poll_ok": 0, "poll_fail": 0, "send_ok": 0, "send_fail": 0,
         "weather_ok": 0, "weather_fail": 0, "door": 0, "max_loop_ms": 0}


def send(text):
    # ส่งข้อความ Telegram (เน็ตหลุด = นับว่าพลาด ไม่ล้ม)
    try:
        r = requests.post(API + "sendMessage", json={"chat_id": CHAT, "text": text})
        ok = r.status_code == 200
        r.close()
    except Exception as e:
        print("send error:", e)
        ok = False
    stats["send_ok" if ok else "send_fail"] += 1
    gc.collect()


def poll(offset):
    # ถามข้อความใหม่ (timeout=0 ตอบทันที) · คืน offset ใหม่
    try:
        r = requests.get(API + "getUpdates?timeout=0&limit=5&offset=" + str(offset))
        updates = r.json().get("result", [])
        r.close()
        stats["poll_ok"] += 1
    except Exception as e:
        print("poll error:", e)
        stats["poll_fail"] += 1
        return offset
    for u in updates:
        offset = u["update_id"] + 1
        msg = u.get("message", {})
        if str(msg.get("chat", {}).get("id", "")) == str(CHAT) and "text" in msg:
            send("ESP32 ได้รับ: " + msg["text"] + "\n(หน่วยความจำเหลือ "
                 + str(gc.mem_free()) + " ไบต์)")
    gc.collect()
    return offset


def skip_old():
    # ทิ้งข้อความที่ค้างในแชทก่อนเริ่ม (ไม่งั้นบอร์ดตอบข้อความเก่าทั้งหมดรัว ๆ) · คืน offset เริ่มต้น
    try:
        r = requests.get(API + "getUpdates?timeout=0&offset=-1")
        updates = r.json().get("result", [])
        r.close()
        if updates:
            return updates[-1]["update_id"] + 1
    except Exception as e:
        print("skip_old error:", e)
    return 0


def weather():
    # ดึงโอกาสฝนวันนี้ (สูงสุดรายชั่วโมง) · ไม่ได้ = None
    url = ("https://api.open-meteo.com/v1/forecast?latitude=" + str(config["LAT"])
           + "&longitude=" + str(config["LON"])
           + "&hourly=precipitation_probability&timezone=Asia%2FBangkok&forecast_days=1")
    try:
        r = requests.get(url)
        probs = r.json()["hourly"]["precipitation_probability"]
        r.close()
        stats["weather_ok"] += 1
        return max([p for p in probs if p is not None])
    except Exception as e:
        print("weather error:", e)
        stats["weather_fail"] += 1
        return None
    finally:
        gc.collect()


def checklist_text(rain):
    items = build_checklist(rules, timetable, None if rain is None else {"rain_prob": rain},
                            now()[1], config["RAIN_PROB"])
    lines = ["ESP32: ออกจากห้องแล้ว", "อย่าลืม"]
    for i in range(len(items)):
        lines.append(str(i + 1) + ". " + str(items[i]))
    return "\n".join(lines)


def handle(actions, rain):
    for a in actions:
        if a["do"] == "checklist":
            send(checklist_text(rain))
        print("action:", a)


# ----- เริ่ม -----
print("connecting wifi...")
wlan = connect_wifi(secrets["WIFI_SSID"], secrets["WIFI_PASS"])
print("wifi:", wlan.isconnected())
try:
    ntptime.settime()                    # ตั้งนาฬิกาบอร์ดจากเน็ต
except Exception as e:
    print("ntp error:", e)
print("time:", now()[1])

config["OUT_DELAY"] = 10                 # ทดสอบ: รอ 10 วิ เหมือนโหมดเดโม
config["NO_CLASS_WINDOW"] = ["00:00", "23:59"]
config["ALERT_EVERY_EXIT"] = True
config["COOLDOWN_MIN"] = 1
guard = DoorGuard(config, [], rules.get("appointments", {}))

door = Pin(DOOR_PIN, Pin.IN, Pin.PULL_UP)
stable = door.value()
candidate = stable
since = time.ticks_ms()
offset = skip_old()
rain = weather()
start = time.ticks_ms()
mem_start = gc.mem_free()
last = {"tick": 0, "poll": 0, "mem": start, "weather": start}
send("ESP32 เริ่มทดสอบ (หน่วยความจำเหลือ " + str(mem_start) + " ไบต์)")
print("start mem_free:", mem_start)

while True:
    t0 = time.ticks_ms()
    # ประตู (กันสั่น 500 ms) · ปิด = 0 / เปิด = 1 (ยืนยันขั้วแล้วใน B2)
    value = door.value()
    if value != candidate:
        candidate = value
        since = t0
    elif candidate != stable and time.ticks_diff(t0, since) >= DEBOUNCE_MS:
        stable = candidate
        stats["door"] += 1
        kind = "open" if stable else "close"
        print("door", kind)
        handle(guard.on_door(kind, now()), rain)
    if time.ticks_diff(t0, last["tick"]) >= 1000:
        last["tick"] = t0
        handle(guard.tick(now()), rain)
    if time.ticks_diff(t0, last["poll"]) >= POLL_MS:
        last["poll"] = t0
        if not wlan.isconnected():       # WiFi หลุด -> ต่อใหม่
            wlan = connect_wifi(secrets["WIFI_SSID"], secrets["WIFI_PASS"])
        offset = poll(offset)
    if time.ticks_diff(t0, last["weather"]) >= WEATHER_MS:
        last["weather"] = t0
        rain = weather()
    if time.ticks_diff(t0, last["mem"]) >= MEM_MS:
        last["mem"] = t0
        gc.collect()
        minutes = time.ticks_diff(t0, start) // 60000
        print("[", minutes, "min ] mem_free:", gc.mem_free(), "(start", mem_start, ")",
              "rain:", rain, stats)
    stats["max_loop_ms"] = max(stats["max_loop_ms"], time.ticks_diff(time.ticks_ms(), t0))
    time.sleep_ms(20)
