# Door Buddy บนบอร์ด ESP32 (MicroPython) — B4 ขั้นที่ 1: ทำงานเองโดยไม่ต้องเปิดคอม
# อัปโหลดด้วย tools/upload_board.py · main.py บนบอร์ด: net.start() -> import app -> app.main()
#
# ไฟล์บนบอร์ดที่ต้องมี: main.py, app, net, bdate, core/, secrets.json (WIFI + Telegram),
#   config.json, rules.json, timetable.json, activities.json
# ไฟล์ที่บอร์ดเขียนเอง: rules.json (เมื่อสั่งแก้), state.json, events.csv
#
# ต่างจากฝั่งคอม: ไม่มี thread -> ประตูใช้ interrupt จดเวลาที่ขาเปลี่ยนไว้เอง (รอเน็ตก็ไม่หลุด)
#   และเน็ตใช้ net.py (ค้างสาย HTTPS ไว้สายเดียว) · ข้อความบนจอคอมเป็นภาษาอังกฤษ
import gc
import json
import os
import time
from array import array

import machine
import ntptime
from machine import Pin

import bdate
import net
from core.checklist import build_checklist
from core.commands import parse_command
from core.guard import DoorGuard

DOOR_PIN = 32
DEBOUNCE_MS = 500
POLL_MS = 3000              # ถาม Telegram ทุก 3 วิ
MAX_NET_FAILS = 2           # ต่อ HTTPS ใหม่ไม่ได้เพราะหน่วยความจำ ติดกันเท่านี้ -> รีสตาร์ทบอร์ด
OFFLINE_REBOOT_MS = 2 * 60 * 1000   # WiFi หลุดนานเกินนี้ -> รีสตาร์ทบอร์ด (เริ่ม WiFi ใหม่หมด)
MAX_TG_ERRORS = 6           # เรียก Telegram พลาดติดกันเท่านี้ (~2 นาที) -> รีสตาร์ทบอร์ด
WEATHER_MS = 60 * 60 * 1000
NTP_MS = 24 * 60 * 60 * 1000
TZ = 7 * 3600               # เวลาไทย UTC+7
MAX_EVENTS_BYTES = 100000   # events.csv ใหญ่เกินนี้ -> ย้ายเป็น events_old.csv แล้วเริ่มใหม่
STATE_TH = {"HOME": "อยู่ห้อง", "DOOR_OPEN": "ประตูเปิดอยู่",
            "MAYBE_OUT": "เพิ่งปิดประตู กำลังรอดูว่าออกไปไหม",
            "OUT": "ออกไปข้างนอก", "ENTERING": "เพิ่งเปิดประตูเข้ามา"}
MAIN_BUTTONS = [["เช็คลิสต์", "นัด"], ["ของ", "อื่น ๆ"]]
KEYBOARD = {"keyboard": MAIN_BUTTONS, "resize_keyboard": True, "is_persistent": True}
HELP = """วิธีใช้ (บอร์ด)
(ปุ่มด้านล่าง: เช็คลิสต์ / นัด / ของ / อื่น ๆ)

# พิมพ์ได้
- พรุ่งนี้ ร่ม / 24/10 ร่ม = เพิ่มของเฉพาะวัน
- ลืม ร่ม / เพิ่ม ร่ม ทุกวัน = เพิ่มของพกทุกวัน · ลบ ร่ม = ลบ
- วันนี้ไม่ต้องเตือน / พรุ่งนี้ไม่ต้องเตือน / เปิดเตือน
- ยังอยู่ห้อง / ออกแล้ว = แก้เมื่อระบบเดาผิด
- /list พรุ่งนี้ · /status · เปิดเดโม / ปิดเดโม
(เมนูปุ่มซ้อน + เพิ่มนัดมีเวลา ใช้บนคอมไปก่อน)"""


# ---------- ไฟล์ ----------

def load(name, default=None):
    try:
        with open(name) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(name, data):
    try:
        with open(name, "w") as f:
            json.dump(data, f)
    except OSError as e:
        print("save error:", name, e)


def log(event, secs=0, detail=""):
    # บันทึกลง events.csv (คอลัมน์เดียวกับฝั่งคอม เอาไปใช้กับ analyze.py ได้)
    t = now()[1]
    row = "{:04d}-{:02d}-{:02d},{:02d}:{:02d}:{:02d},{},{},{}\n".format(
        t[0], t[1], t[2], t[3], t[4], t[5], event, int(secs), detail.replace(",", " "))
    try:
        try:
            size = os.stat("events.csv")[6]
        except OSError:
            size = -1
        if size > MAX_EVENTS_BYTES:
            try:
                os.remove("events_old.csv")
            except OSError:
                pass
            os.rename("events.csv", "events_old.csv")
            size = -1
        with open("events.csv", "a") as f:
            if size < 0:
                f.write("date,time,event,secs,detail\n")
            f.write(row)
    except OSError as e:
        print("log error:", e)
    print("log:", event, secs, detail)


# ---------- เวลา ----------

def now(epoch=None):
    # now แบบที่ core ต้องการ · epoch = เวลาเหตุการณ์ (เช่น เวลาที่ประตูขยับจริง)
    if epoch is None:
        epoch = time.time() + TZ
    return (epoch, time.localtime(int(epoch))[:7])


def today_key():
    t = now()[1]
    return bdate.make_key(t[0], t[1], t[2])


def hm():
    t = now()[1]
    return "{:02d}:{:02d}".format(t[3], t[4])


# ---------- เน็ต ----------

def api(method, data):
    # เรียก Telegram (ผ่านสายที่ค้างไว้ใน net.py) · คืน dict หรือ None ถ้าเน็ตหลุด/timeout (ไม่ล้ม)
    gc.collect()
    t0 = time.ticks_ms()
    print("->", method)                          # ไล่ปัญหา: เห็นว่าค้างตรงไหน
    global tg_errors
    try:
        result = net.call(method, data)
        net_ok()
        tg_errors = 0
        print("<-", method, time.ticks_diff(time.ticks_ms(), t0), "ms")
        if not result.get("ok", False):          # Telegram ไม่รับ: บอกเหตุผล (ไม่ทิ้งเงียบ ๆ)
            print("telegram said:", result.get("description"))
        return result
    except Exception as e:
        net_fail(method, e)
        # พลาดแบบไหนก็ตาม (timeout ฯลฯ) ติดกันนาน ๆ ทั้งที่ WiFi ต่ออยู่ -> รีสตาร์ท
        # ทดสอบแล้ว: ต่อ HTTPS แล้ว timeout กลางทาง (เน็ตยังไม่มา) หน่วยความจำส่วน HTTPS ไม่คืน
        #   หลังจากนั้น timeout ตลอดแม้เน็ตกลับมาแล้ว -> รีสตาร์ทให้หน่วยความจำกลับมาเต็ม
        tg_errors += 1
        if tg_errors >= MAX_TG_ERRORS:
            reboot_for_net("telegram")
        return None
    finally:
        gc.collect()


net_fails = 0
tg_errors = 0           # เรียก Telegram พลาดติดกันกี่ครั้ง (ทุกแบบ)


def net_ok():
    global net_fails
    net_fails = 0


def net_fail(what, e):
    # ต่อเน็ตพลาด · นับเฉพาะพลาดเพราะหน่วยความจำไม่พอ (เน็ตหลุดจริง รีสตาร์ทก็ไม่ช่วย)
    # ทดสอบแล้ว: สายหลุดหลังรันไปสักพัก หน่วยความจำส่วน HTTPS แตกเป็นชิ้นจนต่อใหม่ไม่ได้
    # ติดกันถึง MAX_NET_FAILS = รีสตาร์ทบอร์ด (หน่วยความจำกลับมาเต็ม ต่อได้ทันที)
    global net_fails
    if "ALLOC" in str(e) or isinstance(e, MemoryError):
        net_fails += 1
    print("net error:", what, e, "| fails:", net_fails, "|", net.mem_info())
    if net_fails >= MAX_NET_FAILS:
        reboot_for_net("memory")


def reboot_for_net(reason):
    # reason: "memory" = ต่อ HTTPS ใหม่ไม่ได้ · "wifi" = WiFi หลุดนานเกิน OFFLINE_REBOOT_MS
    # เก็บของที่ต้องไม่หายลงไฟล์ก่อนรีสตาร์ท (state.json บันทึกทุกวิอยู่แล้ว)
    #   outbox.json   = ข้อความที่ยังส่งไม่ออก -> เปิดมาใหม่ส่งต่อ
    #   netreset.json = รีสตาร์ทเพราะเน็ตกี่ครั้งแล้ว + โหมดเดโม -> เปิดมาใหม่ไม่ส่ง "เริ่มทำงาน" ซ้ำ
    save("outbox.json", outbox[-10:])
    save("netreset.json", {"count": net_resets + 1, "demo": demo})
    log("reboot", 0, "net " + reason)
    print("net:", reason, "-> reboot")
    time.sleep(1)
    machine.reset()


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_html(text):
    # แบบเดียวกับฝั่งคอม: บรรทัดแรกตัวหนา · "# " ตัวหนา · "- " เป็นจุด · (…) ตัวเอียง
    lines = []
    for i, line in enumerate(text.split("\n")):
        safe = escape(line)
        if i == 0 and safe.strip():
            safe = "<b>" + safe + "</b>"
        elif safe.startswith("# "):
            safe = "<b>" + safe[2:] + "</b>"
        elif safe.startswith("- "):
            safe = "• " + safe[2:]
        elif safe.startswith("(") and safe.endswith(")"):
            safe = "<i>" + safe + "</i>"
        lines.append(safe)
    return "\n".join(lines)


def send(text, buttons=None, silent=False):
    # ส่งข้อความ (ไม่สำเร็จ = เก็บคิวไว้ส่งรอบหน้า) · buttons = ปุ่มใต้ข้อความ
    markup = KEYBOARD
    if buttons:
        markup = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row]
                                      for row in buttons]}
    data = {"chat_id": CHAT, "text": format_html(text)[:3800], "parse_mode": "HTML",
            "disable_notification": silent, "reply_markup": markup}
    print(text)
    outbox.append(data)
    flush()


def flush():
    while outbox:
        result = api("sendMessage", outbox[0])
        if result is None:
            return                          # เน็ตหลุด: รอบหน้าค่อยส่ง
        outbox.pop(0)                       # ส่งได้ / Telegram ไม่รับ = เอาออก (ไม่ค้างคิว)


# ---------- ข้อมูล ----------

def upcoming(key):
    appts = sorted(rules.get("appointments", {}).get(key, []), key=lambda a: a["time"])
    if key == today_key():
        return [a for a in appts if a["time"] > hm()]
    return appts


def items_for(key):
    r = dict(rules)
    r["appointments"] = dict(rules.get("appointments", {}))
    r["appointments"][key] = upcoming(key)
    weather = None if rain is None or key != today_key() else {"rain_prob": rain}
    return build_checklist(r, timetable, weather, bdate.date_tuple(key), config["RAIN_PROB"])


def item_lines(items):
    return [str(i + 1) + ". " + items[i].name + "  (" + items[i].source + ")"
            for i in range(len(items))]


def checklist_text(key):
    lines = []
    appts = sorted(rules.get("appointments", {}).get(key, []), key=lambda a: a["time"])
    if appts:
        lines.append("# นัด")
        left = upcoming(key)
        for a in appts:
            lines.append("- " + a["time"] + "  " + a["name"] + ("" if a in left else "  (ผ่านแล้ว)"))
        lines.append("")
    if key == today_key():
        lines.append("# อากาศ")
        lines.append("- โอกาสฝน " + str(rain) + "% วันนี้" if rain is not None
                     else "(ยังไม่มีข้อมูลอากาศ)")
        lines.append("")
    items = items_for(key)
    if not items:
        lines.append("(ไม่มีของต้องพก)")
    else:
        lines.append("# อย่าลืม")
        lines += item_lines(items)
    return "\n".join(lines)


def clean_old_dates():
    # ลบนัด/ของเฉพาะวัน/วันปิดเตือน ที่ผ่านไปแล้ว
    today = today_key()
    changed = False
    for section in ["by_date", "appointments"]:
        for key in list(rules.get(section, {}).keys()):
            if key < today:
                del rules[section][key]
                changed = True
    old = [k for k in rules.get("no_alert_dates", []) if k < today]
    for k in old:
        rules["no_alert_dates"].remove(k)
        changed = True
    if changed:
        save("rules.json", rules)


def apply_no_alert_dates():
    if today_key() in rules.get("no_alert_dates", []):
        guard.set_no_alert()


def set_demo(on):
    # โหมดเดโม: รอ 10 วิ เตือนทุกครั้งที่ออก (เว้น 1 นาที) เตือนได้ทุกเวลา เปิดค้าง 10 วิ
    global demo
    demo = on
    config.clear()
    config.update(base_config)
    if on:
        config.update({"OUT_DELAY": 10, "COOLDOWN_MIN": 1, "OPEN_ALERT_SEC": 10,
                       "NO_CLASS_WINDOW": ["00:00", "23:59"], "ALERT_EVERY_EXIT": True})
    guard.timetable = [] if on else timetable
    guard.alerted = False
    guard.alerted_windows = []
    guard.last_alert = None
    del alerted_items[:]


# ---------- ทำตาม action จาก DoorGuard ----------

def handle(actions):
    global alerted_items
    for a in actions:
        do = a["do"]
        if do == "checklist":
            send("🚪 ออกจากห้องแล้ว " + hm() + "\n" + checklist_text(today_key()),
                 buttons=[[("ยังไม่ได้ออก", "o:home")]])
            alerted_items = [i.name for i in items_for(today_key())]
            log("alert")
        elif do == "checklist_quiet":
            send("🏠 เพิ่งกลับห้อง " + hm() + "\n(ถ้าจริง ๆ กำลังจะออกไป นี่คือของที่ต้องพก)\n\n"
                 + checklist_text(today_key()), buttons=[[("จริง ๆ กำลังออก", "o:out")]],
                 silent=True)
            log("alert_quiet")
        elif do == "short_msg":
            send("🚪 ออกจากห้องแล้ว " + hm() + "\n(กดปุ่ม \"เช็คลิสต์\" ถ้าอยากดูของ)", silent=True)
            log("alert_short")
        elif do == "open_long":
            minutes = int(a["secs"]) // 60
            send("⚠️ ประตูเปิดค้างมา " + (str(minutes) + " นาที" if minutes else
                                         str(int(a["secs"])) + " วินาที") + "\nลืมปิดหรือเปล่า")
            log("open_long", a["secs"])
        elif do == "skip":
            new = []
            if a.get("code") in ["window", "cooldown"]:
                new = [i for i in items_for(today_key()) if i.name not in alerted_items]
            if new:
                send("🚪 ออกจากห้องแล้ว " + hm() + "\n(เตือนไปแล้วรอบหนึ่ง นี่คือของที่เพิ่มมา)\n\n"
                     + "# ของที่เพิ่มมา\n" + "\n".join(item_lines(new)),
                     buttons=[[("ยังไม่ได้ออก", "o:home")]])
                alerted_items += [i.name for i in new]
                log("alert_new", 0, " ".join(i.name for i in new))
            else:
                log("skip", 0, a.get("code", ""))
        elif do == "log":
            log(a["event"], a["secs"])
        elif do == "new_day":
            del alerted_items[:]
            if demo:
                set_demo(False)
                send("กลับเป็นโหมดใช้งานจริงแล้ว (รีเซ็ตประจำวัน)")
            clean_old_dates()
            apply_no_alert_dates()


# ---------- คำสั่งแชท ----------

def status_text():
    s = ("สถานะระบบ (บอร์ด)\n- โหมด: " + ("เดโม" if demo else "ใช้งานจริง")
         + "\n- ตอนนี้: " + STATE_TH.get(guard.state, guard.state)
         + "\n- ประตู: " + ("เปิด" if stable else "ปิด")
         + "\n- เตือนวันนี้ไปแล้ว: " + ("ใช่" if guard.alerted else "ยัง")
         + "\n- ปิดเตือนวันนี้: " + ("ใช่" if guard.no_alert else "ไม่")
         + "\n- อากาศ: " + ("ฝน " + str(rain) + "%" if rain is not None else "ไม่มีข้อมูล")
         + "\n- หน่วยความจำเหลือ: " + str(gc.mem_free()) + " ไบต์"
         + "\n- รีสตาร์ทเองเพราะเน็ต: " + str(net_resets) + " ครั้ง"
         + "\n- ทำงานมา: " + str(time.ticks_diff(time.ticks_ms(), start) // 60000) + " นาที")
    return s


def items_text():
    lines = ["🎒 ของที่ต้องพก", "", "# พกทุกวัน"]
    lines += ["- " + n for n in rules.get("always", [])] or ["(ไม่มี)"]
    lines += ["", "# เฉพาะวัน"]
    days = sorted(set(rules.get("by_date", {})) | set(rules.get("appointments", {})))
    shown = False
    for key in days:
        parts = []
        if rules.get("by_date", {}).get(key):
            parts.append("ทั้งวัน: " + ", ".join(rules["by_date"][key]))
        for a in rules.get("appointments", {}).get(key, []):
            if a.get("items"):
                parts.append(a["time"] + " " + a["name"] + ": " + ", ".join(a["items"]))
        if parts:
            shown = True
            lines.append("- " + bdate.short_day(key, today_key()))
            lines += ["   " + p for p in parts]
    if not shown:
        lines.append("(ไม่มี)")
    return "\n".join(lines)


def appointments_text():
    lines = []
    for key in sorted(rules.get("appointments", {})):
        for a in sorted(rules["appointments"][key], key=lambda x: x["time"]):
            lines.append("- " + bdate.short_day(key, today_key()) + "  " + a["time"] + "  " + a["name"])
    return "📅 นัดทั้งหมด\n" + "\n".join(lines) if lines else "📅 ยังไม่มีนัด"


def add_unique(lst, names):
    added = [n for n in names if n not in lst]
    lst += added
    return added


def run_command(text):
    # ข้อความแชท -> ข้อความตอบกลับ (ใช้ core/commands.py ตัวเดียวกับคอม)
    text = text.strip()
    today = today_key()
    if text == "เช็คลิสต์":
        return "📋 เช็คลิสต์ " + bdate.short_day(today, today) + "\n" + checklist_text(today)
    if text == "นัด":
        return appointments_text()
    if text == "ของ":
        return items_text()
    if text == "อื่น ๆ":
        return status_text() + "\n\n" + HELP
    if text == "เปิดเดโม":
        set_demo(True)
        return "เปิดโหมดเดโมแล้ว\n(รอ 10 วิ · เตือนทุกครั้งที่ออก · ตี 3 กลับเป็นใช้งานจริงเอง)"
    if text == "ปิดเดโม":
        set_demo(False)
        return "กลับเป็นโหมดใช้งานจริงแล้ว"
    key, rest = bdate.find_date(text, today)
    cmd = parse_command(text, (key, rest) if key else None, activities, None)
    print("cmd:", cmd)
    c = cmd["cmd"]
    if c == "help":
        return HELP
    if c == "status":
        return status_text()
    if c == "list":
        day = cmd["date"] or today
        return "📋 เช็คลิสต์ " + bdate.short_day(day, today) + "\n" + checklist_text(day)
    if c == "bad_date":
        return "ไม่เข้าใจวันที่\n(ลองแบบนี้: /list พรุ่งนี้, /list 5/11)"
    if c == "no_alert":
        day = cmd.get("date")
        if day is None or day == today:
            guard.set_no_alert()
            return "🔕 โอเค วันนี้จะไม่เตือน\n(พรุ่งนี้เตือนตามปกติ)"
        add_unique(rules.setdefault("no_alert_dates", []), [day])
        save("rules.json", rules)
        return "🔕 โอเค วัน " + bdate.short_day(day) + " จะไม่เตือน"
    if c == "alert_on":
        guard.set_alert_on()
        if today in rules.get("no_alert_dates", []):
            rules["no_alert_dates"].remove(today)
            save("rules.json", rules)
        return "เปิดเตือนกลับแล้ว"
    if c == "still_home":
        handle(guard.still_home())
        return "แก้แล้ว: ยังอยู่ห้อง"
    if c == "out_now":
        handle(guard.force_out(now()))
        return "แก้แล้ว: ออกไปข้างนอก"
    if c in ["forget", "add_always"]:
        if c == "forget":
            log("forget", 0, cmd["item"])
        if add_unique(rules.setdefault("always", []), [cmd["item"]]):
            save("rules.json", rules)
            return "เพิ่ม " + cmd["item"] + " ในของที่พกทุกวันแล้ว"
        return cmd["item"] + " อยู่ในของที่พกทุกวันอยู่แล้ว"
    if c == "remove":
        if cmd["item"] in rules.get("always", []):
            rules["always"].remove(cmd["item"])
            save("rules.json", rules)
            return "ลบ " + cmd["item"] + " ออกจากของที่พกทุกวันแล้ว"
        return "ไม่เจอ " + cmd["item"] + " ในของที่พกทุกวัน"
    if c in ["add_item", "add_activity"]:
        add_unique(rules.setdefault("by_date", {}).setdefault(cmd["date"], []), cmd["items"])
        save("rules.json", rules)
        return "เพิ่มของที่ต้องพกวัน " + bdate.short_day(cmd["date"]) + " แล้ว: " + ", ".join(cmd["items"])
    if c == "list_appts":
        return appointments_text()
    if c == "remove_appt":
        if cmd["date"] and rules.get("appointments", {}).pop(cmd["date"], None) is not None:
            save("rules.json", rules)
            return "ลบนัดวัน " + bdate.short_day(cmd["date"]) + " แล้ว"
        return "ไม่เจอนัดที่จะลบ"
    return "ไม่เข้าใจคำสั่ง\n(กดปุ่ม อื่น ๆ เพื่อดูวิธีใช้)"


def on_button(press):
    # ปุ่มใต้ข้อความเตือน (ยังไม่ได้ออก / จริง ๆ กำลังออก) · ปุ่มอื่นเป็นเมนูของคอม บอร์ดยังไม่รองรับ
    api("answerCallbackQuery", {"callback_query_id": press["id"]})
    data = press.get("data", "")
    if data == "o:home":
        handle(guard.still_home())
        send("แก้แล้ว: ยังอยู่ห้อง")
    elif data == "o:out":
        handle(guard.force_out(now()))
        send("แก้แล้ว: ออกไปข้างนอก")
    else:
        send("ปุ่มนี้เป็นเมนูของโปรแกรมบนคอม บอร์ดยังไม่รองรับ\n(กดปุ่มด้านล่าง หรือพิมพ์คำสั่งแทน)")


def poll():
    # รับข้อความใหม่ (เฉพาะ chat id ของผู้ใช้)
    global offset
    result = api("getUpdates", {"timeout": 0, "limit": 5, "offset": offset})
    if not result:
        return
    for u in result.get("result", []):
        offset = u["update_id"] + 1
        if "callback_query" in u:
            press = u["callback_query"]
            if str(press.get("message", {}).get("chat", {}).get("id", "")) == str(CHAT):
                on_button(press)
            continue
        msg = u.get("message", {})
        if str(msg.get("chat", {}).get("id", "")) == str(CHAT) and "text" in msg:
            print("chat:", msg["text"])
            send(run_command(msg["text"]))


def skip_old():
    # ทิ้งข้อความที่ค้างในแชทก่อนเริ่ม (ไม่ทำคำสั่งเก่า)
    result = api("getUpdates", {"timeout": 0, "offset": -1})
    if result and result.get("result"):
        return result["result"][-1]["update_id"] + 1
    return 0


def fetch_rain():
    # โอกาสฝนสูงสุดตั้งแต่ชั่วโมงนี้ไปอีก RAIN_HOURS ชม. · ไม่ได้ = None
    path = ("/v1/forecast?latitude=" + str(config["LAT"])
            + "&longitude=" + str(config["LON"])
            + "&hourly=precipitation_probability&timezone=Asia%2FBangkok&forecast_days=2")
    gc.collect()
    t0 = time.ticks_ms()
    print("-> weather")
    try:
        probs = net.get_http("api.open-meteo.com", path)["hourly"]["precipitation_probability"]
        net_ok()
        print("<- weather", time.ticks_diff(time.ticks_ms(), t0), "ms")
        hour = now()[1][3]
        window = [p for p in probs[hour:hour + config["RAIN_HOURS"]] if p is not None]
        return max(window) if window else None
    except Exception as e:
        net_fail("weather", e)
        return None
    finally:
        gc.collect()


# ---------- ประตู (interrupt) ----------
# ทุกครั้งที่ขาเปลี่ยน ชิปเรียก on_edge ทันที (hard interrupt: แม้โปรแกรมหลักกำลังรอเน็ต) -> จดเวลาไว้
# โปรแกรมหลักค่อยมาไล่กันสั่นทีหลัง โดยใช้เวลาที่จดไว้ (เวลาจริงที่ประตูขยับ)
# hard interrupt ห้ามจองหน่วยความจำใหม่ -> เตรียมที่เก็บไว้ล่วงหน้า (array) แล้วแค่เขียนทับ

EDGE_MAX = 64
edge_t = array("i", [0] * EDGE_MAX)     # เวลา (ticks_ms) ที่ขาเปลี่ยน
edge_v = bytearray(EDGE_MAX)            # ค่าขาหลังเปลี่ยน (0 = ปิด, 1 = เปิด)
edge_n = 0                              # จดไปแล้วกี่ช่อง


def on_edge(pin):
    global edge_n
    if edge_n < EDGE_MAX:
        edge_t[edge_n] = time.ticks_ms()
        edge_v[edge_n] = pin.value()
        edge_n += 1


def commit(t):
    # ค่าคงที่นานพอแล้ว (ไม่ใช่สั่น) -> นับว่าประตูเปลี่ยนจริง ส่งให้ guard พร้อมเวลาจริง
    global stable
    if candidate != stable and time.ticks_diff(t, since) >= DEBOUNCE_MS:
        stable = candidate
        kind = "open" if stable else "close"           # ยืนยันขั้วแล้วใน B2: เปิด = 1
        ago = time.ticks_diff(time.ticks_ms(), since) / 1000
        when = now(time.time() + TZ - ago)
        print("door", kind, "(", ago, "s ago )")
        log("door_" + kind)
        handle(guard.on_door(kind, when))


def process_door():
    global candidate, since, edge_n
    irq = machine.disable_irq()             # กัน interrupt เขียนทับระหว่างคัดลอก
    batch = [(edge_t[i], edge_v[i]) for i in range(edge_n)]
    edge_n = 0
    machine.enable_irq(irq)
    for t, v in batch:
        commit(t)                       # ค่าเดิมนิ่งพอก่อนขอบนี้ไหม
        if v != candidate:
            candidate = v
            since = t
    commit(time.ticks_ms())


# ---------- เริ่มทำงาน ----------

base_config = load("config.json", {})
config = dict(base_config)
rules = load("rules.json", {})
timetable = load("timetable.json", [])
activities = load("activities.json", {})
CHAT = load("secrets.json", {}).get("TELEGRAM_CHAT_ID", "")   # token อยู่ใน net.py
outbox = []
alerted_items = []
demo = False
net_resets = 0          # รีสตาร์ทเองเพราะเน็ตกี่ครั้งตั้งแต่เปิดไฟ (ดูใน /status)
rain = None
start = time.ticks_ms()
guard = DoorGuard(config, timetable, rules.setdefault("appointments", {}))
stable = candidate = 0
since = 0
offset = 0
# import app = แค่โหลดโปรแกรม (ยังไม่ต่อเน็ต/ยังไม่เริ่ม) -> memcheck.py วัดหน่วยความจำได้
# เริ่มทำงานจริงด้วย app.main() (main.py บนบอร์ดเรียกให้ตอนเปิดไฟ)


def main():
    global alerted_items, stable, candidate, since, offset, rain, net_resets
    wlan = net.start()                          # main.py ต่อไว้ให้แล้ว (ถ้ารันเองจะต่อตรงนี้)
    try:
        ntptime.settime()
    except Exception as e:
        print("ntp error:", e)
    print("time:", now()[1])

    state = load("state.json")                  # โหลดหลังตั้งเวลาแล้ว (ต้องรู้ว่าวันนี้วันไหน)
    if state and guard.load_dict(state, now()):
        alerted_items = state.get("alerted_items", [])
        print("state loaded")
    clean_old_dates()
    apply_no_alert_dates()

    door = Pin(DOOR_PIN, Pin.IN, Pin.PULL_UP)
    stable = door.value()
    candidate = stable
    since = time.ticks_ms()
    try:
        door.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=on_edge, hard=True)
        print("door irq: hard")
    except (TypeError, ValueError):             # บอร์ด/เฟิร์มแวร์ไม่รองรับ hard -> ใช้แบบปกติ
        door.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=on_edge)
        print("door irq: soft")

    offset = skip_old()
    rain = fetch_rain()
    reset_info = load("netreset.json")          # มี = เพิ่งรีสตาร์ทเองเพราะเน็ต (ไม่ใช่เปิดไฟใหม่)
    outbox.extend(load("outbox.json", []))
    for name in ("netreset.json", "outbox.json"):
        try:
            os.remove(name)
        except OSError:
            pass
    if reset_info:
        net_resets = reset_info.get("count", 0)
        if reset_info.get("demo"):
            set_demo(True)
        print("net reboot #", net_resets, "| resend", len(outbox))
        flush()
    else:
        send("✅ Door Buddy (บอร์ด) เริ่มทำงาน\n(หน่วยความจำเหลือ " + str(gc.mem_free()) + " ไบต์)")
    last = {"tick": 0, "poll": 0, "weather": time.ticks_ms(), "ntp": time.ticks_ms(),
            "online": time.ticks_ms()}
    saved = None

    while True:
        try:
            t0 = time.ticks_ms()
            process_door()
            if time.ticks_diff(t0, last["tick"]) >= 1000:
                last["tick"] = t0
                handle(guard.tick(now()))
                if not demo:                               # จำค่าข้ามการรีสตาร์ท (โหมดจริง)
                    data = guard.to_dict()
                    data["alerted_items"] = alerted_items
                    if data != saved:
                        save("state.json", data)
                        saved = data
            if time.ticks_diff(t0, last["poll"]) >= POLL_MS:
                last["poll"] = t0
                if not wlan.isconnected():
                    net.close()                            # สาย HTTPS เดิมตายไปพร้อม WiFi แล้ว
                    wlan = net.wifi()
                if wlan.isconnected():
                    last["online"] = t0
                    flush()
                    poll()
                elif time.ticks_diff(t0, last["online"]) >= OFFLINE_REBOOT_MS:
                    reboot_for_net("wifi")
            if time.ticks_diff(t0, last["weather"]) >= WEATHER_MS:
                last["weather"] = t0
                rain = fetch_rain()
                if rain is None:                           # ดึงไม่ได้ -> ลองใหม่ใน 10 นาที
                    last["weather"] = t0 - WEATHER_MS + 10 * 60 * 1000
            if time.ticks_diff(t0, last["ntp"]) >= NTP_MS:  # ตั้งนาฬิกาใหม่ทุกวัน (กันเวลาเพี้ยน)
                last["ntp"] = t0
                try:
                    ntptime.settime()
                except Exception:
                    pass
            time.sleep_ms(20)
        except KeyboardInterrupt:
            raise                                          # Ctrl+C จากคอม = หยุดจริง
        except Exception as e:
            # กันล้มทั้งระบบ: error ตรงไหนก็บันทึกแล้วทำงานต่อ
            print("error:", e)
            log("error", 0, str(e)[:60])
            time.sleep(1)
