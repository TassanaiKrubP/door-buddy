# ไล่ปัญหา HTTPS ต่อไม่ได้: โหลดทีละส่วน แล้ววัดหน่วยความจำ + ลองต่อ HTTPS หลังแต่ละขั้น
# จะเห็นว่าโหลดถึงส่วนไหนแล้ว HTTPS เริ่มต่อไม่ได้ และแต่ละส่วนกินหน่วยความจำไปเท่าไร
#   gc free   = หน่วยความจำของ Python ที่เหลือ
#   tls block = ก้อนใหญ่สุดที่ส่วนเข้ารหัส (HTTPS) ใช้ได้ (ถ้าเล็กไป HTTPS จะพัง/ค้าง)
# รัน: ต้องไม่ให้ app เริ่มเอง -> มีไฟล์ nostart บนบอร์ด แล้วกด EN ก่อน (ดูวิธีในแชท)
#   python -m mpremote connect COM3 run esp32/memcheck.py
import gc
import json
import time

import esp32
import network


def tls_block():
    return max(h[2] for h in esp32.idf_heap_info(esp32.HEAP_DATA))


def show(label):
    gc.collect()
    print("[", label, "] gc free:", gc.mem_free(), "| tls block:", tls_block())


def try_https(label):
    # ลองต่อ HTTPS 1 ครั้ง (ไม่ส่งข้อความ แค่ถามข้อมูลบอท) · พิมพ์ผล + เวลาที่ใช้
    import requests
    gc.collect()
    t0 = time.ticks_ms()
    print("  https test after", label, "...")
    try:
        r = requests.get(API + "getMe")
        ok = r.status_code
        r.close()
        print("  https OK", ok, time.ticks_diff(time.ticks_ms(), t0), "ms")
    except Exception as e:
        print("  https FAIL", e, time.ticks_diff(time.ticks_ms(), t0), "ms")
    show("after https")


with open("secrets.json") as f:
    secrets = json.load(f)
API = "https://api.telegram.org/bot" + secrets["TELEGRAM_TOKEN"] + "/"

show("1 start")
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(secrets["WIFI_SSID"], secrets["WIFI_PASS"])
for _ in range(30):
    if wlan.isconnected():
        break
    time.sleep_ms(500)
print("wifi:", wlan.isconnected())
show("2 wifi")

import requests
show("3 requests")
try_https("requests")

import bdate
from core.checklist import build_checklist
from core.commands import parse_command
from core.guard import DoorGuard
show("4 core + bdate")
try_https("core")

import app
show("5 app loaded (not running)")
try_https("app")
print("done")
