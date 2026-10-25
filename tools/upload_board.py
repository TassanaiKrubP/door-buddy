# อัปโหลดโปรแกรมขึ้นบอร์ด ESP32 แบบแปลโค้ดไว้ก่อน (.mpy) · บอร์ดไม่ต้องแปลเอง (ประหยัด RAM)
# แบบ บอร์ด+คอม: บอร์ดมีแค่ door_sensor (อ่านประตู ส่งให้คอมทาง WiFi) + main.py
#   (secrets.json อยู่บนบอร์ดแล้วตั้งแต่ขั้น B3 · ใช้แค่ WIFI_SSID / WIFI_PASS)
#   แบบเดิมที่บอร์ดทำเองทั้งหมด (app.py, net.py, core/) เลิกใช้แล้ว เพราะ HTTPS บนบอร์ดช้า/หลุดบ่อย
#
# รัน (ในโฟลเดอร์ door_buddy):
#   python tools/upload_board.py COM3
# ต้องติดตั้งก่อน: python -m pip install mpy-cross mpremote
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
# โปรแกรมที่จะแปลเป็น .mpy -> ชื่อบนบอร์ด
SOURCES = [("esp32/door_sensor.py", "door_sensor.mpy")]


def run(args, check=True):
    # รันคำสั่งแล้วพิมพ์ให้เห็น · check=False ไม่หยุดถ้าพลาด (เช่น ลบไฟล์ที่ไม่มีอยู่แล้ว)
    print(">", " ".join(args))
    result = subprocess.run(args, cwd=ROOT)
    if check and result.returncode != 0:
        print("ไม่สำเร็จ หยุดตรงนี้ (ดู error ด้านบน)")
        sys.exit(1)


def mpremote(port, *args, check=True):
    run([sys.executable, "-m", "mpremote", "connect", port] + list(args), check)


def main():
    if len(sys.argv) < 2:
        print("ใช้แบบนี้: python tools/upload_board.py COM3")
        return
    port = sys.argv[1]

    # 1) แปลโค้ดบนคอม
    os.makedirs(BUILD, exist_ok=True)
    for src, dest in SOURCES:
        run([sys.executable, "-m", "mpy_cross", "-o", os.path.join(BUILD, dest), src])

    # 2) ลบ .py ตัวเก่าบนบอร์ด (กันบอร์ดไปใช้ .py แทน .mpy) · ไม่มีอยู่แล้วก็ไม่เป็นไร
    for src, dest in SOURCES:
        mpremote(port, "rm", ":" + dest.replace(".mpy", ".py"), check=False)

    # 3) อัปโหลด
    for src, dest in SOURCES:
        mpremote(port, "cp", os.path.join(BUILD, dest), ":" + dest)
    mpremote(port, "cp", "esp32/main.py", ":main.py")
    print("\nเสร็จแล้ว · กดปุ่ม EN บนบอร์ดเพื่อเริ่มใหม่")


if __name__ == "__main__":
    main()
