# ขั้น B2: ทดสอบเซนเซอร์ประตู MC-38 บน ESP32 (MicroPython)
# ต่อสาย: MC-38 สายหนึ่ง -> GND · อีกสาย -> GPIO32 (ขา D32) · สวิตช์ไม่มีขั้ว สลับสายได้
# รันจากคอม: python -m mpremote connect COM3 run esp32/door_test.py   (หยุดด้วย Ctrl+C)
# ข้อความเป็นภาษาอังกฤษ เพราะหน้าจอ Windows อาจแสดงภาษาไทยจากบอร์ดเพี้ยน
from machine import Pin
import time

PIN = 32
DEBOUNCE_MS = 500        # สถานะต้องคงที่นานเท่านี้ ถึงนับว่าประตูเปลี่ยนจริง (กันสั่น)

door = Pin(PIN, Pin.IN, Pin.PULL_UP)   # PULL_UP: สวิตช์ต่อลง GND = 0, สวิตช์เปิด = 1


def name(value):
    # ค่าที่อ่านได้ -> ข้อความ · คาดไว้ตามงานกล่องยา: ปิด = 0 (LOW), เปิด = 1 (HIGH)
    if value:
        return "OPEN   (pin=1 HIGH)"
    return "CLOSED (pin=0 LOW)"


stable = door.value()            # สถานะที่ยืนยันแล้ว
candidate = stable               # สถานะที่กำลังรอดูว่าคงที่ไหม
since = time.ticks_ms()
bounces = 0                      # จำนวนครั้งที่ค่ากระตุกแป๊บเดียวแล้วกลับ (ไม่นับเป็นการเปลี่ยน)
print("start: door", name(stable))

while True:
    value = door.value()
    now = time.ticks_ms()
    if value != candidate:
        if candidate != stable:          # เปลี่ยนกลับก่อนครบเวลา = สั่น
            bounces += 1
        candidate = value
        since = now
    elif candidate != stable and time.ticks_diff(now, since) >= DEBOUNCE_MS:
        stable = candidate
        print("door", name(stable), " (bounces so far:", bounces, ")")
    time.sleep_ms(20)
