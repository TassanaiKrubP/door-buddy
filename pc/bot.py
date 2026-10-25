# เมนูปุ่มในแชท (ปุ่มซ้อนเป็นชั้น) + ถามทีละขั้น (wizard) สำหรับเพิ่มนัด / เพิ่มของ
#
# กดปุ่มล่าง        -> ส่งเมนูใหม่ (ปุ่มติดข้อความ)
# กดปุ่มในเมนู      -> แก้ข้อความเดิมเป็นชั้นถัดไป (แชทไม่รก) · ทุกชั้นมีปุ่ม กลับ
# พิมพ์เองแบบเดิม   -> ส่งให้ App.run_command เหมือนเดิม
#
# โครงเมนู (ปุ่มล่าง: เช็คลิสต์ / นัด / ประจำสัปดาห์ / ของ / อื่น ๆ)
#   เช็คลิสต์ -> วันนี้ / พรุ่งนี้ / เลือกวัน
#   นัด       = ครั้งเดียว (หาหมอ เตะบอล เดต) -> ดูนัด / เพิ่มนัด (วัน -> เวลา -> ชื่อ -> ของ) / ลบนัด
#                / นัดที่บันทึกไว้ (ชื่อ+ของที่ระบบจำเองตอนบันทึกนัด ลบได้)
#   ประจำสัปดาห์ = ซ้ำทุกสัปดาห์ (เรียน ML ทุกจันทร์ 09:00) -> ดูกิจกรรม (ทีละวัน) / เพิ่มกิจกรรม
#                / ลบกิจกรรม / งดบางสัปดาห์
#   ของ       -> ดูของ / เพิ่มของ / ลบของ -> พกทุกวัน / เฉพาะวัน (พกทั้งวัน) / ของสำหรับนัด
#                / ของสำหรับประจำสัปดาห์
#                (ข้อมูลข้างใน: ทั้งวัน = by_date · ของของนัด = appointments[..]["items"]
#                 · ของของประจำสัปดาห์ = weekly[..]["items"])
#   อื่น ๆ    -> วันนี้ไม่ต้องเตือน (หรือ เปิดเตือนกลับ) / สถานะ / วิธีใช้ / เคลียร์ข้อมูล
#
# ChatBot ไม่ส่งข้อความเอง แต่คืน list ของ "out" ให้ App ส่ง (เทสต์ได้โดยไม่ต้องมีเน็ต)
#   {"send": ข้อความ, "buttons": ..., "silent": False}   ส่งข้อความใหม่
#   {"edit": message_id, "text": ..., "buttons": ...}   แก้ข้อความเดิม
#
# data ของปุ่ม (Telegram จำกัด 64 byte -> ใช้อักษรอังกฤษ/ตัวเลขสั้น ๆ)
#   m:<หน้า>                  ไปหน้าเมนู (ดูชื่อหน้าใน page())
#   l:<วัน>                   ดูเช็คลิสต์วันนั้น       d:<วัน>  หน้าของเฉพาะวันนั้น (ลบ/เพิ่ม)
#   sa:<วัน>                  เพิ่มของเฉพาะวัน: เลือกว่าให้ทั้งวัน หรือนัดไหน
#   x:aall x:call x:cdall x:tall   เคลียร์ (นัด / พกทุกวัน / เฉพาะวัน / กิจกรรมประจำ) ออกทั้งหมด
#                             ถามยืนยันก่อน · ใส่ ! ท้าย (เช่น x:call!) = เคลียร์จริง · อยู่ในเมนู อื่น ๆ
#   a:new                     เริ่มเพิ่มนัด -> ad:<วัน>  ah:<ชม>  an:<เลขกิจกรรม>  ai:<เลขของ>  ai:done
#   w:always  w:date:<วัน>    เริ่มเพิ่มของ           w:cancel  ยกเลิกที่กำลังถาม
#   <นัด> = <วัน>:<ลำดับในวันนั้น>:<HHMM>  อ้างถึงนัด 1 อัน (เวลาไว้เช็กว่ายังเป็นนัดเดิม)
#   w:appt:<นัด>              เพิ่มของให้นัด         p:<นัด>  (ปุ่มเก่า) = หน้าของวันของนัดนั้น
#   x:a:<นัด>                 ลบนัด
#   x:i:<เลข>:<จำนวน>         ลบของทุกวัน   x:d:<วัน>:<เลข>:<จำนวน>  ลบของเฉพาะวัน
#   x:p:<นัด>:<เลข>:<จำนวน>   ลบของของนัด
#   wk:new                    เริ่มเพิ่มกิจกรรมประจำ -> wd:<mon..sun>  ah:<ชม>  ai:...
#   wi:<เลข>:<จำนวน>          เพิ่มของให้กิจกรรมประจำ   wx:<เลข>:<จำนวน>  หน้าลบของของกิจกรรมนั้น
#   x:wi:<เลข>:<ชิ้น>:<จำนวนชิ้น>  ลบของ 1 ชิ้นของกิจกรรมประจำ
#   x:t:<เลข>:<จำนวน>         ลบนัดที่บันทึกไว้ (ชื่อ+ของ · ไม่ลบนัดที่ลงวันไว้)
#   x:w:<เลข>:<จำนวน>         ลบกิจกรรมประจำ   ws:<วัน>:<เลข>:<จำนวน>  งด/ยกเลิกงด เฉพาะวันนั้น
#   r:<นัด>                   (ปุ่มเก่า) จำนัดนี้ไว้เป็นชื่อให้เลือก · ตอนนี้ระบบจำชื่อนัดเองทุกครั้ง
#   o:noalert o:alerton o:status o:help o:home o:out     อื่น ๆ
#   o:demo (สลับโหมด · เปิดต้องยืนยัน o:demo!)
#
# กันล้น: ของต่อนัด/ต่อครั้ง ไม่เกิน MAX_ITEMS · ปุ่มกิจกรรมแสดงแค่ MAX_ACTIVITY_BUTTONS อันล่าสุด
import datetime

from pc import storage
from pc import thai_dt
from pc.telegram import MAIN_BUTTONS

# ปุ่มล่าง -> หน้าเมนู
MAIN_PAGES = {MAIN_BUTTONS[0][0]: "list", MAIN_BUTTONS[0][1]: "appt",
              MAIN_BUTTONS[1][0]: "acts", MAIN_BUTTONS[1][1]: "items",
              MAIN_BUTTONS[2][0]: "other"}
MENU_WORDS = ["/menu", "เมนู", "ปุ่ม"]  # พิมพ์คำนี้ = เรียกปุ่มล่างกลับมา
MENU_BACK = ("ปุ่มเมนูกลับมาแล้ว (ดูด้านล่าง)\n"
             "(ถ้าหายอีก พิมพ์ เมนู หรือกดปุ่ม Menu ข้างช่องพิมพ์ แล้วเลือก /menu)")
WIZARD_TIMEOUT = 300         # ถามค้างไว้เกินกี่วินาที = ยกเลิกเอง
MAX_ITEMS = 10                # ของต่อนัด / ต่อการเพิ่ม 1 ครั้ง (กันปุ่มเกินที่ Telegram รับ)
MAX_ACTIVITY_BUTTONS = 6      # ขั้นเลือกชื่อนัด แสดงกิจกรรมที่ใช้ล่าสุดกี่อัน
MAX_LIST = 40                 # หน้ารายการให้กดลบ แสดงไม่เกินกี่อัน (กันปุ่มเกินที่ Telegram รับ)
THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEK_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]
CANCEL = [("ยกเลิก", "w:cancel")]
EXPIRED = "เมนูนี้หมดอายุแล้ว กดปุ่มด้านล่างเพื่อเริ่มใหม่"
KIND_HELP = ("{}ของแบบไหน\n"
             "- พกทุกวัน = ขึ้นในเช็คลิสต์ทุกวัน (เช่น กุญแจ)\n"
             "- เฉพาะวัน = พกทั้งวันของวันที่เลือก (เช่น ร่มวันศุกร์)\n"
             "- ของสำหรับนัด = เอาไปนัดไหน (เช่น ชุดบอลไปเตะบอล)\n"
             "- ของสำหรับประจำสัปดาห์ = เอาไปกิจกรรมทุกสัปดาห์ (เช่น โน้ตบุ๊กไปเรียน ML)")
# ปุ่มเคลียร์ (เมนู อื่น ๆ > เคลียร์ข้อมูล): data -> (ข้อความบนปุ่ม, คำถามยืนยัน)
CLEAR = {"aall": ("เคลียร์นัดออกทั้งหมด", "เคลียร์นัดออกทั้งหมด รวมของของนัดด้วย"),
         "call": ("เคลียร์ของพกทุกวันออกทั้งหมด", "เคลียร์ของพกทุกวันออกทั้งหมด"),
         "cdall": ("เคลียร์ของเฉพาะวันออกทั้งหมด",
                   "เคลียร์ของเฉพาะวันออกทั้งหมด (ทั้งวัน + ของของนัด · ตัวนัดยังอยู่)"),
         "tall": ("เคลียร์กิจกรรมประจำออกทั้งหมด",
                  "เคลียร์กิจกรรมประจำ (ที่ซ้ำทุกสัปดาห์) ออกทั้งหมด (นัดที่บันทึกไว้ยังอยู่)")}
CLEAR_ORDER = ["aall", "call", "cdall", "tall"]
MORE = "(แสดง {} อันแรก ลบบางอันก่อนถึงจะเห็นที่เหลือ)"
CHAT_HELP = """วิธีใช้
(ส่วนใหญ่กดปุ่มด้านล่างได้เลย: เช็คลิสต์ / นัด / ประจำสัปดาห์ / ของ / อื่น ๆ)

# พิมพ์แทนการกดก็ได้
- พรุ่งนี้ ร่ม / 24/10 ร่ม = เพิ่มของเฉพาะวัน (พกทั้งวัน)
- พรุ่งนี้ 5โมงเย็น ซ้อมบอล = เพิ่มนัด
- ลืม ร่ม / เพิ่ม ร่ม ทุกวัน = เพิ่มของพกทุกวัน
- ลบ ร่ม = ลบของพกทุกวัน
- นัด = ดูนัด · ลบนัด 25/10 = ลบนัดวันนั้น
- ปุ่ม ประจำสัปดาห์ = กิจกรรมทุกสัปดาห์ (เช่น เรียน ML ทุกจันทร์) · สัปดาห์ไหนไม่มี กด งดบางสัปดาห์
- วันนี้ไม่ต้องเตือน / พรุ่งนี้ไม่ต้องเตือน / เปิดเตือน
- ยังอยู่ห้อง / ออกแล้ว = แก้เมื่อระบบเดาผิด
- /list พรุ่งนี้ = ดูเช็คลิสต์ · /status = สถานะระบบ
- เมนู (หรือ /menu) = เรียกปุ่มด้านล่างกลับมา ถ้าปุ่มหาย"""


def send(text, buttons=None, silent=False):
    return {"send": text, "buttons": buttons, "silent": silent}


def edit(message_id, text, buttons=None):
    return {"edit": message_id, "text": text, "buttons": buttons}


def back(page):
    return [("กลับ", "m:" + page)]


def grid(pairs, per_row):
    # list ของ (ข้อความ, data) -> แถวละ per_row ปุ่ม
    rows = []
    for i in range(0, len(pairs), per_row):
        rows.append(pairs[i:i + per_row])
    return rows


def weekly_label(entry):
    # "ทุกจันทร์ 09:00 เรียน ML"
    return "ทุก" + WEEK_TH[WEEK.index(entry["day"])] + " " + entry["time"] + " " + entry["name"]


def short_day(key, today):
    # "2026-10-24" -> "พรุ่งนี้ ส.24/10" / "ส.24/10"
    date = thai_dt.key_to_date(key)
    text = THAI_DAYS[date.weekday()] + str(date.day) + "/" + str(date.month)
    if date == today:
        return "วันนี้ " + text
    if date == today + datetime.timedelta(days=1):
        return "พรุ่งนี้ " + text
    return text


def day_buttons(today, prefix, count=7):
    # ปุ่มเลือกวัน count วันนับจากวันนี้ แถวละ 4 ปุ่ม
    pairs = []
    for i in range(count):
        key = thai_dt.date_key(today + datetime.timedelta(days=i))
        pairs.append((short_day(key, today), prefix + key))
    return grid(pairs, 4)


def hour_buttons(first_hour):
    # ปุ่มชั่วโมง first_hour-22 (ไม่ต่ำกว่า 06) แถวละ 6 ปุ่ม
    pairs = []
    for hour in range(max(first_hour, 6), 23):
        label = "{:02d}".format(hour)
        pairs.append((label, "ah:" + label))
    return grid(pairs, 6)


def name_buttons(names, prefix):
    # ปุ่มชื่อของ แถวละ 2 ปุ่ม (ไม่เกิน MAX_LIST) · data = prefix + เลขลำดับ + จำนวนทั้งหมด
    # (ใส่จำนวนไว้เช็กว่ารายการเปลี่ยนไปหรือยัง กันกดปุ่มเก่าแล้วลบผิดชิ้น)
    pairs = []
    for i in range(min(len(names), MAX_LIST)):
        pairs.append((names[i][:25], prefix + str(i) + ":" + str(len(names))))
    return grid(pairs, 2)


def more_note(count):
    # ข้อความต่อท้ายเมื่อรายการยาวเกิน MAX_LIST
    return "\n" + MORE.format(MAX_LIST) if count > MAX_LIST else ""


def appt_ref(key, index, appt):
    # <วัน>:<ลำดับ>:<HHMM> ไว้ใส่ใน data ของปุ่ม
    return key + ":" + str(index) + ":" + appt["time"].replace(":", "")


def parse_ref(parts, start):
    # parts[start:start+3] -> (วัน, ลำดับ, "HH:MM")
    hhmm = parts[start + 2]
    return parts[start], int(parts[start + 1]), hhmm[:2] + ":" + hhmm[2:]


def valid_time(text):
    # "HH:MM" ที่ใช้ได้จริง (ชั่วโมง 0-23 นาที 0-59)
    return text is not None and int(text[:2]) < 24 and int(text[3:5]) < 60


def is_past(key, time_text, now):
    # วัน key เวลา time_text ผ่านไปแล้วหรือยัง (เทียบกับ now)
    tup = now[1]
    today = "{:04d}-{:02d}-{:02d}".format(tup[0], tup[1], tup[2])
    if key != today:
        return key < today
    return time_text <= "{:02d}:{:02d}".format(tup[3], tup[4])


def split_items(text):
    # "ร่ม, ผ้าเช็ดตัว" -> ["ร่ม", "ผ้าเช็ดตัว"] (คั่นด้วย , หรือขึ้นบรรทัดใหม่)
    names = []
    for part in text.replace("\n", ",").split(","):
        part = part.strip()[:40]
        if part != "" and part not in names:
            names.append(part)
    return names


def load_suggestions():
    # suggestions.json: คำในชื่อนัด -> ของที่น่าจะต้องเอาไป (ไม่มีไฟล์ = ไม่เดา)
    try:
        return storage.load_json("suggestions.json")
    except (OSError, ValueError):
        return {}


class ChatBot:

    def __init__(self, app):
        self.app = app            # App ใน main.py (ใช้ข้อมูล + เมธอดแก้ข้อมูล)
        self.wizard = None        # กำลังถามอะไรอยู่ (None = ไม่ได้ถาม) ดู start_wizard

    def __str__(self):
        if self.wizard is None:
            return "ChatBot(ว่าง)"
        return "ChatBot(กำลังถาม " + self.wizard["kind"] + "/" + self.wizard["step"] + ")"

    def today(self, now):
        return datetime.date(now[1][0], now[1][1], now[1][2])

    def activity_names(self):
        return [name for name in self.app.activities if not name.startswith("_")]

    def recent_activities(self):
        # กิจกรรมที่ใช้ล่าสุดก่อน (ท้ายไฟล์ = ล่าสุด ดู App.remember_activity) ไม่เกิน MAX
        names = self.activity_names()
        names.reverse()
        return names[:MAX_ACTIVITY_BUTTONS]

    def suggest(self, name):
        # ของที่น่าจะต้องเอาไปสำหรับนัดชื่อ name: จากกิจกรรมที่ชื่อตรงกัน + คำใน suggestions.json
        result = []
        if name in self.activity_names():
            result += self.app.activities[name]
        suggestions = load_suggestions()
        for word in suggestions:
            if not word.startswith("_") and word in name:
                result += suggestions[word]
        unique = []
        for item in result:
            if item not in unique:
                unique.append(item)
        return unique

    # ---------- หน้าเมนู ----------

    def page(self, name, now):
        # คืน (ข้อความ, ปุ่ม) ของหน้าเมนู
        app = self.app
        today = self.today(now)

        # ----- เช็คลิสต์ -----
        if name == "list":
            tomorrow = today + datetime.timedelta(days=1)
            return "เช็คลิสต์ของวันไหน", [
                [("วันนี้", "l:" + thai_dt.date_key(today)),
                 ("พรุ่งนี้", "l:" + thai_dt.date_key(tomorrow))],
                [("เลือกวัน", "m:lday")]]
        if name == "lday":
            return "ดูเช็คลิสต์วันไหน", day_buttons(today, "l:") + [back("list")]

        # ----- นัด -----
        if name == "appt":
            return ("นัด (ครั้งเดียว เช่น หาหมอ เตะบอล เดต)\n"
                    "(ของที่ทำทุกสัปดาห์ อยู่ที่ปุ่ม ประจำสัปดาห์)",
                    [[("ดูนัด", "m:appts"), ("เพิ่มนัด", "a:new"), ("ลบนัด", "m:appdel")],
                     [("นัดที่บันทึกไว้", "m:names")]])
        if name == "names":
            # นัดที่บันทึกไว้ = ชื่อนัด + ของที่ระบบจำเองตอนบันทึกนัด (ขึ้นเป็นปุ่มให้กดตอนเพิ่มนัด)
            # ลบได้ · นัดที่ลงวันไว้แล้วไม่หาย
            names = self.activity_names()
            if len(names) == 0:
                return ("ยังไม่มีนัดที่บันทึกไว้\n(เพิ่มนัดแล้วระบบจะจำชื่อกับของไว้"
                        " ครั้งหน้ากดเลือกได้เลย)", [back("appt")])
            lines = ["- " + n + (": " + ", ".join(self.app.activities[n])
                                 if self.app.activities[n] else "") for n in names]
            return ("นัดที่บันทึกไว้ (ขึ้นเป็นปุ่มให้กดตอนเพิ่มนัด พร้อมของ)\n" + "\n".join(lines)
                    + "\n\nกดชื่อที่จะลบออก (นัดที่ลงวันไว้แล้วไม่หาย)" + more_note(len(names)),
                    name_buttons(names, "x:t:") + [back("appt")])
        if name == "acts":
            # ประจำสัปดาห์ = ซ้ำทุกสัปดาห์ (ระบบนับเป็นนัดของวันนั้นเอง) · หน้าตาเหมือนเมนูนัด
            return ("ประจำสัปดาห์ (ทำทุกสัปดาห์ เช่น เรียน ML ทุกจันทร์)\n"
                    "(นัดครั้งเดียว อยู่ที่ปุ่ม นัด)",
                    [[("ดูกิจกรรม", "m:wkview"), ("เพิ่มกิจกรรม", "wk:new"),
                      ("ลบกิจกรรม", "m:wkdel")],
                     [("งดบางสัปดาห์", "m:wkskip")]])
        if name == "wkview":
            rows = app.weekly_rows()
            if len(rows) == 0:
                return ("ยังไม่มีกิจกรรมประจำสัปดาห์\n(เช่น เรียน ML ทุกจันทร์"
                        " เพิ่มครั้งเดียว ระบบเตือนให้เองทุกสัปดาห์)",
                        [[("เพิ่มกิจกรรม", "wk:new")], back("acts")])
            lines = []
            for d in range(7):                  # ทีละวัน จันทร์-อาทิตย์ (วันว่าง = -)
                todo = [e for i, e in rows if e["day"] == WEEK[d]]
                if not todo:
                    lines.append(WEEK_TH[d] + ": -")
                    continue
                lines.append(WEEK_TH[d] + ":")
                for entry in todo:
                    line = "- " + entry["time"] + "  " + entry["name"]
                    if entry.get("items"):
                        line += " (พก " + ", ".join(entry["items"]) + ")"
                    lines.append(line)
            skipped = self.upcoming_skips(today)
            if skipped:
                lines.append("\nงดไว้: " + ", ".join(skipped))
            return ("📅 ประจำสัปดาห์\n" + "\n".join(lines),
                    [[("เพิ่มกิจกรรม", "wk:new"), ("ลบกิจกรรม", "m:wkdel")],
                     [("งดบางสัปดาห์", "m:wkskip")], back("acts")])
        if name == "wkdel":
            rows = app.weekly_rows()
            if len(rows) == 0:
                return "ไม่มีกิจกรรมประจำให้ลบ", [back("acts")]
            buttons = []
            for index, entry in rows[:MAX_LIST]:
                label = ("ทุก" + WEEK_TH[WEEK.index(entry["day"])] + " " + entry["time"] + " "
                         + entry["name"])
                buttons.append([(label[:40], "x:w:" + str(index) + ":" + str(len(rows)))])
            return "กดกิจกรรมประจำที่จะลบ (ลบทุกสัปดาห์)", buttons + [back("acts")]
        if name == "wkskip":
            # ครั้งที่จะถึงใน 14 วัน กดเพื่องด (สัปดาห์นั้นไม่มีเรียน) กดซ้ำ = ยกเลิกงด
            rows = self.weekly_dates(today)
            if len(rows) == 0:
                return "ไม่มีกิจกรรมประจำใน 2 สัปดาห์นี้", [back("acts")]
            count = len(app.rules["weekly"])
            buttons = []
            for key, index, entry, skipped in rows[:MAX_LIST]:
                label = short_day(key, today) + " " + entry["time"] + " " + entry["name"]
                if skipped:
                    label += " (งดแล้ว)"
                buttons.append([(label[:40], "ws:" + key + ":" + str(index) + ":" + str(count))])
            return ("ครั้งไหนไม่มี กดเพื่องดเฉพาะครั้งนั้น\n(กดซ้ำ = ยกเลิกงด"
                    " · นัดอื่นวันนั้นยังเตือนปกติ)", buttons + [back("acts")])
        if name == "appts":
            rows = app.appointment_rows()
            lines = []
            for key, index, appt in rows:
                line = "- " + short_day(key, today) + "  " + appt["time"] + "  " + appt["name"]
                if is_past(key, appt["time"], now):
                    line += "  (ผ่านแล้ว)"
                lines.append(line)
                if appt.get("items"):
                    lines.append("   ต้องพก: " + ", ".join(appt["items"]))
            text = "📅 นัดทั้งหมด\n" + "\n".join(lines) if rows else "📅 ยังไม่มีนัด"
            return text, [[("เพิ่มนัด", "a:new"), ("ลบนัด", "m:appdel")], back("appt")]
        if name == "appdel":
            rows = app.appointment_rows()
            if len(rows) == 0:
                return "ไม่มีนัดให้ลบ", [back("appt")]
            buttons = []
            for key, index, appt in rows[:MAX_LIST]:
                label = short_day(key, today) + " " + appt["time"] + " " + appt["name"]
                buttons.append([(label[:40], "x:a:" + appt_ref(key, index, appt))])
            buttons.append(back("appt"))
            return "กดนัดที่จะลบ" + more_note(len(rows)), buttons

        # ----- ของ -----
        if name == "items":
            return "ของ", [[("ดูของ", "m:iview"), ("เพิ่มของ", "m:iadd"),
                           ("ลบของ", "m:idel")]]
        if name == "iview":
            app.reload_rules()
            text = "🎒 ของที่ต้องพก\n\n# พกทุกวัน\n"
            text += "\n".join("- " + n for n in app.rules["always"]) or "(ไม่มี)"
            text += "\n\n# เฉพาะวัน (พกทั้งวัน)\n"
            text += "\n".join("- " + short_day(k, today) + ": " + ", ".join(v)
                              for k, v in sorted(app.rules["by_date"].items()) if v) or "(ไม่มี)"
            text += "\n\n# ของสำหรับนัด\n"
            text += "\n".join("- " + short_day(k, today) + " " + a["time"] + " " + a["name"]
                              + ": " + ", ".join(a["items"])
                              for k, i, a in app.appointment_rows() if a.get("items")) or "(ไม่มี)"
            text += "\n\n# ของสำหรับประจำสัปดาห์\n"
            text += "\n".join("- " + weekly_label(e) + ": " + ", ".join(e["items"])
                              for i, e in app.weekly_rows() if e.get("items")) or "(ไม่มี)"
            return text, [[("เพิ่มของ", "m:iadd"), ("ลบของ", "m:idel")], back("items")]
        if name == "iadd":
            return (KIND_HELP.format("เพิ่ม"),
                    [[("พกทุกวัน", "w:always"), ("เฉพาะวัน", "m:adday")],
                     [("ของสำหรับนัด", "m:apadd")], [("ของสำหรับประจำสัปดาห์", "m:wkadd")],
                     back("items")])
        if name == "adday":
            # วันที่เลือกได้: 7 วันข้างหน้า + วันที่มีนัด/ของอยู่แล้ว (ไกลกว่า 7 วันก็เลือกได้)
            return ("เฉพาะวัน (พกทั้งวัน): เพิ่มของให้วันไหน",
                    grid([(short_day(k, today), "w:date:" + k) for k in self.day_choices(today)], 4)
                    + [back("iadd")])
        if name == "apadd":
            rows = [(k, i, a) for k, i, a in app.appointment_rows() if not is_past(k, a["time"], now)]
            if len(rows) == 0:
                return "ยังไม่มีนัด เพิ่มนัดก่อน", [[("เพิ่มนัด", "a:new")], back("iadd")]
            buttons = [[((short_day(k, today) + " " + a["time"] + " " + a["name"])[:40],
                         "w:appt:" + appt_ref(k, i, a))] for k, i, a in rows[:MAX_LIST]]
            return "ของสำหรับนัด: เพิ่มของให้นัดไหน", buttons + [back("iadd")]
        if name == "wkadd":
            rows = app.weekly_rows()
            if len(rows) == 0:
                return ("ยังไม่มีกิจกรรมประจำสัปดาห์ เพิ่มก่อน",
                        [[("เพิ่มกิจกรรมประจำ", "wk:new")], back("iadd")])
            buttons = [[(weekly_label(e)[:40], "wi:" + str(i) + ":" + str(len(rows)))]
                       for i, e in rows[:MAX_LIST]]
            return "ของสำหรับประจำสัปดาห์: เพิ่มของให้อันไหน", buttons + [back("iadd")]
        if name == "idel":
            return (KIND_HELP.format("ลบ"),
                    [[("พกทุกวัน", "m:delalw"), ("เฉพาะวัน", "m:delday")],
                     [("ของสำหรับนัด", "m:apdel")], [("ของสำหรับประจำสัปดาห์", "m:wkidel")],
                     back("items")])
        if name == "apdel":
            rows = [(k, i, a) for k, i, a in app.appointment_rows() if a.get("items")]
            if len(rows) == 0:
                return "ไม่มีของสำหรับนัดให้ลบ", [back("idel")]
            buttons = [[((short_day(k, today) + " " + a["time"] + " " + a["name"])[:40],
                         "d:" + k)] for k, i, a in rows[:MAX_LIST]]
            return "ของสำหรับนัด: ลบของของนัดไหน", buttons + [back("idel")]
        if name == "wkidel":
            rows = [(i, e) for i, e in app.weekly_rows() if e.get("items")]
            if len(rows) == 0:
                return "ไม่มีของสำหรับประจำสัปดาห์ให้ลบ", [back("idel")]
            count = len(app.rules["weekly"])
            buttons = [[(weekly_label(e)[:40], "wx:" + str(i) + ":" + str(count))]
                       for i, e in rows[:MAX_LIST]]
            return "ของสำหรับประจำสัปดาห์: ลบของของอันไหน", buttons + [back("idel")]
        if name == "delalw":
            app.reload_rules()
            names = list(app.rules["always"])
            if len(names) == 0:
                return "ไม่มีของที่พกทุกวันให้ลบ", [back("idel")]
            return ("พกทุกวัน: กดชิ้นที่จะลบ" + more_note(len(names)),
                    name_buttons(names, "x:i:") + [back("idel")])
        if name == "delday":
            keys = self.item_days()
            if len(keys) == 0:
                return "ไม่มีของเฉพาะวันให้ลบ", [back("idel")]
            pairs = []
            for key in keys[:MAX_LIST]:
                count = self.day_item_count(key)
                pairs.append((short_day(key, today) + " (" + str(count) + " ชิ้น)", "d:" + key))
            return ("เฉพาะวัน: ลบของของวันไหน" + more_note(len(keys)),
                    grid(pairs, 2) + [back("idel")])

        # ----- อื่น ๆ -----
        if name == "other":
            if app.guard.no_alert:
                first = [("เปิดเตือนกลับ", "o:alerton")]
            else:
                first = [("วันนี้ไม่ต้องเตือน", "o:noalert")]
            demo = ("โหมดเดโม: เปิด" if app.demo else "โหมดเดโม: ปิด")
            return "อื่น ๆ", [first, [("สถานะ", "o:status"), ("วิธีใช้", "o:help")],
                              [(demo, "o:demo")], [("เคลียร์ข้อมูล", "m:clear")]]
        if name == "clear":
            # ปุ่มลบทีเดียวหมด อยู่ที่นี่ที่เดียว (ไม่อยู่ในเมนูนัด/ของ กันกดพลาด) · กดแล้วถามยืนยันอีกครั้ง
            return ("เคลียร์ข้อมูลออกทั้งหมด\n(กดแล้วจะถามยืนยันอีกครั้ง)",
                    [[(CLEAR[k][0], "x:" + k)] for k in CLEAR_ORDER] + [back("other")])
        return EXPIRED, None

    # ---------- กิจกรรมประจำ ----------

    def weekly_dates(self, today, days=14):
        # ครั้งที่จะถึงใน days วัน: list ของ (วัน, ลำดับในไฟล์, entry, งดแล้วไหม) เรียงตามวัน+เวลา
        rows = self.app.weekly_rows()
        skips = self.app.rules["weekly_skip"]
        result = []
        for i in range(days):
            date = today + datetime.timedelta(days=i)
            key = thai_dt.date_key(date)
            for index, entry in rows:
                if entry["day"] == WEEK[date.weekday()]:
                    skipped = (entry["time"] + " " + entry["name"]) in skips.get(key, [])
                    result.append((key, index, entry, skipped))
        return result

    def weekly_items_page(self, index):
        # ของของกิจกรรมประจำอันที่ index: กดชิ้นที่จะลบ
        app = self.app
        app.reload_rules()
        weekly = app.rules["weekly"]
        if index >= len(weekly):
            return EXPIRED, None
        entry = weekly[index]
        items = entry.get("items", [])
        if not items:
            return weekly_label(entry) + "\n(ไม่มีของแล้ว)", [back("wkidel")]
        pairs = [(items[j][:25], "x:wi:" + str(index) + ":" + str(j) + ":" + str(len(items)))
                 for j in range(len(items))]
        return (weekly_label(entry) + " (กดชิ้นที่จะลบ)\n" + ", ".join(items),
                grid(pairs, 2) + [back("wkidel")])

    def upcoming_skips(self, today):
        # ข้อความครั้งที่งดไว้ เช่น ["จ.2/11 เรียน ML"]
        return [short_day(key, today) + " " + entry["name"]
                for key, index, entry, skipped in self.weekly_dates(today) if skipped]

    # ---------- ของเฉพาะวัน (ทั้งวัน + ของของนัด รวมในหน้าเดียว) ----------

    def day_appts(self, key):
        # นัดของวัน key เรียงตามเวลา: list ของ (ลำดับในไฟล์, appt)
        return [(index, appt) for k, index, appt in self.app.appointment_rows() if k == key]

    def day_item_count(self, key):
        count = len(self.app.rules["by_date"].get(key, []))
        for index, appt in self.day_appts(key):
            count += len(appt.get("items", []))
        return count

    def item_days(self):
        # วันที่มีของเฉพาะวันอยู่ (ทั้งวัน หรือของของนัด) เรียงตามวัน
        self.app.reload_rules()
        keys = set(self.app.rules["by_date"].keys())
        for key, index, appt in self.app.appointment_rows():
            if appt.get("items"):
                keys.add(key)
        return sorted(keys)

    def day_choices(self, today):
        # วันให้เลือกตอนเพิ่มของ: 7 วันข้างหน้า + วันที่มีนัด/ของอยู่แล้ว (ไม่เกิน 16 วัน)
        self.app.reload_rules()
        keys = set(thai_dt.date_key(today + datetime.timedelta(days=i)) for i in range(7))
        keys |= set(self.app.rules["appointments"].keys())
        keys |= set(self.app.rules["by_date"].keys())
        return sorted(k for k in keys if k >= thai_dt.date_key(today))[:16]

    def day_item_lines(self, key, now):
        # บรรทัดของวัน key แยกกลุ่ม: "ทั้งวัน: ร่ม" / "17:00 ซ้อมบอล: ชุดบอล, รองเท้า"
        lines = []
        names = self.app.rules["by_date"].get(key, [])
        if names:
            lines.append("ทั้งวัน: " + ", ".join(names))
        for index, appt in self.day_appts(key):
            if appt.get("items"):
                line = appt["time"] + " " + appt["name"] + ": " + ", ".join(appt["items"])
                if is_past(key, appt["time"], now):
                    line += "  (ผ่านแล้ว)"
                lines.append(line)
        return lines

    def date_delete_page(self, key, now):
        # หน้าของวัน key: เห็นของทุกชิ้นของวันนั้น (ทั้งวัน + ของของนัด) กดชิ้นที่จะลบ / เพิ่ม
        self.app.reload_rules()
        day = short_day(key, self.today(now))
        lines = self.day_item_lines(key, now)
        bottom = [[("เพิ่มของ", "sa:" + key)], back("delday")]
        if not lines:
            return "ของวัน " + day + "\n(ยังไม่มีของ)", bottom
        pairs = []
        names = self.app.rules["by_date"].get(key, [])
        for i in range(len(names)):
            pairs.append((names[i][:25], "x:d:" + key + ":" + str(i) + ":" + str(len(names))))
        for index, appt in self.day_appts(key):
            items = appt.get("items", [])
            for i in range(len(items)):
                label = items[i][:18] + " (" + appt["name"][:10] + ")"
                pairs.append((label, "x:p:" + appt_ref(key, index, appt) + ":" + str(i)
                              + ":" + str(len(items))))
        return ("ของวัน " + day + " (กดชิ้นที่จะลบ)\n" + "\n".join("- " + l for l in lines)
                + more_note(len(pairs)),
                grid(pairs[:MAX_LIST], 2) + bottom)

    def add_target_page(self, key, now):
        # เพิ่มของเฉพาะวัน: วันนั้นมีนัด -> ถามว่าให้ทั้งวัน หรือนัดไหน · ไม่มีนัด -> ถามชื่อของเลย
        upcoming = [(i, a) for i, a in self.day_appts(key) if not is_past(key, a["time"], now)]
        if not upcoming:
            self.start_wizard("date", now, key)
            return self.ask(now)
        buttons = [[("ทั้งวัน", "w:date:" + key)]]
        for index, appt in upcoming[:MAX_LIST]:
            buttons.append([(appt["time"] + " " + appt["name"][:25],
                             "w:appt:" + appt_ref(key, index, appt))])
        return ("วัน " + short_day(key, self.today(now)) + " มีนัด ใส่ของให้อะไร",
                buttons + [back("adday")])

    # ---------- รับข้อความที่พิมพ์ / ปุ่มล่าง ----------

    def on_text(self, text, now):
        text = text.strip()
        if text.lower() in MENU_WORDS:              # ปุ่มล่างหาย -> ส่งข้อความธรรมดา (แนบปุ่มล่างมาด้วย)
            self.wizard = None
            return [send(MENU_BACK)]
        if text in MAIN_PAGES:                      # กดปุ่มล่าง = เปิดเมนูใหม่
            self.wizard = None
            page_text, buttons = self.page(MAIN_PAGES[text], now)
            return [send(page_text, buttons)]
        if self.wizard is not None:
            expired = now[0] - self.wizard["since"] > WIZARD_TIMEOUT
            if not expired and not text.startswith("/"):
                return self.wizard_text(text, now)
            self.wizard = None                      # หมดเวลา / พิมพ์คำสั่งอื่น = ยกเลิกที่ถาม
        reply, actions = self.app.run_command(text, now)
        self.app.handle(actions, now)
        return [send(reply)]

    # ---------- ถามทีละขั้น ----------

    def start_wizard(self, kind, now, key=None):
        # kind = "appt"       เพิ่มนัด: date -> time -> name -> items
        #        "always" / "date"   เพิ่มของ: พิมพ์ชื่อ (date ใช้ key = วัน)
        #        "apptitems"  เพิ่มของสำหรับนัดที่บันทึกแล้ว: items (key = (วัน, ลำดับ, เวลา))
        #        "weekly"     เพิ่มกิจกรรมประจำ: day -> time -> name -> items (date = "mon".."sun")
        #        "weekitems"  เพิ่มของให้กิจกรรมประจำ: items (key = ลำดับในไฟล์)
        step = {"appt": "date", "apptitems": "items", "weekly": "day",
                "weekitems": "items"}.get(kind, "name")
        self.wizard = {"kind": kind, "step": step, "since": now[0], "key": key,
                       "date": None, "time": None, "name": None,
                       "shown": [],              # กิจกรรมที่แสดงเป็นปุ่มขั้นเลือกชื่อ (an:<เลข>)
                       "options": [], "chosen": [],
                       "limit": MAX_ITEMS,       # เลือกได้อีกกี่ชิ้น
                       "note": ""}               # ข้อความเตือนสั้น ๆ แสดงครั้งเดียว (เช่น เต็มแล้ว)

    def start_weekly_items(self, index, now):
        # เริ่มเพิ่มของให้กิจกรรมประจำ: เสนอของที่เดาได้ (ที่ยังไม่มี) + พิมพ์เพิ่มได้
        weekly = self.app.rules["weekly"]
        if index >= len(weekly):
            return False
        entry = weekly[index]
        self.start_wizard("weekitems", now, index)
        w = self.wizard
        w["name"] = weekly_label(entry)
        have = entry.get("items", [])
        w["options"] = [i for i in self.suggest(entry["name"]) if i not in have][:MAX_ITEMS]
        w["limit"] = MAX_ITEMS - len(have)
        w["have"] = list(have)
        return True

    def start_appt_items(self, key, index, time_text, now):
        # เริ่มเพิ่มของให้นัดที่บันทึกแล้ว: เสนอของที่เดาได้ (ที่ยังไม่มี) + พิมพ์เพิ่มได้
        appt = self.app.find_appt(key, index, time_text)
        if appt is None:
            return False
        self.start_wizard("apptitems", now, (key, index, time_text))
        w = self.wizard
        w["date"], w["time"], w["name"] = key, time_text, appt["name"]
        have = appt.get("items", [])
        w["options"] = [i for i in self.suggest(appt["name"]) if i not in have][:MAX_ITEMS]
        w["limit"] = MAX_ITEMS - len(have)
        w["have"] = list(have)
        return True

    def items_ask(self, head):
        # หน้าเลือกของ (ใช้ทั้งขั้น 4/4 ของเพิ่มนัด และเพิ่มของสำหรับนัด)
        w = self.wizard
        pairs = []
        for i in range(len(w["options"])):
            item = w["options"][i]
            label = ("✓ " + item) if item in w["chosen"] else item
            pairs.append((label[:25], "ai:" + str(i)))
        if w["chosen"]:
            chosen = "เลือกแล้ว " + str(len(w["chosen"])) + " ชิ้น: " + ", ".join(w["chosen"])
        else:
            chosen = "ยังไม่ได้เลือก"
        text = (head + "\nต้องเอาอะไรไปบ้าง"
                + "\n(กดเพื่อเลือก/เอาออก หรือพิมพ์ชื่อของ หลายชิ้นคั่นด้วย , · ไม่เกิน "
                + str(MAX_ITEMS) + " ชิ้น)")
        if w.get("have"):
            text += "\n\nมีอยู่แล้ว: " + ", ".join(w["have"])
        text += "\n\n" + chosen
        if w["note"]:
            text += "\n\n" + w["note"]
            w["note"] = ""
        return text, grid(pairs, 2) + [[("บันทึก", "ai:done")], CANCEL]

    def ask(self, now):
        # คำถามของขั้นปัจจุบัน -> (ข้อความ, ปุ่ม)
        w = self.wizard
        today = self.today(now)
        if w["kind"] == "appt":
            if w["step"] == "date":
                return ("เพิ่มนัด (1/4)\nนัดวันไหน\n(หรือพิมพ์ เช่น 5/11, วันศุกร์)",
                        day_buttons(today, "ad:") + [CANCEL])
            head = "เพิ่มนัด ({}/4) " + short_day(w["date"], today)
            if w["step"] == "time":
                first_hour = 6
                if w["date"] == thai_dt.date_key(today):
                    first_hour = now[1][3] + 1          # วันนี้: ไม่แสดงชั่วโมงที่ผ่านไปแล้ว
                buttons = hour_buttons(first_hour)
                note = "(หรือพิมพ์ เช่น 8.30, บ่าย2ครึ่ง)"
                if len(buttons) == 0:
                    note = "(วันนี้เลยช่วงในปุ่มแล้ว พิมพ์เวลาเอง เช่น 23.30)"
                return head.format(2) + "\nกี่โมง\n" + note, buttons + [CANCEL]
            if w["step"] == "name":
                pairs = []
                w["shown"] = self.recent_activities()
                for i in range(len(w["shown"])):
                    pairs.append((w["shown"][i], "an:" + str(i)))
                return (head.format(3) + " " + w["time"]
                        + "\nนัดอะไร (กดเลือก หรือพิมพ์ชื่อนัดเอง เช่น หาหมอ)",
                        grid(pairs, 2) + [CANCEL])
            # step items
            return self.items_ask(head.format(4) + " " + w["time"] + " " + w["name"])
        if w["kind"] == "weekly":
            if w["step"] == "day":
                pairs = [(WEEK_TH[i], "wd:" + WEEK[i]) for i in range(7)]
                return ("เพิ่มกิจกรรมประจำ (1/4)\nทำทุกวันอะไร\n(หรือพิมพ์ เช่น จันทร์)",
                        grid(pairs, 4) + [CANCEL])
            head = "เพิ่มกิจกรรมประจำ ({}/4) ทุก" + WEEK_TH[WEEK.index(w["date"])]
            if w["step"] == "time":
                return (head.format(2) + "\nกี่โมง\n(หรือพิมพ์ เช่น 8.30, บ่าย1)",
                        hour_buttons(6) + [CANCEL])
            if w["step"] == "name":             # ไม่ใช้ชื่อนัด (แยกนัด กับ ประจำสัปดาห์ ให้ชัด)
                return (head.format(3) + " " + w["time"]
                        + "\nกิจกรรมอะไร (พิมพ์ชื่อ เช่น เรียน ML)", [CANCEL])
            return self.items_ask(head.format(4) + " " + w["time"] + " " + w["name"])
        if w["kind"] == "weekitems":
            return self.items_ask("เพิ่มของให้ " + w["name"])
        if w["kind"] == "apptitems":
            return self.items_ask("เพิ่มของให้นัด " + short_day(w["date"], today)
                                  + " " + w["time"] + " " + w["name"])
        if w["kind"] == "always":
            return "พกทุกวัน: พิมพ์ชื่อของที่จะเพิ่ม (หลายชิ้นคั่นด้วย ,)", [CANCEL]
        return ("วัน " + short_day(w["key"], today) + " (พกทั้งวัน)"
                + ": พิมพ์ชื่อของที่จะเพิ่ม (หลายชิ้นคั่นด้วย ,)", [CANCEL])

    def to_items_step(self, name):
        # ได้ชื่อนัดแล้ว -> ขั้นเลือกของ (กิจกรรมเดิมเลือกของไว้ให้ก่อน / นัดใหม่ให้เลือกจากที่เดา)
        w = self.wizard
        w["name"] = name
        w["options"] = self.suggest(name)[:MAX_ITEMS]
        w["chosen"] = []
        if name in self.activity_names():
            w["chosen"] = list(self.app.activities[name])[:MAX_ITEMS]
        w["step"] = "items"

    def choose(self, item):
        # เลือกของ 1 ชิ้นในขั้นเลือกของ · เต็มแล้ว = ไม่เพิ่ม + ตั้งข้อความเตือน · คืน True ถ้าเพิ่มได้
        w = self.wizard
        if item in w["chosen"] or item in w.get("have", []):
            return True
        if len(w["chosen"]) >= w["limit"]:
            w["note"] = "ครบ " + str(MAX_ITEMS) + " ชิ้นแล้ว เอาชิ้นอื่นออกก่อนถึงจะเพิ่มได้"
            return False
        if item not in w["options"]:
            w["options"].append(item)
        w["chosen"].append(item)
        return True

    def wizard_text(self, text, now):
        # ผู้ใช้พิมพ์ตอบคำถาม
        w = self.wizard
        today = self.today(now)
        if w["kind"] in ["always", "date"]:     # เพิ่มของ: พิมพ์ชื่อแล้วจบเลย
            names = split_items(text)
            if len(names) == 0:
                return [send("พิมพ์ชื่อของด้วย", [CANCEL])]
            if len(names) > MAX_ITEMS:
                return [send("เพิ่มได้ครั้งละไม่เกิน " + str(MAX_ITEMS) + " ชิ้น ลองใหม่",
                             [CANCEL])]
            return [self.finish_items(names, None)]
        if w["step"] == "day":                  # กิจกรรมประจำ: พิมพ์ชื่อวัน
            found = [i for i in range(7) if WEEK_TH[i] in text]
            if len(found) == 0:
                return [send("ไม่เข้าใจวัน ลองใหม่ เช่น จันทร์ หรือกดปุ่ม", [CANCEL])]
            w["date"] = WEEK[found[0]]
            w["step"] = "time"
        elif w["step"] == "date":
            date, rest = thai_dt.find_date(text, today)
            if date is None or date < today:
                return [send("ไม่เข้าใจวันที่ ลองใหม่ เช่น 5/11 หรือ วันศุกร์", [CANCEL])]
            w["date"] = thai_dt.date_key(date)
            w["step"] = "time"
        elif w["step"] == "time":
            time_text, rest = thai_dt.find_time(text)
            if not valid_time(time_text):
                return [send("ไม่เข้าใจเวลา ลองใหม่ เช่น 17:00, 8.30, บ่าย2", [CANCEL])]
            if w["kind"] == "appt" and is_past(w["date"], time_text, now):
                return [send("เวลานี้ผ่านไปแล้ว ลองเวลาอื่น", [CANCEL])]
            w["time"] = time_text
            w["step"] = "name"
        elif w["step"] == "name":
            name = text.strip()[:40]
            if name == "":
                return [send("พิมพ์ชื่อด้วย", [CANCEL])]
            self.to_items_step(name)
        else:                                   # step items: พิมพ์ของเพิ่ม (เต็มแล้วหยุด)
            for item in split_items(text):
                if not self.choose(item):
                    break
        ask_text, buttons = self.ask(now)
        return [send(ask_text, buttons)]

    def finish_appointment(self, message_id):
        # จบการเพิ่มนัด: บันทึก · กิจกรรมเดิม = ย้ายขึ้นเป็นล่าสุด · กิจกรรมใหม่ = มีปุ่มถามว่าจะจำไหม
        w = self.wizard
        self.wizard = None
        app = self.app
        reply = app.add_appointment(w["date"], w["time"], w["name"], list(w["chosen"]))
        # นัดที่เพิ่งเพิ่ม = อันสุดท้ายของวันนั้น
        index = len(app.rules["appointments"][w["date"]]) - 1
        ref = appt_ref(w["date"], index, {"time": w["time"]})
        buttons = [[("แก้ของ", "d:" + w["date"]), ("ยกเลิกนัดนี้", "x:a:" + ref)],
                   [("ดูนัด", "m:appts")]]
        # จำชื่อนัด + ของไว้เอง (ครั้งหน้ามีปุ่มชื่อนี้ให้กด พร้อมของ) ไม่ต้องให้ผู้ใช้กดจำ
        app.remember_activity(w["name"], w["chosen"])
        if message_id is None:
            return send(reply, buttons)
        return edit(message_id, reply, buttons)

    def finish_weekly(self, message_id):
        # จบการเพิ่มกิจกรรมประจำ
        w = self.wizard
        self.wizard = None
        reply = self.app.add_weekly(w["date"], w["time"], w["name"], list(w["chosen"]))
        buttons = [[("ดูกิจกรรม", "m:wkview"), ("เพิ่มอีก", "wk:new")]]
        if message_id is None:
            return send(reply, buttons)
        return edit(message_id, reply, buttons)

    def finish_weekly_items(self, message_id):
        w = self.wizard
        self.wizard = None
        if w["chosen"]:
            reply = self.app.add_weekly_items(w["key"], w["chosen"])
        else:
            reply = "ไม่ได้เลือกของเพิ่ม"
        buttons = [[("ดูของ", "m:iview"), ("เพิ่มอีก", "m:wkadd")]]
        if message_id is None:
            return send(reply, buttons)
        return edit(message_id, reply, buttons)

    def finish_appt_items(self, message_id):
        # จบการเพิ่มของสำหรับนัด
        w = self.wizard
        self.wizard = None
        key, index, time_text = w["key"]
        if w["chosen"]:
            reply = self.app.add_appt_items(key, index, time_text, w["chosen"])
        else:
            reply = "ไม่ได้เลือกของเพิ่ม"
        buttons = [[("ดูของวันนั้น", "d:" + key), ("เพิ่มอีก", "m:iadd")]]
        if message_id is None:
            return send(reply, buttons)
        return edit(message_id, reply, buttons)

    def finish_items(self, names, message_id):
        # จบการเพิ่มของ (ทุกวัน / เฉพาะวัน)
        w = self.wizard
        self.wizard = None
        if w["kind"] == "always":
            replies = [self.app.add_always(name) for name in names]
            buttons = [[("ดูของ", "m:iview"), ("เพิ่มอีก", "m:iadd")]]
        else:
            replies = [self.app.add_date_items(w["key"], names)]
            buttons = [[("ดูของวันนั้น", "d:" + w["key"]), ("เพิ่มอีก", "m:iadd")]]
        if message_id is None:
            return send("\n".join(replies), buttons)
        return edit(message_id, "\n".join(replies), buttons)

    # ---------- กดปุ่มติดข้อความ ----------

    def on_button(self, data, message_id, message_text, now):
        app = self.app
        parts = data.split(":")
        kind = parts[0]

        # กดปุ่มอื่นที่ไม่ใช่การตอบคำถาม = เลิกถาม
        if kind not in ["ad", "ah", "an", "ai", "wd"] and data != "w:cancel":
            self.wizard = None

        if kind == "m":
            page_text, buttons = self.page(parts[1], now)
            return [edit(message_id, page_text, buttons)]
        if kind == "l":
            return [edit(message_id, app.checklist_page(parts[1], self.today(now)),
                         [back("list")])]
        if kind == "d":
            page_text, buttons = self.date_delete_page(parts[1], now)
            return [edit(message_id, page_text, buttons)]
        if kind == "p":                         # p:<นัด> (ปุ่มเก่า) -> หน้าของวันของนัดนั้น
            page_text, buttons = self.date_delete_page(parts[1], now)
            return [edit(message_id, page_text, buttons)]
        if kind == "sa":                        # sa:<วัน> เพิ่มของเฉพาะวัน
            page_text, buttons = self.add_target_page(parts[1], now)
            return [edit(message_id, page_text, buttons)]

        # ----- ถามทีละขั้น -----
        if data == "a:new":
            self.start_wizard("appt", now)
        elif data == "wk:new":
            self.start_wizard("weekly", now)
        elif kind == "wi":                      # wi:<เลข>:<จำนวน> เพิ่มของให้กิจกรรมประจำ
            index, count = int(parts[1]), int(parts[2])
            if count != len(app.rules["weekly"]) or not self.start_weekly_items(index, now):
                return [edit(message_id, "รายการเปลี่ยนไปแล้ว ลองกดใหม่", [back("wkadd")])]
        elif data == "w:always":
            self.start_wizard("always", now)
        elif kind == "w" and parts[1] == "date":
            self.start_wizard("date", now, parts[2])
        elif kind == "w" and parts[1] == "appt":   # w:appt:<นัด>
            key, index, time_text = parse_ref(parts, 2)
            if not self.start_appt_items(key, index, time_text, now):
                return [edit(message_id, "ไม่เจอนัดนี้แล้ว (อาจถูกลบไปแล้ว)")]
        elif data == "w:cancel":
            self.wizard = None
            return [edit(message_id, "ยกเลิกแล้ว")]
        elif kind in ["ad", "ah", "an", "ai", "wd"]:
            out = self.wizard_button(kind, parts, message_id, now)
            if out is not None:
                return [out]
        if self.wizard is not None:
            ask_text, buttons = self.ask(now)
            return [edit(message_id, ask_text, buttons)]

        if kind == "wx":                        # wx:<เลข>:<จำนวน> หน้าลบของของกิจกรรมประจำ
            index, count = int(parts[1]), int(parts[2])
            if count != len(app.rules["weekly"]):
                return [edit(message_id, "รายการเปลี่ยนไปแล้ว ลองกดใหม่", [back("wkidel")])]
            page_text, buttons = self.weekly_items_page(index)
            return [edit(message_id, page_text, buttons)]

        # ----- งด/ยกเลิกงด กิจกรรมประจำเฉพาะวัน -----
        if kind == "ws":                        # ws:<วัน>:<เลข>:<จำนวน>
            index, count = int(parts[2]), int(parts[3])
            if count != len(app.rules["weekly"]) or index >= count:
                reply = "รายการเปลี่ยนไปแล้ว ลองกดใหม่"
            else:
                reply = app.toggle_weekly_skip(parts[1], index)
            page_text, buttons = self.page("wkskip", now)
            return [edit(message_id, reply + "\n\n" + page_text, buttons)]

        # ----- ลบ -----
        if kind == "x":
            return [self.delete(parts, message_id, now)]

        # ----- จำนัดเป็นกิจกรรม (ผู้ใช้กดเอง) -----
        if kind == "r":                         # r:<นัด>
            key, index, time_text = parse_ref(parts, 1)
            return [self.remember(key, index, time_text, message_id, message_text)]

        # ----- อื่น ๆ -----
        if data == "o:noalert":
            return [edit(message_id, app.no_alert_today(),
                         [[("เปิดเตือนกลับ", "o:alerton")], back("other")])]
        if data == "o:alerton":
            return [edit(message_id, app.alert_on_today(), [back("other")])]
        if data == "o:status":
            return [edit(message_id, app.status_text(), [back("other")])]
        if data == "o:demo":
            # เปิดเดโม = ถามยืนยันก่อน (เวลาทั้งชุดเปลี่ยน) · ปิดเดโม = ปิดเลย
            if app.demo:
                return [edit(message_id, app.toggle_demo(False, now), [back("other")])]
            return [edit(message_id,
                         "เปิดโหมดเดโมไหม\n- รอ 10 วิ ก็นับว่าออกจากห้อง\n"
                         "- เตือนทุกครั้งที่ออก (เว้น 1 นาที) เตือนได้ทุกเวลา\n"
                         "- ข้อมูลทดสอบบันทึกแยก ไม่ปนข้อมูลจริง\n"
                         "(ตี 3 จะกลับเป็นโหมดใช้งานจริงเอง)",
                         [[("เปิดโหมดเดโม", "o:demo!"), ("ไม่เปิด", "m:other")]])]
        if data == "o:demo!":
            return [edit(message_id, app.toggle_demo(True, now), [back("other")])]
        if data == "o:help":
            return [edit(message_id, CHAT_HELP, [back("other")])]
        if data == "o:home" or data == "o:out":
            # ปุ่มใต้ข้อความเตือน: แก้สถานะ แล้วเอาปุ่มออกจากข้อความเดิม (กันกดซ้ำ)
            if data == "o:home":
                app.handle(app.guard.still_home(now), now)
                note = "แก้แล้ว: ยังอยู่ห้อง"
            else:
                app.handle(app.guard.force_out(now), now)
                note = "แก้แล้ว: ออกไปแล้ว"
            return [edit(message_id, (message_text + "\n\n" + note).strip())]
        return [edit(message_id, EXPIRED)]

    def wizard_button(self, kind, parts, message_id, now):
        # ปุ่มตอบคำถามเพิ่มนัด · คืน out ถ้าจบ/ผิด, None = ไปถามขั้นถัดไป
        w = self.wizard
        need = {"ad": "date", "ah": "time", "an": "name", "ai": "items", "wd": "day"}[kind]
        # ปุ่มเลือกของ (ai) ใช้ทั้งเพิ่มนัด เพิ่มของสำหรับนัด และกิจกรรมประจำ
        kinds = {"ai": ["appt", "apptitems", "weekly", "weekitems"], "ad": ["appt"],
                 "wd": ["weekly"]}.get(kind, ["appt", "weekly"])
        if w is None or w["kind"] not in kinds or w["step"] != need:
            return edit(message_id, EXPIRED)
        if kind == "wd":
            if parts[1] not in WEEK:
                return edit(message_id, EXPIRED)
            w["date"] = parts[1]
            w["step"] = "time"
        elif kind == "ad":
            if parts[1] < thai_dt.date_key(self.today(now)):
                return edit(message_id, EXPIRED)        # ปุ่มวันเก่าจากเมื่อวาน
            w["date"] = parts[1]
            w["step"] = "time"
        elif kind == "ah":
            time_text = parts[1] + ":00"
            if w["kind"] == "appt" and is_past(w["date"], time_text, now):
                return edit(message_id, "เวลานี้ผ่านไปแล้ว กดเพิ่มนัดใหม่")
            w["time"] = time_text
            w["step"] = "name"
        elif kind == "an":
            index = int(parts[1])
            if index >= len(w["shown"]):
                return edit(message_id, EXPIRED)
            self.to_items_step(w["shown"][index])
        elif parts[1] == "done":
            if w["kind"] == "apptitems":
                return self.finish_appt_items(message_id)
            if w["kind"] == "weekly":
                return self.finish_weekly(message_id)
            if w["kind"] == "weekitems":
                return self.finish_weekly_items(message_id)
            return self.finish_appointment(message_id)
        else:                                           # ai:<เลข> เลือก/เอาออก
            index = int(parts[1])
            if index >= len(w["options"]):
                return edit(message_id, EXPIRED)
            item = w["options"][index]
            if item in w["chosen"]:
                w["chosen"].remove(item)
            else:
                self.choose(item)
        return None

    def remember(self, key, index, time_text, message_id, message_text):
        # ปุ่ม "เพิ่มเป็นกิจกรรมประจำ": เอาชื่อ+ของของนัดนั้นไปเก็บเป็นกิจกรรม
        app = self.app
        appt = app.find_appt(key, index, time_text)
        if appt is None or not appt.get("items"):
            return edit(message_id, "ไม่เจอนัดนี้แล้ว (อาจถูกลบไปแล้ว)")
        app.remember_activity(appt["name"], appt["items"])
        note = "เพิ่ม \"" + appt["name"] + "\" เป็นกิจกรรมประจำแล้ว ครั้งหน้ากดเลือกได้เลย"
        return edit(message_id, (message_text + "\n\n" + note).strip(),
                    [[("ดูนัด", "m:appts")]])

    def delete(self, parts, message_id, now):
        # ปุ่ม x:... -> ลบ แล้วแสดงหน้าลบเดิมที่อัปเดตแล้ว
        app = self.app
        what = parts[1]
        if what == "a":                         # x:a:<นัด> ลบนัดอันเดียว (เวลาซ้ำกันไม่ลบปน)
            key, index, time_text = parse_ref(parts, 2)
            reply = app.remove_appointment_at(key, index, time_text)
            page_text, buttons = self.page("appdel", now)
            return edit(message_id, reply + "\n\n" + page_text, buttons)
        if what == "p":                         # x:p:<นัด>:<เลข>:<จำนวน> ลบของสำหรับนัด
            key, index, time_text = parse_ref(parts, 2)
            appt = app.find_appt(key, index, time_text)
            names = appt.get("items", []) if appt else []
            item_index, count = int(parts[5]), int(parts[6])
            if count != len(names) or item_index >= len(names):
                reply = "รายการเปลี่ยนไปแล้ว ลองกดใหม่"
            else:
                reply = app.remove_appt_item(key, index, time_text, names[item_index])
            page_text, buttons = self.date_delete_page(key, now)
            return edit(message_id, reply + "\n\n" + page_text, buttons)

        # ----- เคลียร์ออกทั้งหมด (เมนู อื่น ๆ > เคลียร์ข้อมูล) -----
        if what in CLEAR:                       # ถามยืนยันก่อน (เคลียร์แล้วกู้ไม่ได้)
            return edit(message_id, CLEAR[what][1] + " จริงไหม\n(กู้คืนไม่ได้)",
                        [[("เคลียร์เลย", "x:" + what + "!"), ("ไม่เคลียร์", "m:clear")]])
        if what.endswith("!") and what[:-1] in CLEAR:
            todo = {"aall": app.clear_appointments, "call": app.clear_always,
                    "cdall": app.clear_date_items, "tall": app.clear_weekly}
            reply = todo[what[:-1]]()
            page_text, buttons = self.page("clear", now)
            return edit(message_id, reply + "\n\n" + page_text, buttons)

        if what == "i":                         # x:i:<เลข>:<จำนวน>
            app.reload_rules()
            names = app.rules["always"]
            index, count = int(parts[2]), int(parts[3])
            if count != len(names) or index >= len(names):
                reply = "รายการเปลี่ยนไปแล้ว ลองกดใหม่"
            else:
                reply = app.remove_always(names[index])
            page_text, buttons = self.page("delalw", now)
            return edit(message_id, reply + "\n\n" + page_text, buttons)
        if what == "d":                         # x:d:<วัน>:<เลข>:<จำนวน>
            key = parts[2]
            app.reload_rules()
            names = app.rules["by_date"].get(key, [])
            index, count = int(parts[3]), int(parts[4])
            if count != len(names) or index >= len(names):
                reply = "รายการเปลี่ยนไปแล้ว ลองกดใหม่"
            else:
                reply = app.remove_date_item(key, names[index])
            page_text, buttons = self.date_delete_page(key, now)
            return edit(message_id, reply + "\n\n" + page_text, buttons)
        if what == "wi":                        # x:wi:<เลข>:<ชิ้น>:<จำนวนชิ้น> ลบของของกิจกรรมประจำ
            index, j, count = int(parts[2]), int(parts[3]), int(parts[4])
            weekly = app.rules["weekly"]
            items = weekly[index].get("items", []) if index < len(weekly) else []
            if count != len(items) or j >= len(items):
                reply = "รายการเปลี่ยนไปแล้ว ลองกดใหม่"
            else:
                reply = app.remove_weekly_item(index, items[j])
            page_text, buttons = self.weekly_items_page(index)
            return edit(message_id, reply + "\n\n" + page_text, buttons)
        if what == "t":                         # x:t:<เลข>:<จำนวน> ลบนัดที่บันทึกไว้
            names = self.activity_names()
            index, count = int(parts[2]), int(parts[3])
            if count != len(names) or index >= len(names):
                reply = "รายการเปลี่ยนไปแล้ว ลองกดใหม่"
            else:
                reply = app.forget_activity(names[index])
            page_text, buttons = self.page("names", now)
            return edit(message_id, reply + "\n\n" + page_text, buttons)
        if what == "w":                         # x:w:<เลข>:<จำนวน> ลบกิจกรรมประจำ
            index, count = int(parts[2]), int(parts[3])
            if count != len(app.rules["weekly"]) or index >= count:
                reply = "รายการเปลี่ยนไปแล้ว ลองกดใหม่"
            else:
                reply = app.remove_weekly(index)
            page_text, buttons = self.page("wkdel", now)
            return edit(message_id, reply + "\n\n" + page_text, buttons)
        return edit(message_id, EXPIRED)
