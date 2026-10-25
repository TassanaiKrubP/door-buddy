# อ่าน/เขียนไฟล์ของโปรเจกต์: json ตั้งค่า, data/state.json, data/events.csv
import csv
import json
import os
import shutil

# โฟลเดอร์หลักของโปรเจกต์ (อยู่เหนือ pc/ หนึ่งชั้น)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS = "data/events.csv"
EVENT_HEADER = ["date", "time", "event", "secs", "detail"]


def ensure_from_example(name):
    # ไฟล์ข้อมูลของผู้ใช้ยังไม่มี (เช่น เพิ่ง clone จาก GitHub) -> คัดลอกจาก <ชื่อ>.example.json
    # rules.json / activities.json เป็นข้อมูลส่วนตัว ไม่ขึ้น git (ดู .gitignore)
    path = os.path.join(ROOT, name)
    if not os.path.exists(path):
        shutil.copy(path.replace(".json", ".example.json"), path)


def load_json(name):
    # อ่านไฟล์ json จากโฟลเดอร์หลัก เช่น load_json("config.json")
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def save_json(name, data):
    # เขียนไฟล์ json (ภาษาไทยอ่านออก ไม่เป็น \uXXXX) · สร้างโฟลเดอร์ให้ถ้ายังไม่มี
    path = os.path.join(ROOT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# แถวที่ยังเขียนไม่ได้ (เช่น เปิดไฟล์ค้างใน Excel ซึ่งล็อกไฟล์ไว้) รอเขียนรอบหน้า
pending_events = []


def append_event(row):
    # เพิ่ม 1 แถวต่อท้าย data/events.csv · row = [date, time, event, secs, detail]
    # ไฟล์ใหม่ใส่หัวตารางให้ · utf-8-sig ให้ Excel เปิดภาษาไทยได้
    # เขียนไม่ได้ = เก็บไว้ใน pending_events แล้วลองใหม่ครั้งหน้า (โปรแกรมไม่ล้ม) · คืน True ถ้าเขียนได้
    pending_events.append(row)
    path = os.path.join(ROOT, EVENTS)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        is_new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8-sig" if is_new else "utf-8", newline="") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(EVENT_HEADER)
            writer.writerows(pending_events)
    except OSError:
        return False
    pending_events.clear()
    return True
