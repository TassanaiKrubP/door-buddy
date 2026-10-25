# จำลองสถานการณ์เข้าออกห้องกับ core/guard.py ตัวจริง (ค่าใน config.json จริง + ตารางเรียนจำลอง)
# ใช้ตรวจตรรกะ "ควรเตือนไหม" ในเวลาจริง (OUT_DELAY 10 วิ, ช่วงเตือน 90 นาที) ซึ่งโหมดเดโมแสดงไม่ได้
# เดินเวลาทีละวินาที ส่งเปิด/ปิดประตูตามเวลาที่กำหนด แล้วเทียบผลกับที่ควรเป็น
#
# รัน (ในโฟลเดอร์ door_buddy):  python tools/scenarios.py
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.guard import DoorGuard  # noqa: E402

SHOW = ("checklist", "checklist_quiet")      # สิ่งที่ผู้ใช้ได้รับ (เช็คลิสต์)
TUE = 27                                     # อังคาร 27 ต.ค. ไม่มีเรียน (ช่วงปกติ 08:00-11:00)
MON = 26                                     # จันทร์ 26 ต.ค. คาบแรก 09:00 (ช่วงเตือน 07:30-09:00)
# ตารางเรียนของการจำลอง (ไม่อ่าน timetable.json จริง ผู้ใช้จะแก้ไฟล์นั้นยังไงผลก็เหมือนเดิม)
TIMETABLE = [{"day": "mon", "start": "09:00", "end": "12:00", "subject": "วิชา A"}]


def load(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def epoch(day, text):
    # "HH:MM[:SS]" ของวัน day -> วินาที · ชั่วโมง >= 24 = วันถัดไป (เช่น "26:30" = 02:30)
    parts = [int(x) for x in text.split(":")] + [0]
    return day * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def trip(out_t, back_t=None):
    # ออกจากห้อง = เปิด แล้วปิดใน 5 วิ · กลับ = เปิด แล้วปิดใน 5 วิ
    events = [(out_t, "open"), (out_t + ":05", "close")]
    if back_t:
        events += [(back_t, "open"), (back_t + ":05", "close")]
    return events


def run(day, appts, events, start="05:00", end="12:00"):
    # คืน list ของ "HH:MM ชนิด" ที่ผู้ใช้ได้รับ
    appointments = {}
    for d, t in appts:
        appointments.setdefault("2026-10-%02d" % d, []).append({"time": t, "name": "นัด " + t})
    guard = DoorGuard(load("config.json"), TIMETABLE, appointments)
    todo = sorted((epoch(day, t), kind) for t, kind in events)
    got = []
    for t in range(epoch(day, start), epoch(day, end) + 1):
        d, sod = t // 86400, t % 86400
        now = (t, (2026, 10, d, sod // 3600, sod // 60 % 60, sod % 60, (d - 26) % 7))
        actions = []
        while todo and todo[0][0] == t:
            actions += guard.on_door(todo.pop(0)[1], now)
        actions += guard.tick(now)
        for a in actions:
            if a["do"] in SHOW:
                got.append("%02d:%02d %s" % (now[1][3], now[1][4], a["do"]))
    return got


# (ชื่อ, วัน, นัด, เหตุการณ์, ที่ควรได้, ช่วงเวลาจำลอง, ข้อจำกัดที่รู้อยู่แล้ว)
C = "checklist"
SCENARIOS = [
    # เวลาที่ได้รับ = เวลาปิดประตู + OUT_DELAY (10 วิ) -> นาทีเดียวกับที่ออก
    ("นัด 7:30 · ซื้อข้าว 6:30-6:50 · ออกไปนัด 7:10", TUE, [(TUE, "07:30")],
     trip("06:30", "06:50") + trip("07:10"), ["06:30 " + C, "07:10 " + C], None, None),
    ("นัด 7:30 · ซื้อข้าว 6:30-7:10 · ออกไปนัด 7:20", TUE, [(TUE, "07:30")],
     trip("06:30", "07:10") + trip("07:20"), ["06:30 " + C, "07:20 " + C], None, None),
    ("นัด 7:30 · ออก 7:30:50 (ตรงเวลานัดพอดี ยืนยันว่าออกตอน 7:31)", TUE, [(TUE, "07:30")],
     [("07:30:45", "open"), ("07:30:50", "close")], ["07:31 " + C], None, None),
    ("นัด 7:30 · ออกสาย 7:35 (เลยเวลานัด)", TUE, [(TUE, "07:30")], trip("07:35"), [], None, None),
    ("ทิ้งขยะ 6:30 (กลับภายใน 10 วิ) · ออกจริง 6:40", TUE, [(TUE, "07:30")],
     [("06:30", "open"), ("06:30:02", "close"), ("06:30:08", "open"), ("06:30:10", "close")]
     + trip("06:40"), ["06:40 " + C], None, None),
    ("เข้าออก 3 รอบก่อนนัด 7:30", TUE, [(TUE, "07:30")],
     trip("06:10", "06:20") + trip("06:30", "06:40") + trip("07:00"),
     ["06:10 " + C, "06:30 " + C, "07:00 " + C], None, None),
    ("สองนัด 7:30 + 9:00 · ออก 7:00 กลับ 8:00 ออก 8:30", TUE, [(TUE, "07:30"), (TUE, "09:00")],
     trip("07:00", "08:00") + trip("08:30"), ["07:00 " + C, "08:30 " + C], None, None),
    ("จันทร์เรียน 9:00 + นัด 8:00 · ไปนัด 7:40 กลับ 8:20 ไปเรียน 8:40", MON, [(MON, "08:00")],
     trip("07:40", "08:20") + trip("08:40"), ["07:40 " + C, "08:40 " + C], None, None),
    ("วันไม่มีเรียน ไม่มีนัด · ออก 8:30 (ช่วง 8-11)", TUE, [], trip("08:30"), ["08:30 " + C],
     None, None),
    ("นัดหลังเที่ยงคืน 00:30 · ออก 23:40", MON, [(TUE, "00:30")], trip("23:40"), ["23:40 " + C],
     ("23:00", "25:00"), None),
    ("กลับดึก 02:30 (ก่อนรีเซ็ตตี 3) · เช้าออก 7:00 นัด 7:30", MON, [(TUE, "07:30")],
     trip("22:00", "26:30") + trip("31:00"), ["07:00 " + C], ("21:00", "32:00"), None),
    ("กลับดึก 03:30 (หลังรีเซ็ตตี 3) · เช้าออก 7:00 นัด 7:30", MON, [(TUE, "07:30")],
     trip("22:00", "27:30") + trip("31:00"), ["07:00 checklist_quiet"], ("21:00", "32:00"),
     "ระบบเห็นการออกตอนเช้าเป็น 'กลับห้อง' -> ส่งเช็คลิสต์แบบเงียบ + ปุ่ม 'จริง ๆ กำลังออก'"),
    ("เปิดประตูใส่รองเท้า 40 วิ แล้วออก (ไม่ถึง 1 นาที)", TUE, [(TUE, "07:30")],
     [("06:30", "open"), ("06:30:40", "close")], ["06:30 " + C], None, None),
    ("เปิดประตูยืนคุย 70 วิ แล้วออก ปิดจากข้างนอก", TUE, [(TUE, "07:30")],
     [("06:30", "open"), ("06:31:10", "close")], [], None,
     "เปิดค้างเกิน 1 นาทีแล้วปิด = ถือว่าปิดจากในห้อง -> ไม่เตือน"),
    ("แวะกลับมาเปิด-ปิดหยิบของแล้วออกเลย · กลับจริง 9:30", TUE, [(TUE, "07:30")],
     trip("06:30") + [("07:00", "open"), ("07:00:10", "close")] + trip("09:30"),
     ["06:30 " + C, "09:30 " + C], None,
     "ระบบคิดว่ากลับห้องตอน 7:00 -> ตอนกลับจริง 9:30 เตือนผิด (แก้ด้วยปุ่ม 'ยังไม่ได้ออก')"),
]


def main():
    passed = 0
    limits = 0
    for i, (name, day, appts, events, expect, span, limit) in enumerate(SCENARIOS, 1):
        start, end = span or ("05:00", "12:00")
        got = run(day, appts, events, start, end)
        ok = got == expect
        mark = "ผ่าน" if ok else "ไม่ผ่าน"
        if ok and limit:
            mark = "ข้อจำกัด"
            limits += 1
        elif ok:
            passed += 1
        print("%2d. [%s] %s" % (i, mark, name))
        print("      ได้รับ: " + (", ".join(got) if got else "(ไม่มีเช็คลิสต์)"))
        if not ok:
            print("      ควรได้: " + (", ".join(expect) if expect else "(ไม่มีเช็คลิสต์)"))
        if limit:
            print("      หมายเหตุ: " + limit)
    print()
    print("สรุป: ผ่าน %d · ข้อจำกัดที่รู้อยู่แล้ว %d · ไม่ผ่าน %d (จาก %d สถานการณ์)"
          % (passed, limits, len(SCENARIOS) - passed - limits, len(SCENARIOS)))


if __name__ == "__main__":
    main()
