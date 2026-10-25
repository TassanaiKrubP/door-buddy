# DoorGuard: state machine กันเตือนผิด
# ห้ามใช้ datetime / ห้ามทำ I/O (กติกา core/) เวลาต้องส่งเข้ามาเสมอ
#
# now = (epoch, tup)
#   epoch = วินาที ใช้หาระยะเวลา
#   tup   = (ปี, เดือน, วัน, ชม, นาที, วินาที, วันในสัปดาห์) ใช้ดูนาฬิกา/วัน
#
# on_door / tick คืนค่าเป็น list ของ action (dict) ให้ฝั่ง pc ไปทำต่อ
#   {"do": "checklist"}                     ส่งเช็คลิสต์เต็ม
#   {"do": "short_msg"}                     ส่งข้อความบรรทัดเดียวแบบไม่มีเสียง
#   {"do": "log", "event": ..., "secs": ...} บันทึกลง events.csv
#   {"do": "skip", "why": ..., "code": ...} ออกจริงแต่ไม่เตือน (บอกเหตุผล)
#                                           code = no_alert / outside / window (เตือนไปแล้วในช่วงนี้) / cooldown
#   {"do": "open_long", "secs": ...}        ประตูเปิดค้างนานเกิน OPEN_ALERT_SEC (เตือนครั้งเดียวต่อการเปิด)
#   {"do": "checklist_quiet"}               กลับห้องในช่วงเตือนที่ยังไม่เตือน -> ส่งเช็คลิสต์แบบเงียบ
#                                           (กันกรณีสถานะกลับด้าน: จริง ๆ กำลังออก แต่ระบบคิดว่ากลับ)
#   {"do": "new_day"}                       ข้าม NIGHT_RESET (ฝั่ง pc ใช้ล้างนัดเก่า)
#   {"do": "prep", "time": "09:00", "name": ...}
#                                           เช็คลิสต์ล่วงหน้า PREP_MIN นาทีก่อนคาบแรก/นัด
#                                           (เตรียมของก่อนออก · เตือนตอนออกยังมาเหมือนเดิม)

from core.checklist import DAYS
from core.weekly import weekly_on

HOME = "HOME"
DOOR_OPEN = "DOOR_OPEN"
MAYBE_OUT = "MAYBE_OUT"
OUT = "OUT"
ENTERING = "ENTERING"


def to_min(text):
    # "HH:MM" -> นาทีนับจากเที่ยงคืน
    return int(text[:2]) * 60 + int(text[3:5])


def next_day(tup):
    # วันถัดไป (ปี, เดือน, วัน) แบบไม่ใช้ datetime (กติกา core/)
    y, m, d = tup[0], tup[1], tup[2]
    leap = (y % 4 == 0 and y % 100 != 0) or y % 400 == 0
    days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    if d < days:
        return (y, m, d + 1)
    if m < 12:
        return (y, m + 1, 1)
    return (y + 1, 1, 1)


class DoorGuard:

    def __init__(self, config, timetable, appointments=None):
        self.config = config
        self.timetable = timetable
        # นัด: {"YYYY-MM-DD": [{"time": "08:00", "name": ...}]} (ใช้ dict เดียวกับ rules
        # ฝั่ง pc เพิ่มนัดใหม่แล้ว guard เห็นทันที)
        if appointments is None:
            appointments = {}
        self.appointments = appointments
        self.weekly = []           # กิจกรรมประจำ (ฝั่ง pc ใส่ list เดียวกับ rules["weekly"])
        self.weekly_skip = {}      # วันที่งดกิจกรรมประจำ (rules["weekly_skip"])
        self.state = HOME
        self.t_close = 0           # เวลาที่ปิดประตู (เริ่มจับเวลาออก)
        self.close_tup = None      # นาฬิกาตอนปิดประตู (ใช้ตัดสินช่วงเตือน)
        self.maybe_flipped = False # ข้าม NIGHT_RESET ตอนยังไม่อยู่ห้อง -> สถานะอาจกลับด้าน
        self.last_alert = None     # epoch ที่เตือนครั้งล่าสุด
        self.alerted = False       # วันนี้เตือนไปแล้วอย่างน้อย 1 ครั้ง (ไว้แสดง /status)
        self.alerted_windows = []  # ช่วงเตือนที่เตือนไปแล้ววันนี้ (เตือน 1 ครั้งต่อช่วง)
        self.no_alert = False      # สั่งวันนี้ไม่ต้องเตือน
        self.period = None         # รอบวัน (เปลี่ยนเมื่อข้าม NIGHT_RESET)
        self.open_since = None     # epoch ที่ประตูเริ่มเปิด (None = ปิดอยู่)
        self.open_warned = False   # เตือนลืมปิดไปแล้วในการเปิดครั้งนี้
        self.prepped = []          # เช็คลิสต์ล่วงหน้าที่ส่งแล้ววันนี้ ("09:00 วิชา A")

    def __str__(self):
        return "DoorGuard(" + self.state + ", alerted=" + str(self.alerted) + ")"

    # ---------- ส่วนช่วย ----------

    def day_period(self, now):
        # รอบวัน = เวลาเที่ยงคืนของวัน (นับเป็นวินาที) ใช้เทียบว่าข้ามคืนหรือยัง
        # ก่อนเวลารีเซ็ต (เช่น 02:59) ยังนับเป็นรอบของเมื่อวาน
        tup = now[1]
        secs_of_day = tup[3] * 3600 + tup[4] * 60 + tup[5]
        midnight = int(now[0]) - secs_of_day   # int(): epoch จริงเป็นทศนิยม
        if secs_of_day < to_min(self.config["NIGHT_RESET"]) * 60:
            midnight = midnight - 86400
        return midnight

    def appts_on(self, key, weekday):
        # นัดของวัน key + กิจกรรมประจำของวันนั้น (ที่ไม่ได้งด)
        return (list(self.appointments.get(key, []))
                + weekly_on(self.weekly, self.weekly_skip, key, weekday))

    def windows(self, tup):
        # ช่วงเตือนทั้งหมดของวันนั้น เป็น list ของ (นาทีเริ่ม, นาทีจบ)
        before = self.config["BEFORE_CLASS_MIN"]
        result = []

        # 1) คาบแรกของวัน หรือช่วงที่ตั้งไว้สำหรับวันไม่มีเรียน
        day = DAYS[tup[6]]
        starts = []
        for row in self.timetable:
            if row["day"] == day:
                starts.append(row["start"])
        if len(starts) > 0:
            first = to_min(min(starts))
            result.append((first - before, first))
        elif self.config["NO_CLASS_WINDOW"] is not None:
            window = self.config["NO_CLASS_WINDOW"]
            result.append((to_min(window[0]), to_min(window[1])))

        # 2) นัดของวันนั้น: ช่วงละ BEFORE_CLASS_MIN นาทีก่อนนัด
        key = "{:04d}-{:02d}-{:02d}".format(tup[0], tup[1], tup[2])
        for appt in self.appts_on(key, tup[6]):
            start = to_min(appt["time"])
            result.append((start - before, start))

        # 3) นัดหลังเที่ยงคืนของวันถัดไป (เช่น 00:30) -> ช่วงเตือนเริ่มตั้งแต่คืนนี้
        y, m, d = next_day(tup)
        for appt in self.appts_on("{:04d}-{:02d}-{:02d}".format(y, m, d), (tup[6] + 1) % 7):
            start = to_min(appt["time"]) + 24 * 60
            if start - before < 24 * 60:
                result.append((start - before, start))
        return result

    def in_window(self, tup):
        # อยู่ในช่วงเตือนไหน คืน (นาทีเริ่ม, นาทีจบ) หรือ None ถ้าไม่อยู่ในช่วงไหนเลย
        # อยู่หลายช่วงพร้อมกัน -> เลือกช่วงที่ยังไม่เตือน และจบเร็วสุด
        #   เช่น จันทร์เรียน 9:00 + นัด 8:00 ออก 7:40 = ไปนัด (ถ้าเลือกช่วงเรียน
        #   การไปนัดจะกินช่วงเรียน แล้วตอนออกไปเรียนจริงจะไม่เตือน)
        minute = tup[3] * 60 + tup[4]
        found = [w for w in self.windows(tup) if w[0] <= minute <= w[1]]
        if len(found) == 0:
            return None
        fresh = [w for w in found if w not in self.alerted_windows]
        return min(fresh or found, key=lambda w: w[1])

    def events_today(self, tup):
        # สิ่งที่ต้องเตรียมของวันนั้น: คาบแรก + นัดทุกนัด -> list ของ (นาที, "HH:MM", ชื่อ)
        result = []
        day = DAYS[tup[6]]
        rows = [row for row in self.timetable if row["day"] == day]
        if len(rows) > 0:
            first = min(rows, key=lambda row: row["start"])
            result.append((to_min(first["start"]), first["start"], first["subject"]))
        key = "{:04d}-{:02d}-{:02d}".format(tup[0], tup[1], tup[2])
        for appt in self.appts_on(key, tup[6]):
            result.append((to_min(appt["time"]), appt["time"], appt["name"]))
        return result

    def check_prep(self, now):
        # ถึงเวลาส่งเช็คลิสต์ล่วงหน้าไหม: ตั้งแต่ PREP_MIN นาทีก่อนเวลา จนถึงเวลานั้น (ส่งครั้งเดียว)
        # เปิดโปรแกรมช้า (เช่น 8:20 คาบ 9:00) ก็ยังส่งทันที · ออกไปแล้ว = ไม่ต้องส่ง
        before = self.config.get("PREP_MIN", 0)
        if not before or self.no_alert:
            return []
        minute = now[1][3] * 60 + now[1][4]
        actions = []
        for start, text, name in self.events_today(now[1]):
            key = text + " " + name
            if key in self.prepped or not (start - before <= minute < start):
                continue
            self.prepped.append(key)
            if self.state in (HOME, DOOR_OPEN):
                actions.append({"do": "prep", "time": text, "name": name})
        return actions

    def rearm(self, now):
        # ช่วงเตือนที่ยังไม่จบ (ยังไม่ถึงเวลานัด/คาบ) -> เตือนได้อีกเมื่อออกรอบหน้า
        minute = now[1][3] * 60 + now[1][4]
        self.alerted_windows = [w for w in self.alerted_windows if w[1] < minute]

    def check_new_period(self, now):
        # ข้าม NIGHT_RESET -> กลับ HOME และล้างค่า "เตือนแล้ว/ปิดเตือน"
        period = self.day_period(now)
        if self.period is None:    # ครั้งแรกหลังเปิดเครื่อง: แค่จำรอบวัน ไม่ล้างค่า
            self.period = period
        elif period != self.period:
            self.period = period
            self.maybe_flipped = self.state != HOME   # ยังอยู่ข้างนอกตอนรีเซ็ต
            self.state = HOME
            self.alerted = False
            self.alerted_windows = []
            self.no_alert = False
            self.prepped = []
            return [{"do": "new_day"}]
        return []

    def decide_alert(self, now):
        # ออกจริงแล้ว: ต้องเตือนไหม
        if self.no_alert:
            return [{"do": "skip", "why": "สั่งไว้ว่าวันนี้ไม่ต้องเตือน", "code": "no_alert"}]
        # ตัดสินจากเวลาที่ปิดประตู ไม่ใช่ตอนยืนยันว่าออก (+OUT_DELAY)
        # เช่น นัด 7:30 ออก 7:29 -> ยืนยัน 7:31 เลยช่วงไปแล้ว แต่จริง ๆ ออกก่อนนัด
        tup = self.close_tup if self.close_tup is not None else now[1]
        window = self.in_window(tup)
        if window is None:
            if self.config["OUTSIDE_WINDOW"] == "silent_short":
                return [{"do": "short_msg"}]
            return [{"do": "skip", "why": "นอกช่วงเตือน", "code": "outside"}]
        # เตือนเฉพาะการออกครั้งแรกของช่วงนี้ (ALERT_EVERY_EXIT = เตือนทุกครั้ง ใช้ในโหมดเดโม)
        if window in self.alerted_windows and not self.config.get("ALERT_EVERY_EXIT"):
            return [{"do": "skip", "why": "เตือนไปแล้วในช่วงนี้", "code": "window"}]
        if self.last_alert is not None:
            if now[0] - self.last_alert < self.config["COOLDOWN_MIN"] * 60:
                return [{"do": "skip", "why": "ยังไม่ครบ cooldown", "code": "cooldown"}]
        if window not in self.alerted_windows:
            self.alerted_windows.append(window)
        self.alerted = True
        self.last_alert = now[0]
        return [{"do": "checklist"}]

    # ---------- ส่วนหลัก ----------

    def tick(self, now):
        # เรียกทุกวินาที: เช็คข้ามคืน + ครบ OUT_DELAY หรือยัง
        actions = self.check_new_period(now)
        actions += self.check_prep(now)
        # ประตูเปิดค้าง: เตือนครั้งเดียว ไม่ขึ้นกับสถานะหรือช่วงเตือน
        if self.open_since is not None and not self.open_warned:
            secs = now[0] - self.open_since
            if secs >= self.config["OPEN_ALERT_SEC"]:
                self.open_warned = True
                actions.append({"do": "open_long", "secs": secs})
        if self.state == MAYBE_OUT:
            if now[0] - self.t_close >= self.config["OUT_DELAY"]:
                self.state = OUT
                actions += self.decide_alert(now)
        return actions

    def on_door(self, kind, now):
        # kind = "open" หรือ "close"
        actions = self.tick(now)   # จัดการเวลาที่ค้างอยู่ก่อน
        secs = now[0] - self.t_close

        # จำว่าประตูเปิดตั้งแต่เมื่อไร (ใช้เตือนลืมปิด)
        long_open = False          # ปิดหลังจากเปิดค้างจนเตือนไปแล้ว
        if kind == "open":
            if self.open_since is None:
                self.open_since = now[0]
        else:
            long_open = self.open_warned
            open_secs = 0
            if self.open_since is not None:
                open_secs = now[0] - self.open_since
            self.open_since = None
            self.open_warned = False

        if self.state == HOME:
            if kind == "open":
                self.state = DOOR_OPEN
        elif self.state == DOOR_OPEN:
            if kind == "close" and long_open:
                # เปิดค้างนานแล้วค่อยปิด = น่าจะปิดจากในห้อง ไม่ถือว่าออก
                self.state = HOME
                actions.append({"do": "log", "event": "closed_inside", "secs": open_secs})
            elif kind == "close":
                self.state = MAYBE_OUT
                self.t_close = now[0]
                self.close_tup = now[1]
        elif self.state == MAYBE_OUT:
            if kind == "open":     # กลับมาก่อนครบ OUT_DELAY = ออกแป๊บเดียว
                self.state = HOME
                actions.append({"do": "log", "event": "short_trip", "secs": secs})
        elif self.state == OUT:
            if kind == "open":     # กลับมาแล้ว
                self.state = ENTERING
                self.trip_secs = secs
        elif self.state == ENTERING:
            if kind == "close":
                self.state = HOME
                actions.append({"do": "log", "event": "trip", "secs": self.trip_secs})
                # สถานะอาจกลับด้าน (กลับห้องหลังตี 3 แล้วเช้าออกไปเรียน ระบบเห็นเป็น "กลับห้อง")
                # -> ส่งเช็คลิสต์แบบเงียบไว้ก่อน (เฉพาะวันที่รีเซ็ตตอนยังไม่อยู่ห้อง ไม่งั้นกลับห้องปกติก็ได้เช็คลิสต์)
                window = self.in_window(now[1])
                if (self.maybe_flipped and not self.no_alert and window is not None
                        and window not in self.alerted_windows):
                    self.maybe_flipped = False
                    actions.append({"do": "checklist_quiet"})
                # กลับห้องจริง = ออกรอบหน้าคือการออกใหม่
                #   เช่น นัด 7:30 ออกไปซื้อข้าว 6:30 (เตือน) กลับ 7:10 ออกไปนัด 7:20 -> ต้องเตือนอีก
                #   ล้าง cooldown ด้วย (cooldown มีไว้กันเตือนรัวตอนระบบเดาผิด ไม่ใช่ตอนกลับห้องจริง)
                self.rearm(now)
                self.last_alert = None
        return actions

    # ---------- คำสั่งจากแชท ----------

    def set_no_alert(self):
        # "วันนี้ไม่ต้องเตือน"
        self.no_alert = True

    def set_alert_on(self):
        # "เปิดเตือน": ยกเลิกการปิดเตือนวันนี้
        self.no_alert = False

    def still_home(self, now=None):
        # "ยังอยู่ห้อง": บังคับ HOME + บันทึก false_alert
        # เตือนเมื่อกี้ผิด -> ช่วงเตือนที่ยังไม่จบเตือนได้อีกตอนออกจริง (cooldown ยังกันเตือนรัวอยู่)
        if now is not None:
            self.rearm(now)
        self.state = HOME
        return [{"do": "log", "event": "false_alert", "secs": 0}]

    def force_out(self, now):
        # "ออกแล้ว": สถานะกลับด้าน (ระบบคิดว่ากลับห้อง แต่จริง ๆ ออกไปแล้ว) -> บังคับ OUT
        self.state = OUT
        self.t_close = now[0]
        return [{"do": "log", "event": "false_return", "secs": 0}]

    # ---------- จำค่าข้ามการปิด/เปิดโปรแกรม (ฝั่ง pc เก็บลง data/state.json) ----------

    def to_dict(self):
        # ค่าที่ต้องจำของวันนี้ (ไม่จำ state: เปิดเครื่องใหม่เริ่ม HOME ตามสเปก)
        windows = []
        for window in self.alerted_windows:
            windows.append([window[0], window[1]])
        return {"period": self.period, "alerted": self.alerted,
                "alerted_windows": windows, "no_alert": self.no_alert,
                "last_alert": self.last_alert, "maybe_flipped": self.maybe_flipped,
                "prepped": self.prepped}

    def load_dict(self, data, now):
        # โหลดค่าที่จำไว้ เฉพาะถ้าเป็นรอบวันเดียวกัน คืน True ถ้าโหลด
        if data.get("period") != self.day_period(now):
            return False
        self.period = data["period"]
        self.alerted = data.get("alerted", False)
        self.alerted_windows = []
        for window in data.get("alerted_windows", []):
            self.alerted_windows.append((window[0], window[1]))   # json เก็บ tuple เป็น list
        self.no_alert = data.get("no_alert", False)
        self.last_alert = data.get("last_alert")
        self.maybe_flipped = data.get("maybe_flipped", False)
        self.prepped = list(data.get("prepped", []))
        return True
