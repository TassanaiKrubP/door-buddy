# Door Buddy บนบอร์ด (แบบ บอร์ด+คอม): อ่านเซนเซอร์ประตู แล้วส่งสถานะให้คอมผ่าน WiFi (UDP)
# บอร์ดไม่คุย Telegram เอง (ทดสอบแล้ว: MicroPython RAM ไม่พอสำหรับ HTTPS ช้า/หลุดบ่อย)
#   -> คอม (python -m pc.main) รับสถานะไปตัดสิน + คุย Telegram แทน
# ต่อสาย: MC-38 สายหนึ่ง -> GND · อีกสาย -> D32 · ปิด = 0, เปิด = 1 (ยืนยันแล้วในขั้น B2)
# ไฟล์บนบอร์ด: main.py, door_sensor.mpy, secrets.json (ใช้แค่ WIFI_SSID / WIFI_PASS)
#
# ข้อความที่ส่ง (JSON): {"boot": เลขสุ่มตอนเปิดเครื่อง, "seq": ประตูเปลี่ยนครั้งที่, "door": "open"/"close",
#                       "age": ประตูเปลี่ยนมาแล้วกี่ ms}
#   ส่งทันทีที่ประตูเปลี่ยน + ซ้ำอีก 2 รอบ (UDP อาจหาย) + ทุก 2 วิ (บอกคอมว่ายังอยู่)
#   ส่งแบบกระจายทั้งวง WiFi (broadcast) -> บอร์ดไม่ต้องรู้ IP ของคอม
# ข้อความบนจอเป็นภาษาอังกฤษ (หน้าจอ Windows แสดงภาษาไทยจากบอร์ดเพี้ยน)
import json
import os
import socket
import time

import machine
import network
from machine import Pin

DOOR_PIN = 32
LED_PIN = 2                 # ไฟสีฟ้าบนบอร์ด: ติด = ต่อ WiFi แล้ว
DEBOUNCE_MS = 500           # ค่าต้องคงที่นานเท่านี้ ถึงนับว่าประตูเปลี่ยนจริง (กันสั่น)
PORT = 4210                 # ต้องตรงกับ PORT ใน pc/door_link.py
HEARTBEAT_MS = 2000
REPEAT_MS = (150, 400)      # ส่งซ้ำหลังประตูเปลี่ยน (นับจากครั้งแรก)
WIFI_RETRY_MS = 5000
OFFLINE_RESET_MS = 3 * 60 * 1000   # WiFi หลุดนานเกินนี้ -> รีสตาร์ทบอร์ด (เริ่ม WiFi ใหม่หมด)
TARGET_IP = ""              # ว่าง = broadcast · ถ้าคอมไม่ได้รับ ลองใส่ IP ของคอมตรงนี้


def load_secrets():
    with open("secrets.json") as f:
        return json.load(f)


def try_connect(wlan, secrets):
    # สั่งต่อ WiFi แบบไม่รอ (ระหว่างนี้ยังอ่านประตูได้) · ชิปกำลังต่ออยู่แล้ว = ไม่สั่งซ้ำ
    if wlan.isconnected() or wlan.status() == network.STAT_CONNECTING:
        return
    try:
        wlan.connect(secrets["WIFI_SSID"], secrets["WIFI_PASS"])
    except OSError as e:
        print("wifi connect error:", e)


def target(wlan):
    # ที่อยู่ปลายทาง: IP คอม (ถ้าตั้งไว้) หรือ broadcast ของวง เช่น 192.168.1.255
    if TARGET_IP:
        return TARGET_IP
    ip, mask = wlan.ifconfig()[:2]
    a = [int(x) for x in ip.split(".")]
    m = [int(x) for x in mask.split(".")]
    return ".".join(str(a[i] | (255 - m[i])) for i in range(4))


def main():
    secrets = load_secrets()
    door = Pin(DOOR_PIN, Pin.IN, Pin.PULL_UP)
    led = Pin(LED_PIN, Pin.OUT)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    except (AttributeError, OSError):
        pass

    boot = int.from_bytes(os.urandom(2), "big")    # เลขสุ่ม: คอมรู้ว่าบอร์ดรีสตาร์ท
    stable = door.value()                          # สถานะที่ยืนยันแล้ว
    candidate = stable                             # สถานะที่กำลังรอดูว่าคงที่ไหม
    since = time.ticks_ms()                        # เวลาที่ candidate เริ่มเป็นค่านี้ (= ขาเปลี่ยนจริง)
    changed_at = since                             # เวลาที่ประตูเปลี่ยนล่าสุด (ส่งเป็น age)
    seq = 0
    pending = []                                   # เวลาที่ต้องส่งซ้ำ (ticks)
    last_send = time.ticks_ms()
    last_try = time.ticks_add(time.ticks_ms(), -WIFI_RETRY_MS)
    last_online = time.ticks_ms()
    was_online = False
    print("door sensor start | boot", boot, "| door", "open" if stable else "close")

    while True:
        now = time.ticks_ms()

        # 1) อ่านประตู + กันสั่น
        value = door.value()
        if value != candidate:
            candidate = value
            since = now
        elif candidate != stable and time.ticks_diff(now, since) >= DEBOUNCE_MS:
            stable = candidate
            seq += 1
            changed_at = since
            pending = [now] + [time.ticks_add(now, ms) for ms in REPEAT_MS]
            print("door", "open" if stable else "close", "| seq", seq)

        # 2) WiFi
        online = wlan.isconnected()
        led.value(1 if online else 0)
        if online != was_online:
            was_online = online
            print("wifi:", online, wlan.ifconfig()[0] if online else "")
        if online:
            last_online = now
        else:
            if time.ticks_diff(now, last_try) >= WIFI_RETRY_MS:
                last_try = now
                try_connect(wlan, secrets)
            if time.ticks_diff(now, last_online) >= OFFLINE_RESET_MS:
                print("wifi offline too long -> reset")
                machine.reset()

        # 3) ส่งสถานะ (ตอนประตูเปลี่ยน + ส่งซ้ำ + ทุก 2 วิ)
        due = pending and time.ticks_diff(now, pending[0]) >= 0
        if online and (due or time.ticks_diff(now, last_send) >= HEARTBEAT_MS):
            if due:
                pending.pop(0)
            data = json.dumps({"boot": boot, "seq": seq, "door": "open" if stable else "close",
                               "age": time.ticks_diff(now, changed_at)})
            try:
                sock.sendto(data.encode(), (target(wlan), PORT))
            except OSError as e:
                print("send error:", e)
            last_send = now

        time.sleep_ms(20)
