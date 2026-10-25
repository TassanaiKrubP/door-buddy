# เน็ตของบอร์ด: ต่อ Telegram แบบ HTTPS ค้างสายไว้ 1 สาย (keep-alive) ใช้แทน requests
# ทำไม (ผลจาก memcheck.py):
#   - ต่อ HTTPS ใหม่ทุกครั้ง = ต้องจองหน่วยความจำก้อนใหญ่ทุกครั้ง หลังโหลดแอปแล้ว
#     หน่วยความจำเหลือแต่ชิ้นเล็ก ๆ (tls block 49152 -> 30720 -> 21504) สุดท้าย HTTPS พัง/ค้าง
#   - วิธีนี้: ต่อสายครั้งเดียวตอนเปิดเครื่อง (ก่อนโหลดแอป ตอนหน่วยความจำยังว่างเป็นก้อนใหญ่)
#     แล้วใช้สายเดิมตลอด · ได้ผลพลอยได้คือเร็วขึ้นมาก (เดิมต่อใหม่ทุกครั้ง 2.5-5.7 วิ)
#   - อากาศ (Open-Meteo) ใช้ HTTP ธรรมดา ไม่เข้ารหัส -> ไม่แย่งหน่วยความจำส่วน HTTPS
import errno
import gc
import json
import socket
import time

import network

try:
    import tls
except ImportError:
    import ssl as tls

HOST = "api.telegram.org"
TIMEOUT = 15            # วิ · เน็ตเงียบนานเกินนี้ = ตัดสายแล้วค่อยต่อใหม่ (ไม่ค้างตลอดไป)

token = ""              # อ่านจาก secrets.json ตอน start()
_wifi = ("", "")
_sock = None            # สาย HTTPS ที่ค้างไว้ (None = ยังไม่ต่อ / หลุดไปแล้ว)


def mem_info():
    # สรุปหน่วยความจำไว้ไล่ปัญหา
    #   gc  = ของ Python (เหลือ / ทั้งหมด · "ทั้งหมด" เพิ่มขึ้น = heap ขยายไปกินของระบบ)
    #   idf = ของระบบที่ WiFi + HTTPS ใช้ (เหลือรวม / ก้อนใหญ่สุด · ตอนสายต่ออยู่ก้อนเล็กเป็นปกติ)
    try:
        import esp32
        info = esp32.idf_heap_info(esp32.HEAP_DATA)
        idf = "idf {} / block {}".format(sum(h[1] for h in info), max(h[2] for h in info))
    except Exception:
        idf = "idf ?"
    return "gc {} / {} | {}".format(gc.mem_free(), gc.mem_free() + gc.mem_alloc(), idf)


def wifi():
    # ต่อ WiFi (ต่ออยู่แล้วก็ไม่ทำอะไร) · รอไม่เกิน 15 วิ
    # WiFi หลุดแล้วชิปพยายามต่อใหม่เอง -> ห้ามสั่ง connect ซ้ำตอนนั้น
    #   (ทดสอบแล้ว: error "Wifi Internal State Error" วนทุก 3 วิ และต่อไม่ติด) -> แค่รอ
    # ไม่ปิดโหมดประหยัดไฟ WiFi (ทดสอบแล้วไม่ช่วยเรื่องช้า แต่บอร์ดร้อนขึ้น)
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return wlan
    if not wlan.active():
        wlan.active(True)
    if wlan.status() != network.STAT_CONNECTING:
        try:
            wlan.connect(_wifi[0], _wifi[1])
        except OSError:
            print("wifi: already connecting, wait")   # ชิปกำลังต่ออยู่แล้ว ไม่ใช่ปัญหา
    for _ in range(30):
        if wlan.isconnected():
            break
        time.sleep_ms(500)
    print("wifi:", wlan.isconnected())
    return wlan


def start():
    # เรียกตอนเปิดเครื่อง ก่อนโหลดแอป: อ่านรหัส -> ต่อ WiFi -> ต่อสาย Telegram ไว้เลย
    # เรียกซ้ำได้ (อ่านรหัสครั้งเดียว · ต่ออยู่แล้วก็ไม่ต่อใหม่)
    global token, _wifi
    if not token:
        with open("secrets.json") as f:
            s = json.load(f)
        token = s["TELEGRAM_TOKEN"]
        _wifi = (s["WIFI_SSID"], s["WIFI_PASS"])
    wlan = wifi()
    if wlan.isconnected() and _sock is None:
        print("net: before connect |", mem_info())
        try:
            _open()
        except Exception as e:
            print("net: connect failed", e)      # ไม่เป็นไร เดี๋ยวต่อใหม่ตอนเรียกครั้งแรก
    return wlan


def close():
    global _sock
    if _sock is not None:
        try:
            _sock.close()
        except Exception:
            pass
        _sock = None


def _open():
    # ต่อสาย HTTPS ใหม่ไป Telegram
    global _sock
    close()
    gc.collect()
    t0 = time.ticks_ms()
    addr = socket.getaddrinfo(HOST, 443, 0, socket.SOCK_STREAM)[0][-1]
    raw = socket.socket()
    try:
        raw.settimeout(TIMEOUT)
        raw.connect(addr)
        ctx = tls.SSLContext(tls.PROTOCOL_TLS_CLIENT)
        ctx.verify_mode = tls.CERT_NONE          # ไม่ตรวจใบรับรอง (เหมือน requests เดิม)
        _sock = ctx.wrap_socket(raw, server_hostname=HOST)
    except Exception:
        raw.close()
        raise
    gc.collect()
    print("net: telegram connected", time.ticks_diff(time.ticks_ms(), t0), "ms |", mem_info())


def _read_response(s):
    # อ่านคำตอบ HTTP -> (status, เนื้อหา bytes, ใช้สายต่อได้ไหม) · None = เซิร์ฟเวอร์ปิดสายไปแล้ว
    line = s.readline()
    if not line:
        return None
    status = int(line.split()[1])
    length = -1
    chunked = False
    keep = True
    while True:                                   # หัวข้อความ (header) จนเจอบรรทัดว่าง
        line = s.readline().decode().strip().lower()
        if not line:
            break
        if line.startswith("content-length:"):
            length = int(line[15:])
        elif line.startswith("transfer-encoding:") and "chunked" in line:
            chunked = True
        elif line.startswith("connection:") and "close" in line:
            keep = False
    if chunked:                                   # ส่งมาเป็นท่อน ๆ: [ความยาวฐาน 16] [ข้อมูล]
        parts = []
        while True:
            n = int(s.readline().decode().split(";")[0], 16)
            if n == 0:
                s.readline()
                break
            parts.append(s.read(n))
            s.readline()
        body = b"".join(parts)
    elif length >= 0:
        body = s.read(length) if length else b""
        if len(body) < length:
            raise OSError("short reply")
    else:                                         # ไม่บอกความยาว = อ่านจนเซิร์ฟเวอร์ปิดสาย
        body = s.read()
        keep = False
    return status, body, keep


def call(method, data):
    # เรียก Telegram 1 ครั้งผ่านสายที่ค้างไว้ -> dict · พลาด = ตัดสายทิ้งแล้วโยน error ให้คนเรียก
    # สายเก่าตายไปแล้ว (เซิร์ฟเวอร์ปิดเพราะเงียบนาน) -> ต่อใหม่แล้วลองอีกรอบเดียว
    body = json.dumps(data).encode()
    head = ("POST /bot" + token + "/" + method + " HTTP/1.1\r\nHost: " + HOST
            + "\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body))
            + "\r\n\r\n").encode()
    for last_try in (False, True):
        reused = _sock is not None
        if not reused:
            _open()
        try:
            _sock.write(head + body)              # ส่งก้อนเดียว (แพ็กเก็ตน้อยลง)
            resp = _read_response(_sock)
        except Exception as e:
            close()
            timeout = isinstance(e, OSError) and e.args and e.args[0] == errno.ETIMEDOUT
            if not reused or last_try or timeout:  # timeout ไม่ลองซ้ำ (กันส่งข้อความซ้ำ)
                raise
            print("net: old connection dead, reconnect")
            continue
        if resp is None:                           # เซิร์ฟเวอร์ปิดสายก่อนตอบ
            close()
            if not reused or last_try:
                raise OSError("closed by server")
            print("net: old connection closed, reconnect")
            continue
        status, reply, keep = resp
        if not keep:
            close()
        return json.loads(reply)


def get_http(host, path):
    # GET แบบ HTTP ธรรมดา (ไม่เข้ารหัส) -> dict · ขอแบบ HTTP/1.0 เซิร์ฟเวอร์ส่งจบแล้วปิดสายเอง
    addr = socket.getaddrinfo(host, 80, 0, socket.SOCK_STREAM)[0][-1]
    s = socket.socket()
    try:
        s.settimeout(TIMEOUT)
        s.connect(addr)
        s.write(("GET " + path + " HTTP/1.0\r\nHost: " + host + "\r\n\r\n").encode())
        resp = _read_response(s)
    finally:
        s.close()
    if resp is None or resp[0] != 200:
        raise OSError("http " + (str(resp[0]) if resp else "closed"))
    return json.loads(resp[1])
