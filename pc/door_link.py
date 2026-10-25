# รับสถานะประตูจากบอร์ด ESP32 ผ่าน WiFi (UDP) · ทำงานใน thread แยก ลูปหลักไม่ต้องรอ
# บอร์ดส่งข้อความสั้น ๆ (JSON) ทุกครั้งที่ประตูเปลี่ยน (ส่งซ้ำ 3 รอบกันหาย) + ทุก 2 วิ (บอกว่ายังอยู่)
#   {"boot": 52817, "seq": 7, "door": "open", "age": 120}
#   boot = เลขสุ่มตอนบอร์ดเปิด (เปลี่ยน = บอร์ดรีสตาร์ท)
#   seq  = ประตูเปลี่ยนครั้งที่เท่าไร (เลขเดิม = ข้อความซ้ำ ไม่นับ)
#   age  = ประตูเปลี่ยนมาแล้วกี่ ms -> คอมรู้เวลาที่ประตูขยับจริง โดยไม่ต้องตั้งนาฬิกาบอร์ด
# ทำไม UDP: บอร์ดไม่ต้องรู้ IP ของคอม (ส่งกระจายทั้งวง WiFi) และไม่ต้องใช้ HTTPS (บอร์ด RAM ไม่พอ)
import json
import queue
import socket
import threading
import time

PORT = 4210
OFFLINE_SEC = 10        # ไม่ได้ยินบอร์ดนานเกินนี้ = ออฟไลน์ (บอร์ดส่งทุก 2 วิ)


class DoorTracker:
    # แปลงข้อความจากบอร์ด -> เหตุการณ์ประตู (แยกจาก thread เพื่อให้เทสต์ได้)

    def __init__(self):
        self.boot = None
        self.seq = None
        self.door = None
        self.last_seen = None      # เวลาที่ได้ยินบอร์ดล่าสุด (epoch)

    def feed(self, data, recv_time):
        # รับข้อความ 1 ก้อน -> list ของ (ประตู, เวลาที่ขยับจริง, จริงไหม)
        #   จริงไหม = False: ได้ยินบอร์ดครั้งแรก / บอร์ดรีสตาร์ท -> แค่บอกสถานะ ไม่ใช่การเปิดปิด
        # ข้อความไม่ถูกรูปแบบ = ValueError / KeyError / TypeError
        msg = json.loads(data)
        boot = msg["boot"]
        seq = int(msg["seq"])
        door = msg["door"]
        age = int(msg.get("age", 0))
        if door not in ("open", "close"):
            raise ValueError("bad door: " + str(door))
        self.last_seen = recv_time
        if boot != self.boot:                  # บอร์ดใหม่ / เพิ่งรีสตาร์ท
            self.boot = boot
            self.seq = seq
            self.door = door
            return [(door, recv_time, False)]
        if seq <= self.seq:                    # ข้อความซ้ำ หรือมาช้า (เก่ากว่าที่รู้แล้ว)
            return []
        self.seq = seq
        if door == self.door:                  # พลาดไปคู่หนึ่ง (เปิด+ปิด) สถานะเท่าเดิม
            return []
        self.door = door
        return [(door, recv_time - age / 1000, True)]


class DoorLink:
    # thread ฟังข้อความจากบอร์ด · ลูปหลักหยิบเหตุการณ์ด้วย get_events()

    def __init__(self, port=PORT):
        self.tracker = DoorTracker()
        self.events = queue.Queue()
        self.ip = None                         # IP ของบอร์ด (ไว้แสดงในสถานะ)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", port))             # พอร์ตถูกใช้อยู่ = OSError (คนเรียกจัดการ)
        self.sock.settimeout(1)
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                time.sleep(1)
                continue
            try:
                events = self.tracker.feed(data, time.time())
                self.ip = addr[0]
                for event in events:
                    self.events.put(event)
            except (ValueError, KeyError, TypeError):
                pass                           # ข้อความแปลก (ไม่ใช่ของบอร์ดเรา) ไม่สนใจ

    def get_events(self):
        # หยิบเหตุการณ์ทั้งหมดที่รับมาแล้ว (ไม่รอ)
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def online(self, now_epoch):
        seen = self.tracker.last_seen
        return seen is not None and now_epoch - seen < OFFLINE_SEC

    def seconds_since_seen(self, now_epoch):
        seen = self.tracker.last_seen
        return None if seen is None else int(now_epoch - seen)
