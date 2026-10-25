# ลูปหลัก: รับเหตุการณ์ประตูจากคีย์บอร์ด + tick + พิมพ์ผลลงจอ + ส่ง/รับ Telegram
#          + บันทึก data/events.csv และ data/state.json
# รัน (ในโฟลเดอร์ door_buddy):  python -m pc.main          ใช้ค่าใน config.json
#                               python -m pc.main --demo   ลดเวลาไว้ทดสอบ/อัดคลิป
import datetime
import sys
import time
import traceback

from core.checklist import build_checklist
from core.commands import parse_command
from core.guard import DoorGuard
from core.weekly import appointments_on, skip_key
from pc import storage
from pc import telegram
from pc import thai_dt
from pc.bot import CHAT_HELP, MAX_ITEMS, ChatBot
from pc.door_link import PORT, DoorLink
from pc.door_sim import read_key
from pc.weather import WeatherWorker

HELP = ("กด o = เปิดประตู, c = ปิดประตู, l = ดูเช็คลิสต์, s = สถานะ, "
        "m = พิมพ์ข้อความแชท, b = กดปุ่ม (พิมพ์ data), w = จำลองฝน, q = ออก")
FAKE_RAIN = [None, 80, 0]     # ปุ่ม w วนค่า: ของจริง -> จำลองฝน 80% -> จำลองไม่มีฝน -> ของจริง
STATE = "data/state.json"
DEMO_DATA = "data/demo/"      # โหมดเดโมเขียนไฟล์แยกที่นี่ (ข้อมูลทดสอบไม่ปนข้อมูลจริง)
WEEKDAY_TH = {"mon": "จันทร์", "tue": "อังคาร", "wed": "พุธ", "thu": "พฤหัส",
              "fri": "ศุกร์", "sat": "เสาร์", "sun": "อาทิตย์"}
STATE_TH = {"HOME": "อยู่ห้อง", "DOOR_OPEN": "ประตูเปิดอยู่",
            "MAYBE_OUT": "เพิ่งปิดประตู กำลังรอดูว่าออกไปไหม",
            "OUT": "ออกไปข้างนอก", "ENTERING": "เพิ่งเปิดประตูเข้ามา"}


def get_now():
    # now = (epoch, (ปี, เดือน, วัน, ชม, นาที, วินาที, วันในสัปดาห์)) ตามที่ core ต้องการ
    t = time.localtime()
    return (time.time(), tuple(t[:7]))


def time_at(epoch):
    # now แบบเดียวกับ get_now แต่เป็นเวลาที่กำหนด (เช่น เวลาที่ประตูขยับจริงตามที่บอร์ดบอก)
    return (epoch, tuple(time.localtime(epoch)[:7]))


def clock(now):
    # เวลาแบบ HH:MM:SS ไว้พิมพ์นำหน้าข้อความ
    tup = now[1]
    return "{:02d}:{:02d}:{:02d}".format(tup[3], tup[4], tup[5])


def hm(now):
    # เวลาแบบ HH:MM ไว้ใส่ในข้อความที่ส่งให้คนอ่าน
    return "{:02d}:{:02d}".format(now[1][3], now[1][4])


def day_key(tup):
    # tuple วันที่ -> "YYYY-MM-DD"
    return "{:04d}-{:02d}-{:02d}".format(tup[0], tup[1], tup[2])


def plain(text):
    # ข้อความสำหรับพิมพ์บนจอคอม: เอาเครื่องหมายหัวข้อ "# " ออก (บน Telegram จะเป็นตัวหนา)
    return "\n".join(line[2:] if line.startswith("# ") else line for line in text.split("\n"))


def load_secrets():
    # อ่าน secrets.json · ไม่มีไฟล์หรือกรอกไม่ครบ = None (ใช้แค่จอ)
    try:
        secrets = storage.load_json("secrets.json")
    except (OSError, ValueError):
        return None
    if secrets.get("TELEGRAM_TOKEN") and secrets.get("TELEGRAM_CHAT_ID"):
        return secrets
    return None


def start_telegram(secrets):
    # เริ่ม thread ของ Telegram · ไม่มี secrets = None
    if secrets is None:
        return None
    return telegram.TelegramWorker(secrets["TELEGRAM_TOKEN"], secrets["TELEGRAM_CHAT_ID"])


def start_door_link():
    # เริ่ม thread รับสถานะประตูจากบอร์ด ESP32 · เปิดพอร์ตไม่ได้ = None (ยังกด o/c ได้)
    try:
        link = DoorLink()
    except OSError as e:
        print("เปิดพอร์ตรับสัญญาณบอร์ด", PORT, "ไม่ได้:", e, "-> ใช้คีย์บอร์ด o/c แทน")
        return None
    print("รอสัญญาณประตูจากบอร์ด ESP32 (WiFi พอร์ต " + str(PORT) + ") · กด o/c จำลองได้เหมือนเดิม")
    return link


def item_lines(items):
    # list ของ Item -> ["1. ร่ม  (ฝน 70%)", ...]
    return [str(i + 1) + ". " + items[i].name + "  (" + items[i].source + ")"
            for i in range(len(items))]


def start_weather(config):
    # เริ่ม thread ดึงอากาศ · ไม่มี LAT/LON ใน config = None (ไม่ใช้กฎฝน)
    if config.get("LAT") is None or config.get("LON") is None:
        return None
    return WeatherWorker(config["LAT"], config["LON"])


def add_by_date(rules, key, items):
    # เพิ่มของเข้า by_date ของวันนั้น (ไม่ซ้ำ)
    if key not in rules["by_date"]:
        rules["by_date"][key] = []
    for name in items:
        if name not in rules["by_date"][key]:
            rules["by_date"][key].append(name)


class App:

    def __init__(self, demo):
        self.base_config = storage.load_json("config.json")   # ค่าจริงจากไฟล์ (โหมดเดโมไม่แก้ตัวนี้)
        self.config = dict(self.base_config)                  # ค่าที่ใช้อยู่ (guard ใช้ dict ตัวนี้)
        self.timetable = storage.load_json("timetable.json")
        for name in ["rules.json", "activities.json"]:       # เพิ่ง clone มา = สร้างจากไฟล์ตัวอย่าง
            storage.ensure_from_example(name)
        self.activities = storage.load_json("activities.json")
        self.rules = {}
        self.alerted_items = []    # ชื่อของที่เตือนไปแล้วรอบนี้ (ออกซ้ำแล้วมีของใหม่ = ส่งเฉพาะของใหม่)

        self.guard = DoorGuard(self.config, self.timetable)
        self.reload_rules()

        # ตั้งโหมด (เดโม / ใช้งานจริง) + โหลดค่าที่จำไว้ของวันนี้ (เตือนแล้ว / ปิดเตือน)
        now = get_now()
        self.set_mode(bool(self.base_config.get("DEMO_MODE")) or demo, now)
        self.clean_old_dates(now)

        # Telegram ทำงานใน thread แยก (ไม่มี secrets = None ใช้แค่จอ)
        self.tg = start_telegram(load_secrets())
        if self.tg is None:
            print("ไม่มี secrets.json (หรือกรอกไม่ครบ) -> แสดงบนจออย่างเดียว ไม่ส่ง Telegram")
        else:
            print("เชื่อม Telegram แล้ว (ข้อความที่ส่งมาก่อนเปิดโปรแกรมจะไม่ถูกทำ)")
            # แจ้งว่าระบบเริ่มทำงาน + อัปเดตปุ่มล่างในมือถือเป็นชุดล่าสุด
            self.tg.send("✅ Door Buddy เริ่มทำงาน" + (" (โหมดเดโม)" if self.demo else ""))

        self.weather = start_weather(self.config)   # ดึงอากาศใน thread แยก (ไม่มีพิกัด = None)
        self.bot = ChatBot(self)   # เมนูปุ่ม + ถามทีละขั้น
        self.door = "close"    # สถานะประตูล่าสุด (เริ่มโปรแกรม = ปิด)
        self.last_tick = 0
        self.link = start_door_link()   # บอร์ด ESP32 ส่งสถานะประตูมาทาง WiFi (thread แยก)
        self.board_online = False
        self.board_warned = False       # แจ้งไปแล้วว่าบอร์ดหลุด (กลับมาแล้วค่อยแจ้งว่ากลับมา)
        self.board_hint_at = now[0] + 15   # ถึงเวลานี้ยังไม่ได้ยินบอร์ด -> พิมพ์คำแนะนำ

    def __str__(self):
        return ("App(" + str(self.guard) + ", ประตู=" + self.door
                + ", " + str(self.tg) + ", " + str(self.weather) + ")")

    # ---------- ไฟล์ ----------

    def reload_rules(self):
        # อ่าน rules.json ใหม่ (เผื่อผู้ใช้แก้ไฟล์ระหว่างโปรแกรมรัน) · ไฟล์เสีย = ใช้ค่าเดิม
        try:
            fresh = storage.load_json("rules.json")
        except (OSError, ValueError):
            print("อ่าน rules.json ไม่ได้ (ไฟล์เสีย?) -> ใช้ค่าเดิมไปก่อน")
            return
        if "appointments" not in fresh:   # rules.json รุ่นเก่ายังไม่มีหัวข้อนัด
            fresh["appointments"] = {}
        if "no_alert_dates" not in fresh:  # วันที่สั่งปิดเตือนล่วงหน้า
            fresh["no_alert_dates"] = []
        fresh.setdefault("weekly", [])      # กิจกรรมประจำ (ซ้ำทุกสัปดาห์)
        fresh.setdefault("weekly_skip", {}) # วันที่งดกิจกรรมประจำ
        # แก้ dict เดิม ไม่สร้างใหม่ ตัวแปรที่ชี้ rules อยู่จะเห็นค่าใหม่ด้วย
        self.rules.clear()
        self.rules.update(fresh)
        self.guard.appointments = self.rules["appointments"]
        self.guard.weekly = self.rules["weekly"]
        self.guard.weekly_skip = self.rules["weekly_skip"]

    def save_rules(self):
        storage.save_json("rules.json", self.rules)

    # ---------- โหมด เดโม / ใช้งานจริง ----------

    def set_mode(self, demo, now):
        # สลับโหมดได้ตลอด (ตอนเปิดโปรแกรม / ปุ่มในแชท / ตี 3 กลับเป็นใช้งานจริงเอง)
        #   เดโม: รอ 10 วิ, เตือนทุกครั้งที่ออก (เว้น 1 นาที), เตือนได้ทุกเวลา, เปิดค้าง 20 วิ
        #         บันทึก events ลง data/demo/ และไม่จำค่า "เตือนแล้ว" (อัดคลิปหลายเทคได้)
        #   (ใช้จริง: รอ 10 วิ / เปิดค้าง 60 วิ ใน config · เดโมลดเปิดค้างเหลือ 20 วิ อัดคลิปไม่ต้องรอนาน)
        self.config.clear()                 # แก้ dict เดิม guard จะเห็นค่าใหม่ทันที
        self.config.update(self.base_config)
        self.demo = demo
        if demo:
            self.config.update({"OUT_DELAY": 10, "COOLDOWN_MIN": 1, "OPEN_ALERT_SEC": 20,
                                "NO_CLASS_WINDOW": ["00:00", "23:59"],
                                "ALERT_EVERY_EXIT": True})
            self.guard.timetable = []       # เดโม: ไม่ใช้ช่วงก่อนคาบแรก (เตือนได้ทุกเวลา)
            self.state_file = None          # เดโม: ไม่จำค่าข้ามการปิด/เปิดโปรแกรม
            storage.EVENTS = DEMO_DATA + "events.csv"
            print("โหมดเดโม: OUT_DELAY 10 วิ, เตือนทุกครั้งที่ออก (เว้น 1 นาที), เตือนได้ทุกเวลา,"
                  " เปิดค้าง 20 วิ (บันทึกลง " + DEMO_DATA + ")")
        else:
            self.guard.timetable = self.timetable
            self.state_file = STATE
            storage.EVENTS = "data/events.csv"
        # ค่า "เตือนแล้ว" ของโหมดก่อนไม่เกี่ยวกับโหมดใหม่ (ปิดเตือนวันนี้ยังอยู่เหมือนเดิม)
        self.guard.alerted = False
        self.guard.alerted_windows = []
        self.guard.last_alert = None
        self.alerted_items = []
        self.saved_state = None
        self.load_state(now)
        self.apply_no_alert_dates(now)

    def load_state(self, now):
        # โหลดค่าที่จำไว้ของวันนี้ (เฉพาะโหมดใช้งานจริง) · ไม่มีไฟล์ / ไฟล์เสีย = เริ่มใหม่
        if self.state_file is None:
            return
        try:
            data = storage.load_json(self.state_file)
        except (OSError, ValueError):
            return
        if self.guard.load_dict(data, now):
            self.alerted_items = data.get("alerted_items", [])
            self.saved_state = self.state_data()
            print("โหลดสถานะวันนี้จาก " + self.state_file + " แล้ว")

    def toggle_demo(self, demo, now):
        # ปุ่ม "โหมดเดโม" ในแชท -> ข้อความตอบกลับ
        if demo == self.demo:
            return "ตอนนี้เป็นโหมด" + ("เดโม" if demo else "ใช้งานจริง") + "อยู่แล้ว"
        self.set_mode(demo, now)
        self.log(now, "mode", 0, "demo" if demo else "real")
        if demo:
            return ("เปิดโหมดเดโมแล้ว\n- รอ 10 วิ ก็นับว่าออกจากห้อง\n- เตือนทุกครั้งที่ออก (เว้น 1 นาที)"
                    "\n(ตี 3 จะกลับเป็นโหมดใช้งานจริงเอง)")
        return "กลับเป็นโหมดใช้งานจริงแล้ว"

    def state_data(self):
        # ค่าที่เก็บลง state.json: ของ guard + ชื่อของที่เตือนไปแล้ว
        data = self.guard.to_dict()
        data["alerted_items"] = list(self.alerted_items)
        return data

    def save_state(self):
        # เขียน state.json เฉพาะตอนค่าเปลี่ยน · เขียนไม่ได้ = ลองใหม่รอบหน้า (ไม่ล้ม) · เดโม = ไม่เขียน
        if self.state_file is None:
            return
        data = self.state_data()
        if data != self.saved_state:
            try:
                storage.save_json(self.state_file, data)
                self.saved_state = data
            except OSError:
                pass

    def log(self, now, event, secs=0, detail=""):
        # บันทึกเหตุการณ์ลง events.csv + พิมพ์บนจอ
        if not storage.append_event([day_key(now[1]), clock(now), event, int(secs), detail]):
            print("เขียน " + storage.EVENTS + " ไม่ได้ (เปิดค้างใน Excel?) เก็บไว้เขียนทีหลัง")
        text = "[" + clock(now) + "] log: " + event
        if secs:
            text += " " + str(int(secs)) + " วิ"
        if detail:
            text += " (" + detail + ")"
        print(text)

    def clean_old_dates(self, now):
        # ลบนัด/ของล่วงหน้าของวันที่ผ่านไปแล้ว ("YYYY-MM-DD" เทียบเป็น string ได้)
        self.reload_rules()
        today = day_key(now[1])
        removed = 0
        for section in ["by_date", "appointments"]:
            for key in list(self.rules[section].keys()):
                if key < today:
                    del self.rules[section][key]
                    removed += 1
        for key in list(self.rules["weekly_skip"].keys()):   # วันงดกิจกรรมประจำที่ผ่านไปแล้ว
            if key < today:
                del self.rules["weekly_skip"][key]
                removed += 1
        old = [key for key in self.rules["no_alert_dates"] if key < today]
        for key in old:
            self.rules["no_alert_dates"].remove(key)
        # ข้อมูลรุ่นเก่า: ของของนัดเคยถูกเก็บซ้ำใน by_date ด้วย -> เอาออก (ตอนนี้เก็บในนัดที่เดียว)
        for key in list(self.rules["by_date"].keys()):
            in_appts = []
            for appt in self.rules["appointments"].get(key, []):
                in_appts += appt.get("items", [])
            keep = [name for name in self.rules["by_date"][key] if name not in in_appts]
            if len(keep) != len(self.rules["by_date"][key]):
                removed += 1
                if keep:
                    self.rules["by_date"][key] = keep
                else:
                    del self.rules["by_date"][key]
        if removed > 0 or len(old) > 0:
            self.save_rules()
            print("ล้างนัด/ของล่วงหน้าที่ผ่านไปแล้ว " + str(removed) + " วัน")

    def apply_no_alert_dates(self, now):
        # วันนี้อยู่ในรายการ "ปิดเตือนล่วงหน้า" -> ปิดเตือนวันนี้ (เรียกตอนเปิดโปรแกรม + ข้ามคืน)
        if day_key(now[1]) in self.rules["no_alert_dates"]:
            self.guard.set_no_alert()

    # ---------- ข้อความ ----------

    def appts_on(self, key):
        # นัดของวัน key + กิจกรรมประจำของวันนั้น (ที่ไม่ได้งด)
        return appointments_on(self.rules, key, thai_dt.key_to_date(key).weekday())

    def upcoming_appts(self, key, now):
        # นัดของวัน key ที่ยังไม่ผ่าน (วันนี้ = เวลานัดยังไม่ถึง · วันอื่น = ทุกนัด)
        appts = sorted(self.appts_on(key), key=lambda a: a["time"])
        if key == day_key(now[1]):
            return [a for a in appts if a["time"] > hm(now)]
        return appts

    def rain_prob(self, key, now):
        # โอกาสฝนของวัน key (ไม่มีอากาศ / ไม่มีข้อมูล = None)
        if self.weather is None:
            return None
        return self.weather.rain_prob(key, now, self.config["RAIN_HOURS"])

    def checklist_items(self, date_info, now):
        # รายการของ (list ของ Item) สำหรับวัน date_info · ใช้ทั้งเช็คลิสต์เต็ม และหา "ของใหม่"
        key = day_key(date_info)
        prob = self.rain_prob(key, now)
        weather = None if prob is None else {"rain_prob": prob}
        # ส่งให้ core เฉพาะนัดที่ยังไม่ผ่าน (ของของนัดที่จบแล้วไม่ขึ้นในรายการ)
        rules = dict(self.rules)
        rules["appointments"] = dict(self.rules["appointments"])
        rules["appointments"][key] = self.upcoming_appts(key, now)
        return build_checklist(rules, self.timetable, weather, date_info,
                               self.config["RAIN_PROB"])

    def checklist_text(self, date_info, now=None):
        # เนื้อหาเช็คลิสต์ (ไม่มีบรรทัดหัวข้อ ผู้เรียกใส่เอง)
        # "# " = หัวข้อย่อย (Telegram เป็นตัวหนา)
        # now = เวลาตอนนี้: ถ้าเป็นเช็คลิสต์ของวันนี้ นัดที่เลยเวลาไปแล้วไม่ต้องเอาของไป
        if now is None:
            now = get_now()
        key = day_key(date_info)
        appts = sorted(self.appts_on(key), key=lambda a: a["time"])
        upcoming = self.upcoming_appts(key, now)
        lines = []
        if appts:
            lines.append("# นัด")
            for appt in appts:
                line = "- " + appt["time"] + "  " + appt["name"]
                if appt.get("weekly"):
                    line += "  (ประจำ)"
                if appt not in upcoming:
                    line += "  (ผ่านแล้ว)"
                lines.append(line)
            lines.append("")
        # อากาศ: วันนี้ = อีก RAIN_HOURS ชม. · วันอื่น = ช่วงกลางวัน · ไม่มีข้อมูล = ไม่ใช้กฎฝน
        if self.weather is not None:
            prob = self.rain_prob(key, now)
            lines.append("# อากาศ")
            if prob is None:
                lines.append("(ยังไม่มีข้อมูลอากาศ)")
            else:
                when = ("ในอีก " + str(self.config["RAIN_HOURS"]) + " ชม."
                        if key == day_key(now[1]) else "ช่วงกลางวัน")
                lines.append("- โอกาสฝน " + str(prob) + "% " + when)
            lines.append("")
        items = self.checklist_items(date_info, now)
        if len(items) == 0:
            lines.append("(ไม่มีของต้องพก)")
            return "\n".join(lines)
        lines.append("# อย่าลืม")
        lines += item_lines(items)
        return "\n".join(lines)

    def notify(self, text, silent=False, buttons=None):
        # พิมพ์ลงจอ + ใส่คิวรอส่ง Telegram (thread ส่งเอง ลูปหลักไม่ต้องรอ)
        print(plain(text))
        if buttons:
            print("   ปุ่ม: " + " | ".join(label + " <" + data + ">"
                                          for row in buttons for label, data in row))
        if self.tg is not None:
            self.tg.send(text, silent, buttons)

    def show_only(self, outs):
        # แสดงผลจาก ChatBot บนจออย่างเดียว (ไม่ส่ง Telegram) ใช้กับปุ่ม m / b
        for out in outs:
            print(plain(out.get("send", out.get("text", ""))))
            for row in out.get("buttons") or []:
                print("   " + " | ".join(label + " <" + data + ">" for label, data in row))

    def deliver(self, outs):
        # ส่งผลจาก ChatBot: {"send": ข้อความ, "buttons"} หรือ {"edit": message_id, "text", "buttons"}
        for out in outs:
            if "edit" in out:
                print("(แก้ข้อความเมนู) " + plain(out["text"]))
                if self.tg is not None:
                    self.tg.edit(out["edit"], out["text"], out.get("buttons"))
            else:
                self.notify(out["send"], out.get("silent", False), out.get("buttons"))

    def handle(self, actions, now):
        # ทำตาม action ที่ DoorGuard ส่งกลับมา
        for action in actions:
            if action["do"] == "checklist":
                self.reload_rules()
                # ปุ่มแก้สถานะโผล่เฉพาะใต้ข้อความเตือน (เผื่อระบบเดาผิด)
                self.notify("🚪 ออกจากห้องแล้ว " + hm(now) + "\n"
                            + self.checklist_text(now[1], now),
                            buttons=[[("ยังไม่ได้ออก", "o:home")]])
                # จำว่าเตือนของอะไรไปแล้ว (ออกซ้ำแล้วมีของใหม่ จะส่งเฉพาะของใหม่)
                self.alerted_items = [i.name for i in self.checklist_items(now[1], now)]
                self.log(now, "alert")
            elif action["do"] == "checklist_quiet":
                self.reload_rules()
                self.notify("🏠 เพิ่งกลับห้อง " + hm(now) + "\n"
                            + "(ถ้าจริง ๆ กำลังจะออกไป นี่คือของที่ต้องพก)\n\n"
                            + self.checklist_text(now[1], now), silent=True,
                            buttons=[[("จริง ๆ กำลังออก", "o:out")]])
                self.log(now, "alert_quiet")
            elif action["do"] == "prep":
                # เช็คลิสต์ล่วงหน้า: เตรียมของก่อนออก (ตอนออกจริงยังเตือนอีกรอบตามปกติ)
                self.reload_rules()
                left = (int(action["time"][:2]) * 60 + int(action["time"][3:5])
                        - now[1][3] * 60 - now[1][4])
                self.notify("🎒 เตรียมของ · " + action["name"] + " " + action["time"]
                            + " (อีก " + str(left) + " นาที)\n"
                            + self.checklist_text(now[1], now))
                self.log(now, "prep", 0, action["name"])
            elif action["do"] == "short_msg":
                self.notify("🚪 ออกจากห้องแล้ว " + hm(now) + "\n"
                            + "(กดปุ่ม \"เช็คลิสต์\" ถ้าอยากดูของที่ต้องพก)", silent=True)
                self.log(now, "alert_short")
            elif action["do"] == "open_long":
                minutes = int(action["secs"]) // 60
                how_long = (str(minutes) + " นาที") if minutes > 0 else (
                    str(int(action["secs"])) + " วินาที")
                self.notify("⚠️ ประตูเปิดค้างมา " + how_long + "\nลืมปิดหรือเปล่า")
                self.log(now, "open_long", action["secs"])
            elif action["do"] == "skip":
                # ไม่เตือนซ้ำเพราะเตือนไปแล้ว แต่ถ้ามีของใหม่ (เช่น ร่ม เพราะฝนเพิ่งมา) ส่งเฉพาะของใหม่
                if action.get("code") in ["window", "cooldown"] and self.send_new_items(now):
                    continue
                self.log(now, "skip", 0, action["why"])
            elif action["do"] == "log":
                self.log(now, action["event"], action["secs"])
            elif action["do"] == "new_day":
                print("[" + clock(now) + "] ข้ามคืน -> เริ่มวันใหม่")
                self.alerted_items = []
                if self.demo:                   # ลืมปิดโหมดเดโม -> ตี 3 กลับเป็นใช้งานจริงเอง
                    self.notify(self.toggle_demo(False, now) + "\n(รีเซ็ตประจำวัน)")
                self.clean_old_dates(now)
                self.apply_no_alert_dates(now)

    def send_new_items(self, now):
        # ออกจากห้องซ้ำ: ส่งเฉพาะของที่ยังไม่เคยเตือน · คืน True ถ้ามีของใหม่และส่งแล้ว
        self.reload_rules()
        items = self.checklist_items(now[1], now)
        new = [i for i in items if i.name not in self.alerted_items]
        if not new:
            return False
        self.notify("🚪 ออกจากห้องแล้ว " + hm(now) + "\n"
                    + "(เตือนไปแล้วรอบหนึ่ง นี่คือของที่เพิ่มมา)\n\n# ของที่เพิ่มมา\n"
                    + "\n".join(item_lines(new)),
                    buttons=[[("ยังไม่ได้ออก", "o:home")]])
        self.alerted_items += [i.name for i in new]
        self.log(now, "alert_new", 0, ", ".join(i.name for i in new))
        return True

    # ---------- เหตุการณ์ประตู + คำสั่ง ----------

    def door_event(self, kind, now):
        # รับเหตุการณ์ประตู (จากคีย์บอร์ด ตอนนี้ / จาก ESP32 ภายหลัง)
        word = "เปิด" if kind == "open" else "ปิด"
        if kind == self.door:
            # กดซ้ำ: ประตูอยู่ในสถานะนั้นแล้ว ไม่ส่งเข้า guard
            print("[" + clock(now) + "] ประตู" + word + "อยู่แล้ว")
            return
        self.door = kind
        actions = self.guard.on_door(kind, now)
        print("[" + clock(now) + "] ประตู" + word + " -> " + self.guard.state)
        self.log(now, "door_" + kind)
        self.handle(actions, now)

    def run_command(self, text, now):
        # รับข้อความแชท -> แยกคำสั่ง (core) -> ทำตาม -> คืน (ข้อความตอบกลับ, actions จาก guard)
        self.reload_rules()        # เผื่อผู้ใช้แก้ rules.json เองระหว่างโปรแกรมรัน
        today = datetime.date(now[1][0], now[1][1], now[1][2])
        time_text, rest = thai_dt.find_time(text)
        date, rest = thai_dt.find_date(rest, today)
        if date is None and time_text is not None:
            date = today           # มีเวลาแต่ไม่บอกวัน = วันนี้
        found = None
        if date is not None:
            found = (thai_dt.date_key(date), rest)
        cmd = parse_command(text, found, self.activities, time_text)
        print("[" + clock(now) + "] คำสั่ง: " + str(cmd))

        if cmd["cmd"] == "help":
            return CHAT_HELP, []
        if cmd["cmd"] == "list":
            key = cmd["date"] or day_key(now[1])
            return self.checklist_page(key, today), []
        if cmd["cmd"] == "bad_date":
            return "ไม่เข้าใจวันที่\n(ลองแบบนี้: /list พรุ่งนี้, /list 5/11)", []
        if cmd["cmd"] == "status":
            return self.status_text(), []
        if cmd["cmd"] == "no_alert":
            return self.no_alert_on(cmd.get("date"), now), []
        if cmd["cmd"] == "alert_on":
            return self.alert_on_today(), []
        if cmd["cmd"] == "still_home":
            return "แก้แล้ว: ยังอยู่ห้อง", self.guard.still_home(now)
        if cmd["cmd"] == "out_now":
            return "แก้แล้ว: ออกไปข้างนอก", self.guard.force_out(now)

        if cmd["cmd"] == "forget":
            self.log(now, "forget", 0, cmd["item"])   # ไว้นับว่าลืมอะไรบ่อย
            return self.add_always(cmd["item"]), []
        if cmd["cmd"] == "add_always":
            return self.add_always(cmd["item"]), []
        if cmd["cmd"] == "remove":
            return self.remove_always(cmd["item"]), []
        if cmd["cmd"] == "add_appointment":
            return self.add_appointment(cmd["date"], cmd["time"], cmd["name"],
                                        cmd["items"]), []
        if cmd["cmd"] == "list_appts":
            return self.appointments_text(), []
        if cmd["cmd"] == "remove_appt":
            if cmd["date"] is None:
                return "บอกวันด้วย เช่น ลบนัด 25/10 หรือ ลบนัด พรุ่งนี้ 8โมง", []
            return self.remove_appointments(cmd["date"], cmd["time"]), []
        if cmd["cmd"] == "add_activity" or cmd["cmd"] == "add_item":
            return self.add_date_items(cmd["date"], cmd["items"]), []

        return "ไม่เข้าใจคำสั่ง\n(กดปุ่มด้านล่าง หรือพิมพ์ /help เพื่อดูวิธีใช้)", []

    # ---------- แก้ข้อมูล (ใช้ร่วมกันทั้งพิมพ์คำสั่ง และกดปุ่มเมนู) ----------
    # ทุกเมธอดอ่าน rules.json ใหม่ก่อนแก้ แล้วบันทึกทันที · คืนข้อความตอบกลับ

    def checklist_page(self, key, today):
        # เช็คลิสต์ของวัน key พร้อมหัวข้อ (ใช้ทั้งพิมพ์ /list และกดปุ่ม)
        self.reload_rules()
        day = thai_dt.key_to_date(key)
        return ("📋 เช็คลิสต์ " + thai_dt.short_day(key, today) + "\n"
                + self.checklist_text(thai_dt.date_tuple(day), get_now()))

    def status_text(self):
        text = ("สถานะระบบ\n"
                + "- โหมด: " + ("เดโม" if self.demo else "ใช้งานจริง")
                + "\n- ตอนนี้: " + STATE_TH.get(self.guard.state, self.guard.state)
                + "\n- ประตู: " + ("เปิด" if self.door == "open" else "ปิด")
                + "\n- เตือนวันนี้ไปแล้ว: " + ("ใช่" if self.guard.alerted else "ยัง")
                + "\n- ปิดเตือนวันนี้: " + ("ใช่" if self.guard.no_alert else "ไม่"))
        if self.tg is not None:
            text += "\n- Telegram: " + ("ออนไลน์" if self.tg.online else "ออฟไลน์")
        if self.link is not None:
            ago = self.link.seconds_since_seen(time.time())
            if ago is None:
                text += "\n- บอร์ดประตู: ยังไม่เคยเชื่อม"
            elif self.link.online(time.time()):
                text += "\n- บอร์ดประตู: ออนไลน์"
            else:
                text += "\n- บอร์ดประตู: ออฟไลน์ (เงียบไป " + str(ago) + " วิ)"
        if self.weather is not None:
            w = self.weather
            if w.fake is not None:
                text += "\n- อากาศ: จำลองฝน " + str(w.fake) + "%"
            elif w.ready():
                text += ("\n- อากาศ: อัปเดตล่าสุด "
                         + time.strftime("%H:%M", time.localtime(w.fetched_at)))
            else:
                text += "\n- อากาศ: ยังไม่มีข้อมูล (เน็ตหลุด หรือยังดึงไม่เสร็จ)"
        return text

    def no_alert_today(self):
        return self.no_alert_on(None, None)

    def no_alert_on(self, key, now):
        # ปิดเตือน: key None หรือวันนี้ = ปิดทันที · วันอื่น = จดไว้ ถึงวันนั้นค่อยปิด
        if key is None or (now is not None and key == day_key(now[1])):
            self.guard.set_no_alert()
            return "🔕 โอเค วันนี้จะไม่เตือน\n(พรุ่งนี้เตือนตามปกติ)"
        self.reload_rules()
        if key not in self.rules["no_alert_dates"]:
            self.rules["no_alert_dates"].append(key)
            self.rules["no_alert_dates"].sort()
            self.save_rules()
        return "🔕 โอเค วัน " + thai_dt.short_day(key) + " จะไม่เตือน"

    def alert_on_today(self):
        # ยกเลิก "วันนี้ไม่ต้องเตือน" -> เตือนกลับตามปกติ (ลบออกจากรายการปิดล่วงหน้าด้วย)
        self.guard.set_alert_on()
        self.reload_rules()
        today = day_key(get_now()[1])
        if today in self.rules["no_alert_dates"]:
            self.rules["no_alert_dates"].remove(today)
            self.save_rules()
        return "เปิดเตือนกลับแล้ว\n(วันนี้จะเตือนตามปกติ)"

    def remember_activity(self, name, items):
        # จำกิจกรรมไว้ใน activities.json (ครั้งหน้ามีปุ่มให้กดเลือก พร้อมของ)
        # ลบแล้วใส่ใหม่ = ย้ายไปท้ายสุด -> ท้ายไฟล์คือกิจกรรมที่ใช้ล่าสุด (ไว้เรียงปุ่ม)
        try:
            activities = storage.load_json("activities.json")
        except (OSError, ValueError):
            return False
        activities.pop(name, None)
        activities[name] = list(items)
        storage.save_json("activities.json", activities)
        self.activities = activities
        return True

    def clear_activities(self):
        # เคลียร์กิจกรรมประจำออกทั้งหมด (เก็บหมายเหตุ _note ไว้)
        try:
            activities = storage.load_json("activities.json")
        except (OSError, ValueError):
            return "อ่าน activities.json ไม่ได้"
        activities = {k: v for k, v in activities.items() if k.startswith("_")}
        storage.save_json("activities.json", activities)
        self.activities = activities
        return "เคลียร์กิจกรรมประจำออกทั้งหมดแล้ว"

    # ---------- กิจกรรมประจำ (ซ้ำทุกสัปดาห์) ----------

    def weekly_rows(self):
        # กิจกรรมประจำเรียงตามวัน (จันทร์ก่อน) แล้วตามเวลา: list ของ (ลำดับในไฟล์, entry)
        self.reload_rules()
        weekly = self.rules["weekly"]
        days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        order = sorted(range(len(weekly)),
                       key=lambda i: (days.index(weekly[i]["day"]), weekly[i]["time"]))
        return [(i, weekly[i]) for i in order]

    def add_weekly(self, day, time_text, name, items):
        self.reload_rules()
        self.rules["weekly"].append({"day": day, "time": time_text, "name": name,
                                     "items": list(items)})
        self.save_rules()
        reply = ("✅ บันทึกกิจกรรมประจำแล้ว\n- ทุก" + WEEKDAY_TH[day] + "  " + time_text
                 + "  " + name)
        if len(items) > 0:
            reply += "\n- ต้องพก: " + ", ".join(items)
        reply += "\n(ระบบนับเป็นนัดทุกสัปดาห์ · สัปดาห์ไหนไม่มี กด งดบางสัปดาห์)"
        return reply

    def remove_weekly(self, index):
        self.reload_rules()
        entry = self.rules["weekly"].pop(index)
        self.save_rules()
        return "ลบแล้ว: ทุก" + WEEKDAY_TH[entry["day"]] + " " + entry["time"] + " " + entry["name"]

    def toggle_weekly_skip(self, key, index):
        # งด/ยกเลิกงด กิจกรรมประจำอันที่ index เฉพาะวัน key
        self.reload_rules()
        entry = self.rules["weekly"][index]
        name = skip_key(entry)
        skipped = self.rules["weekly_skip"].setdefault(key, [])
        when = thai_dt.short_day(key) + " " + name
        if name in skipped:
            skipped.remove(name)
            if not skipped:
                del self.rules["weekly_skip"][key]
            reply = "ยกเลิกงดแล้ว: " + when + " (เตือนตามปกติ)"
        else:
            skipped.append(name)
            reply = "งดแล้ว: " + when + " (วันนั้นไม่นับกิจกรรมนี้)"
        self.save_rules()
        return reply

    def add_weekly_items(self, index, names):
        # เพิ่มของให้กิจกรรมประจำอันที่ index (ไม่ใส่ซ้ำ)
        self.reload_rules()
        entry = self.rules["weekly"][index]
        items = entry.setdefault("items", [])
        added = [n for n in names if n not in items]
        items += added
        self.save_rules()
        return ("เพิ่มของให้ ทุก" + WEEKDAY_TH[entry["day"]] + " " + entry["time"] + " "
                + entry["name"] + " แล้ว: " + (", ".join(added) if added else "(มีอยู่แล้ว)"))

    def remove_weekly_item(self, index, name):
        self.reload_rules()
        entry = self.rules["weekly"][index]
        if name in entry.get("items", []):
            entry["items"].remove(name)
            self.save_rules()
        return "ลบ " + name + " ออกจาก " + entry["name"] + " แล้ว"

    def clear_weekly(self):
        self.reload_rules()
        self.rules["weekly"] = []
        self.rules["weekly_skip"] = {}
        self.save_rules()
        self.reload_rules()
        return "เคลียร์กิจกรรมประจำออกทั้งหมดแล้ว"

    def forget_activity(self, name):
        # ลบกิจกรรมที่จำไว้
        try:
            activities = storage.load_json("activities.json")
        except (OSError, ValueError):
            return "อ่าน activities.json ไม่ได้"
        if name not in activities:
            return "ไม่เจอ " + name + " ในนัดที่บันทึกไว้"
        del activities[name]
        storage.save_json("activities.json", activities)
        self.activities = activities
        return "ลบ " + name + " ออกจากนัดที่บันทึกไว้แล้ว"

    def add_always(self, name):
        self.reload_rules()
        if name in self.rules["always"]:
            return name + " อยู่ในของที่พกทุกวันอยู่แล้ว"
        self.rules["always"].append(name)
        self.save_rules()
        return "เพิ่ม " + name + " ในของที่พกทุกวันแล้ว"

    def remove_always(self, name):
        self.reload_rules()
        if name not in self.rules["always"]:
            return "ไม่เจอ " + name + " ในของที่พกทุกวัน"
        self.rules["always"].remove(name)
        self.save_rules()
        return "ลบ " + name + " ออกจากของที่พกทุกวันแล้ว"

    def add_date_items(self, key, items):
        self.reload_rules()
        add_by_date(self.rules, key, items)
        self.save_rules()
        return "เพิ่มของที่ต้องพกวัน " + thai_dt.short_day(key) + " แล้ว: " + ", ".join(items)

    def remove_date_item(self, key, name):
        self.reload_rules()
        items = self.rules["by_date"].get(key, [])
        if name not in items:
            return "ไม่เจอ " + name + " (วัน " + thai_dt.short_day(key) + ")"
        items.remove(name)
        if len(items) == 0:
            del self.rules["by_date"][key]
        self.save_rules()
        return "ลบ " + name + " (วัน " + thai_dt.short_day(key) + ") แล้ว"

    def add_appointment(self, key, time_text, name, items):
        self.reload_rules()
        if key not in self.rules["appointments"]:
            self.rules["appointments"][key] = []
        # ของของนัดเก็บในตัวนัดที่เดียว (ไม่ใส่ by_date ซ้ำ ไม่งั้นลบที่หนึ่งแล้วยังโผล่อีกที่)
        self.rules["appointments"][key].append({"time": time_text, "name": name,
                                                "items": list(items)})
        self.save_rules()
        reply = ("✅ บันทึกนัดแล้ว\n- " + thai_dt.short_day(key) + "  " + time_text + "  " + name)
        if len(items) > 0:
            reply += "\n- ต้องพก: " + ", ".join(items)
        reply += ("\n(ถ้าออกจากห้องช่วง " + str(self.config["BEFORE_CLASS_MIN"])
                  + " นาทีก่อนนัด จะส่งเช็คลิสต์ให้)")
        return reply

    def appointment_rows(self):
        # นัดทั้งหมด เรียงตามวันและเวลา: list ของ (key, ลำดับในไฟล์ของวันนั้น, appt)
        # ใช้ (key, ลำดับ, เวลา) อ้างถึงนัด 1 อัน (นัด 2 อันเวลาเดียวกันจะได้ไม่ปนกัน)
        self.reload_rules()
        rows = []
        for key in sorted(self.rules["appointments"].keys()):
            day = self.rules["appointments"][key]
            order = sorted(range(len(day)), key=lambda i: day[i]["time"])
            for index in order:
                rows.append((key, index, day[index]))
        return rows

    def find_appt(self, key, index, time_text):
        # หานัดจาก (วัน, ลำดับ, เวลา) · ไม่เจอ / เวลาไม่ตรง (ลำดับเลื่อนเพราะลบนัดอื่น) = None
        self.reload_rules()
        day = self.rules["appointments"].get(key, [])
        if 0 <= index < len(day) and day[index]["time"] == time_text:
            return day[index]
        return None

    def remove_appointment_at(self, key, index, time_text):
        # ลบนัด 1 อัน (ปุ่ม 🗑 ในเมนู)
        appt = self.find_appt(key, index, time_text)
        if appt is None:
            return "ไม่เจอนัดนี้แล้ว (อาจถูกลบไปแล้ว)"
        day = self.rules["appointments"][key]
        day.pop(index)
        if len(day) == 0:
            del self.rules["appointments"][key]
        self.save_rules()
        return ("ลบนัดแล้ว: " + thai_dt.short_day(key) + "  " + appt["time"]
                + "  " + appt["name"])

    def add_appt_items(self, key, index, time_text, names):
        # เพิ่มของสำหรับนัด (ไม่ซ้ำ รวมแล้วไม่เกิน MAX_ITEMS)
        appt = self.find_appt(key, index, time_text)
        if appt is None:
            return "ไม่เจอนัดนี้แล้ว (อาจถูกลบไปแล้ว)"
        items = appt.setdefault("items", [])
        added = []
        for name in names:
            if name not in items and len(items) < MAX_ITEMS:
                items.append(name)
                added.append(name)
        self.save_rules()
        title = appt["name"] + " (" + thai_dt.short_day(key) + " " + appt["time"] + ")"
        if not added:
            return "ไม่ได้เพิ่มอะไร (มีอยู่แล้ว หรือครบ " + str(MAX_ITEMS) + " ชิ้นแล้ว)"
        return "เพิ่มของสำหรับ " + title + " แล้ว: " + ", ".join(added)

    def remove_appt_item(self, key, index, time_text, name):
        # ลบของ 1 ชิ้นออกจากนัด
        appt = self.find_appt(key, index, time_text)
        if appt is None or name not in appt.get("items", []):
            return "ไม่เจอแล้ว (อาจถูกลบไปแล้ว)"
        appt["items"].remove(name)
        self.save_rules()
        return "ลบ " + name + " ออกจากนัด " + appt["name"] + " แล้ว"

    def appointments_text(self):
        rows = self.appointment_rows()
        if len(rows) == 0:
            return "ยังไม่มีนัด"
        lines = []
        for key, index, appt in rows:
            lines.append("- " + thai_dt.short_day(key) + "  " + appt["time"] + "  " + appt["name"])
        return "📅 นัดทั้งหมด\n" + "\n".join(lines)

    def remove_appointments(self, key, time_text=None):
        # ลบนัดของวัน key · time_text = None ลบทั้งวัน · ใส่เวลา = ลบเฉพาะเวลานั้น
        self.reload_rules()
        rules = self.rules
        appts = rules["appointments"].get(key, [])
        keep = []
        gone = []
        for appt in appts:
            if time_text is not None and appt["time"] != time_text:
                keep.append(appt)          # ระบุเวลา = เก็บนัดเวลาอื่นไว้
            else:
                gone.append(appt)
        if len(gone) == 0:
            return "ไม่เจอนัดที่จะลบ (วัน " + thai_dt.short_day(key) + ")"
        if len(keep) > 0:
            rules["appointments"][key] = keep
        else:
            del rules["appointments"][key]
        # ลบของที่มากับนัดออกจาก by_date ด้วย (ถ้านัดที่เหลือไม่ได้ใช้ของนั้น)
        still_used = []
        for appt in keep:
            still_used += appt.get("items", [])
        for appt in gone:
            for name in appt.get("items", []):
                if name in rules["by_date"].get(key, []) and name not in still_used:
                    rules["by_date"][key].remove(name)
        if key in rules["by_date"] and len(rules["by_date"][key]) == 0:
            del rules["by_date"][key]
        self.save_rules()
        names = ", ".join(appt["time"] + " " + appt["name"] for appt in gone)
        return "ลบนัดวัน " + thai_dt.short_day(key) + " แล้ว: " + names

    def clear_always(self):
        # ล้างของพกทุกวันทั้งหมด
        self.reload_rules()
        self.rules["always"] = []
        self.save_rules()
        return "เคลียร์ของพกทุกวันออกทั้งหมดแล้ว"

    def clear_date_items(self, key=None):
        # ล้างของเฉพาะวัน (ทั้งวัน + ของของนัด) · key = None ทุกวัน / ใส่วัน = วันนั้นวันเดียว
        # ล้างแค่ของ นัดยังอยู่
        self.reload_rules()
        keys = [key] if key else list(set(self.rules["by_date"]) | set(self.rules["appointments"]))
        for day in keys:
            self.rules["by_date"].pop(day, None)
            for appt in self.rules["appointments"].get(day, []):
                appt["items"] = []
        self.save_rules()
        if key:
            return "เคลียร์ของวัน " + thai_dt.short_day(key) + " ออกแล้ว (นัดยังอยู่)"
        return "เคลียร์ของเฉพาะวันออกทั้งหมดแล้ว (นัดยังอยู่)"

    def clear_appointments(self):
        # ล้างนัดทั้งหมด (ทีละวัน เพื่อลบของที่มากับนัดด้วย)
        keys = list(self.appointment_keys())
        for key in keys:
            self.remove_appointments(key)
        return "เคลียร์นัดออกทั้งหมดแล้ว"

    def appointment_keys(self):
        self.reload_rules()
        return sorted(self.rules["appointments"].keys())

    # ---------- Telegram ----------

    def check_chat(self, now):
        # หยิบข้อความแชท/การกดปุ่มที่ thread รับมาแล้ว (ไม่รอเน็ต) ส่งให้ ChatBot จัดการ
        if self.tg is None:
            return
        for item in self.tg.receive():
            if item["kind"] == "text":
                print("[" + clock(now) + "] แชท: " + item["text"])
                self.deliver(self.bot.on_text(item["text"], now))
            else:
                print("[" + clock(now) + "] กดปุ่ม: " + item["data"])
                self.deliver(self.bot.on_button(item["data"], item["message_id"],
                                                item["text"], now))

    def check_board(self, now):
        # เหตุการณ์ประตูจากบอร์ด ESP32 (thread รับมาแล้ว ไม่ต้องรอ) + แจ้งเมื่อบอร์ดหลุด/กลับมา
        if self.link is None:
            return
        if self.board_hint_at is not None and now[0] >= self.board_hint_at:
            # เปิดโปรแกรมมาสักพักยังไม่ได้ยินบอร์ดเลย -> บอกสาเหตุที่เจอบ่อย (บอกครั้งเดียว)
            self.board_hint_at = None
            if self.link.seconds_since_seen(now[0]) is None:
                print("[" + clock(now) + "] ยังไม่ได้ยินบอร์ดประตูเลย: เช็กว่าคอมกับบอร์ดต่อ WiFi "
                      "ชื่อเดียวกัน (บอร์ดใช้ได้แค่ 2.4GHz) และไฟสีฟ้าบนบอร์ดติด")
        for kind, epoch, real in self.link.get_events():
            if real:
                self.door_event(kind, time_at(epoch))     # ใช้เวลาที่ประตูขยับจริง
            else:
                # ได้ยินบอร์ดครั้งแรก / บอร์ดรีสตาร์ท: เชื่อสถานะจากบอร์ด (ไม่นับเป็นการเปิดปิด)
                print("[" + clock(now) + "] บอร์ดประตูเชื่อมแล้ว (" + str(self.link.ip)
                      + ") ประตู" + ("เปิด" if kind == "open" else "ปิด") + "อยู่")
                self.door = kind
        online = self.link.online(now[0])
        if online == self.board_online:
            return
        self.board_online = online
        if not online:
            self.board_warned = True
            self.notify("⚠️ บอร์ดประตูขาดการเชื่อมต่อ\n"
                        "(ระหว่างนี้ระบบไม่รู้ว่าออกจากห้อง · เช็กไฟเลี้ยงบอร์ดกับ WiFi)")
        elif self.board_warned:
            self.board_warned = False
            self.notify("บอร์ดประตูกลับมาเชื่อมต่อแล้ว", silent=True)

    # ---------- ลูปหลัก ----------

    def step(self, now, key):
        # ทำงาน 1 รอบของลูปหลัก · คืน False เมื่อผู้ใช้กด q
        if key == "q":
            print("ออกจากโปรแกรม")
            return False
        elif key == "o":
            self.door_event("open", now)
        elif key == "c":
            self.door_event("close", now)
        elif key == "l":
            today = datetime.date(now[1][0], now[1][1], now[1][2])
            print(plain(self.checklist_page(day_key(now[1]), today)))
        elif key == "s":
            print("[" + clock(now) + "] " + str(self))
        elif key == "m":
            # พิมพ์ข้อความแชทในจอ (ทดสอบได้โดยไม่ใช้มือถือ) · ตอบแค่บนจอ
            text = input("พิมพ์ข้อความแชท: ")
            self.show_only(self.bot.on_text(text, get_now()))
        elif key == "b":
            # จำลองการกดปุ่มติดข้อความ (พิมพ์ data ที่เห็นใน <...>) · ตอบแค่บนจอ
            data = input("data ของปุ่ม: ")
            self.show_only(self.bot.on_button(data, 0, "", get_now()))
        elif key == "w":
            # จำลองฝน (ทดสอบ/อัดคลิป): ของจริง -> ฝน 80% -> ไม่มีฝน -> ของจริง
            if self.weather is None:
                print("ไม่ได้เปิดใช้อากาศ (ไม่มี LAT/LON ใน config.json)")
            else:
                i = FAKE_RAIN.index(self.weather.fake)
                self.weather.fake = FAKE_RAIN[(i + 1) % len(FAKE_RAIN)]
                print("[" + clock(now) + "] " + str(self.weather))

        self.check_board(now)
        self.check_chat(now)

        # tick ทุก 1 วินาที
        if now[0] - self.last_tick >= 1:
            self.last_tick = now[0]
            before = self.guard.state
            actions = self.guard.tick(now)
            if self.guard.state != before:
                print("[" + clock(now) + "] " + before + " -> " + self.guard.state)
            self.handle(actions, now)

        self.save_state()
        return True


def main():
    app = App("--demo" in sys.argv)
    print(HELP)
    while True:
        try:
            if not app.step(get_now(), read_key()):
                break
        except Exception:
            # กันล้มทั้งระบบ: error ตรงไหนก็ตาม พิมพ์รายละเอียดไว้ไล่หาสาเหตุ แล้วทำงานต่อ
            print("เกิด error (โปรแกรมยังทำงานต่อ):")
            traceback.print_exc()
            try:
                app.log(get_now(), "error", 0, traceback.format_exc().splitlines()[-1])
            except Exception:
                pass
            time.sleep(1)  # กัน error วนถี่ ๆ
        time.sleep(0.05)   # พักสั้น ๆ ไม่ให้กิน CPU (ไม่ใช่ sleep ยาว)


if __name__ == "__main__":
    main()
