# ไฟล์ที่บอร์ดรันเองทุกครั้งที่เปิดไฟ -> อ่านประตูแล้วส่งให้คอมทาง WiFi (door_sensor.mpy)
# ถ้ามีไฟล์ชื่อ nostart บนบอร์ด จะไม่เริ่ม (ไว้ใช้ตอนอยากสั่งบอร์ดจากคอมเอง)
# (แบบเดิมที่บอร์ดคุย Telegram เอง = app.py + net.py เก็บไว้เป็นประวัติ ไม่ได้ใช้แล้ว)
try:
    open("nostart").close()
    print("nostart: not starting (delete file nostart to auto start)")
except OSError:
    import door_sensor
    door_sensor.main()
