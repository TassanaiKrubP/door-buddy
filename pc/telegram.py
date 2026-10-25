# ส่ง/รับข้อความ Telegram ด้วย HTTP ตรง
# ใช้ urllib ที่มากับ Python (ไม่ต้องติดตั้งไลบรารีบอท)
# ห้ามพิมพ์ token ลงจอหรือ log
#
# TelegramWorker ทำงานใน thread แยก (ทำงานขนานกับลูปหลัก)
# เน็ตช้า/หลุด -> รอเฉพาะใน thread นี้ ลูปหลักที่ดูประตูไม่ค้าง
#
# ปุ่ม 2 แบบ
#   ปุ่มล่าง (reply keyboard)  : อยู่ใต้ช่องพิมพ์ตลอด กดแล้วเหมือนพิมพ์ข้อความนั้น
#   ปุ่มติดข้อความ (inline)    : อยู่ใต้ข้อความ กดแล้วส่ง "data" สั้น ๆ กลับมา (ไม่เป็นข้อความในแชท)
#   buttons = list ของแถว แต่ละแถว = list ของ (ข้อความบนปุ่ม, data)
import html
import json
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot"

# ปุ่มล่าง 5 ปุ่ม (กดแล้วบอทส่งเมนูชั้นถัดไปเป็นปุ่มติดข้อความ)
# ปุ่มล่างหาย (เผลอกดซ่อน) -> พิมพ์ "เมนู" หรือกดปุ่ม Menu ข้างช่องพิมพ์แล้วเลือก /menu
MAIN_BUTTONS = [["เช็คลิสต์", "นัด"],
                ["ประจำสัปดาห์", "ของ"],
                ["อื่น ๆ"]]
KEYBOARD = json.dumps({
    "keyboard": MAIN_BUTTONS,
    "resize_keyboard": True,    # ปุ่มขนาดพอดี ไม่เต็มจอ
    "is_persistent": True,      # ปุ่มแสดงค้างไว้ตลอด
}, ensure_ascii=False)

# ขีดจำกัดของ Telegram (เกิน = Telegram ไม่รับ บอทจะเงียบไปเฉย ๆ) -> ตัดให้พอดีก่อนส่ง
# รายการคำสั่งในปุ่ม Menu ข้างช่องพิมพ์ของ Telegram (มีให้กดเสมอ แม้ปุ่มล่างหาย)
COMMANDS = [{"command": "menu", "description": "เรียกปุ่มเมนูด้านล่างกลับมา"},
            {"command": "list", "description": "ดูเช็คลิสต์วันนี้"},
            {"command": "status", "description": "สถานะระบบ"},
            {"command": "help", "description": "วิธีใช้"}]

MAX_TEXT = 3800       # Telegram รับได้ 4096 ตัวอักษร เผื่อที่ให้ตอนแปลงเป็น HTML
MAX_BUTTONS = 90       # ปุ่มติดข้อความต่อ 1 ข้อความ (Telegram รับได้ประมาณ 100)

# ผลของการเรียก API
OK = "ok"          # สำเร็จ
BAD = "bad"        # Telegram ปฏิเสธ (เช่น ข้อความยาวเกิน, แก้ข้อความแล้วเหมือนเดิม) -> ไม่ต้องลองใหม่
NET = "net"        # เน็ตหลุด / timeout -> ลองใหม่ภายหลัง


def call(token, method, params, timeout=5):
    # เรียก Telegram Bot API แล้วคืนผลเป็น dict
    data = urllib.parse.urlencode(params).encode("utf-8")
    with urllib.request.urlopen(API + token + "/" + method, data=data,
                                timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post(token, method, params):
    # เรียก API แล้วคืน OK / BAD / NET
    try:
        if call(token, method, params).get("ok", False):
            return OK
        return BAD
    except urllib.error.HTTPError:      # Telegram ตอบกลับมาว่าผิด (4xx) = เน็ตปกติ แต่คำขอผิด
        return BAD
    except Exception:                   # ต่อไม่ได้ / timeout
        return NET


def shorten(text):
    # ข้อความยาวเกิน -> ตัดที่ท้ายบรรทัด แล้วบอกว่าตัดไปกี่บรรทัด
    if len(text) <= MAX_TEXT:
        return text
    lines = text.split("\n")
    kept = []
    size = 0
    for line in lines:
        if size + len(line) + 1 > MAX_TEXT - 60:
            break
        kept.append(line)
        size += len(line) + 1
    return "\n".join(kept) + "\n(และอีก " + str(len(lines) - len(kept)) + " บรรทัด ยาวเกินที่ส่งได้)"


def limit_buttons(buttons):
    # ปุ่มเกิน MAX_BUTTONS -> ตัดแถวกลาง ๆ ทิ้ง แต่เก็บแถวสุดท้ายไว้ (มักเป็นปุ่ม กลับ / ยกเลิก)
    if not buttons or sum(len(row) for row in buttons) <= MAX_BUTTONS:
        return buttons
    last = buttons[-1]
    kept = []
    count = len(last)
    for row in buttons[:-1]:
        if count + len(row) > MAX_BUTTONS:
            break
        kept.append(row)
        count += len(row)
    return kept + [last]


def format_html(text):
    # ตกแต่งข้อความก่อนส่ง (ทำที่จุดเดียว ข้อความส่วนอื่นเขียนแบบธรรมดา)
    #   บรรทัดแรก          -> ตัวหนา (หัวข้อ)
    #   "# หัวข้อย่อย"     -> ตัวหนา
    #   "- รายการ"         -> "• รายการ"
    #   "(หมายเหตุ)"       -> ตัวเอียง
    # escape < > & ก่อน ข้อความที่ผู้ใช้พิมพ์มีเครื่องหมายพวกนี้จะได้ไม่พัง
    lines = []
    for i, line in enumerate(text.split("\n")):
        safe = html.escape(line, quote=False)
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


def inline(buttons):
    # buttons -> reply_markup แบบปุ่มติดข้อความ (json)
    rows = []
    for row in buttons:
        rows.append([{"text": label, "callback_data": data} for label, data in row])
    return json.dumps({"inline_keyboard": rows}, ensure_ascii=False)


def deliver(token, chat_id, item):
    # ส่งข้อความ 1 รายการจากคิว คืน OK / BAD / NET
    #   item = {"text", "silent", "buttons"}               ส่งข้อความใหม่
    #   item = {"edit": message_id, "text", "buttons"}     แก้ข้อความเดิม (เมนูเปลี่ยนชั้น)
    #   item = {"answer": callback_id}                     บอก Telegram ว่ารับการกดปุ่มแล้ว (หยุดหมุน)
    if "answer" in item:
        return post(token, "answerCallbackQuery", {"callback_query_id": item["answer"]})
    buttons = limit_buttons(item.get("buttons"))
    text = format_html(shorten(item["text"]))
    if "edit" in item:
        params = {"chat_id": chat_id, "message_id": item["edit"], "text": text,
                  "parse_mode": "HTML", "reply_markup": inline(buttons or [])}
        return post(token, "editMessageText", params)
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_notification": "true" if item.get("silent") else "false"}
    if buttons:
        params["reply_markup"] = inline(buttons)
    else:
        params["reply_markup"] = KEYBOARD   # ข้อความธรรมดาแนบปุ่มล่างไว้ให้เสมอ
    return post(token, "sendMessage", params)


def get_updates(token, offset, wait=0):
    # ดึงข้อความใหม่ · wait = รอข้อความใหม่ได้นานสุดกี่วินาที (long polling)
    # ผิดพลาด / เน็ตหลุด = None (ไม่ล้ม)
    params = {"timeout": wait}
    if offset is not None:
        params["offset"] = offset
    try:
        return call(token, "getUpdates", params, timeout=wait + 5).get("result", [])
    except Exception:
        return None


class TelegramWorker:
    # ส่ง/รับข้อความใน thread แยก · ลูปหลักแค่ใส่คิว (send/edit) และหยิบจากคิว (receive)

    def __init__(self, token, chat_id, retry_sec=10, wait=2, set_menu=True):
        self.token = token
        self.set_menu = set_menu          # ตั้งรายการคำสั่งในปุ่ม Menu ตอนเริ่ม (เทสต์ปิด = ไม่ยิงเน็ตจริง)
        self.chat_id = str(chat_id)
        self.retry_sec = retry_sec        # ส่งไม่ได้ รอกี่วินาทีค่อยลองใหม่
        self.wait = wait                  # long polling รอข้อความใหม่กี่วินาที
        self.outbox = queue.Queue()       # รายการรอส่ง (dict ตาม deliver)
        self.inbox = queue.Queue()        # สิ่งที่รับมาแล้ว รอลูปหลักหยิบ
        self.start_time = int(time.time())
        self.offset = None
        self.online = True                # ส่ง/รับครั้งล่าสุดสำเร็จไหม (ไว้แสดงสถานะ)
        self.running = True               # False = ให้ thread หยุด (ใช้ตอนเทสต์)
        # daemon=True: กด q ปิดโปรแกรมแล้ว thread ปิดตามเอง
        threading.Thread(target=self.send_loop, daemon=True).start()
        threading.Thread(target=self.poll_loop, daemon=True).start()

    def __str__(self):
        return ("Telegram(" + ("ออนไลน์" if self.online else "ออฟไลน์")
                + ", ค้างส่ง=" + str(self.outbox.qsize()) + ")")

    # ---------- เรียกจากลูปหลัก (ไม่รอเน็ต) ----------

    def send(self, text, silent=False, buttons=None):
        # ส่งข้อความใหม่ · buttons = ปุ่มติดข้อความ (ไม่ใส่ = แนบปุ่มล่าง)
        self.outbox.put({"text": text, "silent": silent, "buttons": buttons})

    def edit(self, message_id, text, buttons=None):
        # แก้ข้อความเดิม (ใช้ตอนกดเมนูแล้วเปลี่ยนชั้น แชทจะได้ไม่รก)
        self.outbox.put({"edit": message_id, "text": text, "buttons": buttons})

    def receive(self):
        # หยิบสิ่งที่รับมาแล้วทั้งหมด (ไม่มี = list ว่าง)
        #   {"kind": "text", "text": ...}
        #   {"kind": "button", "data": ..., "message_id": ..., "text": ข้อความที่ปุ่มติดอยู่}
        items = []
        while not self.inbox.empty():
            items.append(self.inbox.get())
        return items

    def pending(self):
        return self.outbox.qsize()

    def stop(self):
        # ให้ thread ทั้งสองหยุด (หยุดจริงภายในไม่เกิน ~1 วินาที)
        self.running = False

    # ---------- ทำงานใน thread ----------

    def send_loop(self):
        # ส่งทีละรายการตามลำดับ
        #   NET = รอแล้วลองรายการเดิมใหม่ (ไม่ข้าม ไม่สลับลำดับ)
        #   BAD = Telegram ไม่รับ -> ทิ้งรายการนี้ ไปต่อ (ไม่งั้นคิวค้างตลอด)
        # ตั้งรายการคำสั่งในปุ่ม Menu ครั้งเดียวตอนเริ่ม (ไม่ได้ก็ไม่เป็นไร ปุ่มอื่นยังใช้ได้)
        if self.set_menu:
            post(self.token, "setMyCommands",
                 {"commands": json.dumps(COMMANDS, ensure_ascii=False)})
        while self.running:
            try:
                item = self.outbox.get(timeout=0.5)      # รอรายการในคิว
            except queue.Empty:
                continue                                 # ยังไม่มี -> วนไปเช็ก running
            while self.running:
                result = deliver(self.token, self.chat_id, item)
                if result == NET:
                    self.online = False
                    print("ส่ง Telegram ไม่ได้ จะลองใหม่ใน " + str(self.retry_sec)
                          + " วิ (ค้าง " + str(self.outbox.qsize() + 1) + " รายการ)")
                    time.sleep(self.retry_sec)           # sleep ใน thread นี้ ลูปหลักไม่ค้าง
                    continue
                self.online = True
                # BAD ตอนแก้เมนู ส่วนใหญ่คือ "ข้อความเหมือนเดิม" (กดปุ่มเดิมซ้ำ) ไม่ใช่ปัญหา ไม่ต้องบอก
                if result == BAD and "answer" not in item and "edit" not in item:
                    print("Telegram ไม่รับข้อความนี้ (ข้าม): " + item.get("text", "")[:40])
                break

    def poll_loop(self):
        # รับข้อความแชท + การกดปุ่ม · รับเฉพาะ chat id ของผู้ใช้
        while self.running:
            updates = get_updates(self.token, self.offset, self.wait)
            if updates is None:                     # เน็ตหลุด: พักแล้วลองใหม่
                self.online = False
                time.sleep(3)
                continue
            self.online = True
            for update in updates:
                self.offset = update["update_id"] + 1
                self.read_update(update)

    def read_update(self, update):
        # แปลง update 1 อันจาก Telegram -> ใส่ inbox (หรือทิ้ง)
        if "callback_query" in update:              # กดปุ่มติดข้อความ
            press = update["callback_query"]
            self.outbox.put({"answer": press["id"]})   # ให้ปุ่มหยุดหมุนทันที
            message = press.get("message", {})
            if str(message.get("chat", {}).get("id", "")) != self.chat_id:
                return                              # คนอื่นกด = ไม่สน
            self.inbox.put({"kind": "button", "data": press.get("data", ""),
                            "message_id": message.get("message_id"),
                            "text": message.get("text", "")})
            return
        message = update.get("message", {})
        if str(message.get("chat", {}).get("id", "")) != self.chat_id:
            return                                  # คนอื่นทักบอท = ไม่สน
        if "text" not in message:
            return                                  # รูป/สติกเกอร์ = ไม่สน
        if message.get("date", 0) < self.start_time:
            return                                  # ส่งมาก่อนเปิดโปรแกรม = ทิ้ง (กันทำคำสั่งเก่า)
        self.inbox.put({"kind": "text", "text": message["text"]})


def show_chat_ids():
    # ใช้ครั้งเดียวตอนตั้งค่า: ทักบอทในมือถือก่อน แล้วรัน  python -m pc.telegram
    from pc.storage import load_json
    token = load_json("secrets.json")["TELEGRAM_TOKEN"]
    try:
        result = call(token, "getUpdates", {})
    except Exception as e:
        print("ติดต่อ Telegram ไม่ได้ (เช็ก token / เน็ต):", type(e).__name__)
        return
    found = set()
    for update in result.get("result", []):
        if "message" in update:
            chat = update["message"]["chat"]
            found.add((chat["id"], chat.get("first_name", "")))
    if len(found) == 0:
        print("ยังไม่เจอข้อความ: เปิดบอทในมือถือ พิมพ์อะไรก็ได้ แล้วรันใหม่")
    for chat_id, name in found:
        print("chat id ของ", name, "=", chat_id)


if __name__ == "__main__":
    show_chat_ids()
