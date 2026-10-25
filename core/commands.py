# แยกคำสั่งจากข้อความแชท (จับคำแบบง่าย ไม่ใช้ AI)
# ห้ามทำ I/O (กติกา core/) · คืนเป็น dict ให้ฝั่ง pc ไปทำต่อ


def after(text, word):
    # ข้อความหลังคำนำหน้า เช่น after("ลืมร่ม", "ลืม") -> "ร่ม"
    return text[len(word):].strip()


def parse_command(text, found, activities, time=None):
    # text       = ข้อความที่ผู้ใช้พิมพ์
    # found      = (date_key, ข้อความที่เหลือ) จาก thai_dt ฝั่ง pc หรือ None ถ้าไม่เจอวัน
    # activities = dict จาก activities.json
    # time       = "HH:MM" ถ้าในข้อความมีเวลา (= นัด) หรือ None
    text = text.strip()

    # คำสั่งขึ้นต้นด้วย / (ตัวพิมพ์เล็ก/ใหญ่ได้หมด เช่น /List)
    if text.startswith("/"):
        word = text.split(" ")[0].lower()
        if word == "/help" or word == "/start":
            return {"cmd": "help"}
        if word == "/status":
            return {"cmd": "status"}
        if word == "/list":
            # "/list" = วันนี้ · "/list พรุ่งนี้" = วันที่หาได้ · มีคำต่อท้ายแต่หาวันไม่ได้ = ผิด
            if found is not None:
                return {"cmd": "list", "date": found[0]}
            if text[len(word):].strip() != "":
                return {"cmd": "bad_date"}
            return {"cmd": "list", "date": None}

    # ปิดเตือน: มีคำว่า "ไม่ต้องเตือน" ตรงไหนก็ได้ (เช่น "วันนี้ไม่ต้องเตือนนะ")
    # มีวัน = ปิดล่วงหน้าวันนั้น · ไม่มีวัน = วันนี้ (ต้องเช็กก่อนหาวัน เพราะมีคำว่า "วันนี้")
    if "ไม่ต้องเตือน" in text:
        date = None
        if found is not None:
            date = found[0]
        return {"cmd": "no_alert", "date": date}
    if text == "เปิดเตือน":
        return {"cmd": "alert_on"}
    if text == "ยังอยู่ห้อง":
        return {"cmd": "still_home"}
    if text == "ออกแล้ว":
        return {"cmd": "out_now"}
    if text == "นัด" or text == "/appts":
        return {"cmd": "list_appts"}

    # ลบนัด (ต้องเช็กก่อน "ลบ X") · "ลบนัด 25/10" = ทั้งวัน · "ลบนัด 25/10 8โมง" = เฉพาะเวลานั้น
    if text.startswith("ลบนัด"):
        if found is None:
            return {"cmd": "remove_appt", "date": None, "time": None}
        return {"cmd": "remove_appt", "date": found[0], "time": time}

    # คำสั่งที่มีชื่อของต่อท้าย
    if text.startswith("ลืม") and after(text, "ลืม") != "":
        item = after(text, "ลืม")
        if item.startswith("เอา") and after(item, "เอา") != "":
            item = after(item, "เอา")              # "ลืมเอาร่ม" -> ร่ม
        return {"cmd": "forget", "item": item}
    if text.startswith("เพิ่ม") and text.endswith("ทุกวัน"):
        name = after(text[:-len("ทุกวัน")], "เพิ่ม")
        if name != "":
            return {"cmd": "add_always", "item": name}
    if text.startswith("ลบ") and after(text, "ลบ") != "":
        return {"cmd": "remove", "item": after(text, "ลบ")}

    # มีวัน + เวลา = นัด (ถ้าชื่อนัดตรงกับกิจกรรม แนบของของกิจกรรมไปด้วย)
    if found is not None and time is not None:
        name = found[1]
        if name == "":
            name = "นัด"
        items = []
        if name in activities and not name.startswith("_"):
            items = list(activities[name])
        return {"cmd": "add_appointment", "date": found[0], "time": time,
                "name": name, "items": items}

    # มีวัน + ข้อความ = สั่งกิจกรรม/ของล่วงหน้า
    if found is not None and found[1] != "":
        rest = found[1]
        if rest in activities and not rest.startswith("_"):
            return {"cmd": "add_activity", "date": found[0],
                    "name": rest, "items": list(activities[rest])}
        return {"cmd": "add_item", "date": found[0], "items": [rest]}

    return {"cmd": "none"}
