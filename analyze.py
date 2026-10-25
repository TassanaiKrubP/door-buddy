# ส่วน 5: สรุปผล + กราฟ จาก data/events.csv
# รัน (ในโฟลเดอร์ door_buddy):
#   python analyze.py            ข้อมูลจริง  (data/events.csv)
#   python analyze.py --demo     ข้อมูลโหมดเดโม (data/demo/events.csv)
#   python analyze.py --sample   สร้างข้อมูลจำลอง 14 วันแล้ววิเคราะห์ (กำกับว่า "ข้อมูลจำลอง" ทุกที่)
# ผลลัพธ์: พิมพ์รายงานบนจอ + เขียน report.txt และ report.png ไว้โฟลเดอร์เดียวกับ events.csv
#
# ใช้ตอบคำถามหลัก: OUT_DELAY (รอกี่วินาทีถึงนับว่าออกจริง) ควรตั้งเท่าไร จากข้อมูลจริง
import csv
import os
import random
import sys

from pc import storage

# ชุดสี (จากชุดสีอ้างอิงที่ผ่านการตรวจตาบอดสีแล้ว) + สีตัวหนังสือ/เส้นแกน
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES_1 = "#2a78d6"     # น้ำเงิน
SERIES_2 = "#eb6834"     # ส้ม
THAI_FONTS = ["Tahoma", "Leelawadee UI", "DejaVu Sans"]

SHORT_GRACE = 20         # ค่าแนะนำ = ออกแป๊บเดียว 95% + เผื่ออีก 20 วิ
MIN_SHORTS = 5           # ข้อมูลออกแป๊บเดียวน้อยกว่านี้ = ยังแนะนำไม่ได้


def load_events(path):
    # อ่าน events.csv -> list ของ dict {"date", "time", "event", "secs", "detail"}
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                row["secs"] = int(row["secs"])
            except (ValueError, KeyError, TypeError):
                row["secs"] = 0
            rows.append(row)
    return rows


def percentile(values, p):
    # ค่าที่ p% ของข้อมูลไม่เกิน (แบบง่าย ไม่ใช้ไลบรารี)
    values = sorted(values)
    return values[int(round(p / 100 * (len(values) - 1)))]


def suggest_delay(shorts, trips, current):
    # แนะนำ OUT_DELAY จากระยะเวลาออกแป๊บเดียว · คืน (ค่าแนะนำ หรือ None, เหตุผล)
    # ข้อควรรู้: ออกแป๊บเดียวที่นานเกิน OUT_DELAY ตอนนี้ จะถูกนับเป็น "ออกจริง" ไปแล้ว
    # ถ้าออกแป๊บเดียวส่วนใหญ่ใกล้ค่าตอนนี้ แปลว่าค่าตอนนี้อาจสั้นไป
    if len(shorts) < MIN_SHORTS:
        return None, ("ข้อมูลออกแป๊บเดียวยังน้อย (" + str(len(shorts)) + " ครั้ง ต้องมีอย่างน้อย "
                      + str(MIN_SHORTS) + ") ใช้ไปอีกสักพักแล้วรันใหม่")
    p95 = percentile(shorts, 95)
    value = max(30, ((p95 + SHORT_GRACE + 9) // 10) * 10)     # ปัดขึ้นเป็นหลักสิบ
    reason = ("ออกแป๊บเดียว 95% กลับภายใน " + str(p95) + " วิ -> เผื่ออีก "
              + str(SHORT_GRACE) + " วิ")
    near_limit = len([s for s in shorts if s >= current * 0.9])
    if near_limit >= max(2, len(shorts) // 10):
        reason += ("\nระวัง: ออกแป๊บเดียว " + str(near_limit) + " ครั้งเกือบถึง " + str(current)
                   + " วิ อาจมีที่นานกว่านี้แต่ถูกนับเป็นออกจริงไปแล้ว")
    quick_trips = len([t for t in trips if t < value])
    if quick_trips:
        reason += ("\nถ้าตั้ง " + str(value) + " วิ การออกจริงที่สั้นกว่านี้ " + str(quick_trips)
                   + " ครั้ง จะถูกนับเป็นออกแป๊บเดียวแทน (จะไม่ได้เตือน)")
    return value, reason


def summarize(events, out_delay):
    # นับและสรุปทุกอย่างที่ใช้ในรายงาน + กราฟ
    s = {"days": sorted(set(e["date"] for e in events)), "count": {}, "forget": {},
         "shorts": [], "trips": [], "per_day": {}}
    for e in events:
        name = e["event"]
        s["count"][name] = s["count"].get(name, 0) + 1
        if name == "short_trip":
            s["shorts"].append(e["secs"])
        elif name == "trip":
            s["trips"].append(e["secs"])
        elif name == "forget" and e["detail"]:
            s["forget"][e["detail"]] = s["forget"].get(e["detail"], 0) + 1
        if name in ["alert", "alert_new", "false_alert"]:
            day = s["per_day"].setdefault(e["date"], {"alert": 0, "false_alert": 0})
            day["false_alert" if name == "false_alert" else "alert"] += 1
    alerts = s["count"].get("alert", 0) + s["count"].get("alert_new", 0)
    s["alerts"] = alerts
    s["false_rate"] = (s["count"].get("false_alert", 0) / alerts * 100) if alerts else None
    s["out_delay"] = out_delay
    s["suggest"], s["reason"] = suggest_delay(s["shorts"], s["trips"], out_delay)
    return s


def report_lines(s, label):
    # รายงานแบบตัวหนังสือ (ใช้ทั้งพิมพ์บนจอ และเขียน report.txt = ตารางตัวเลขของกราฟ)
    c = s["count"]
    lines = ["รายงาน Door Buddy" + label]
    if s["days"]:
        lines.append("ช่วงข้อมูล: " + s["days"][0] + " ถึง " + s["days"][-1]
                     + " (" + str(len(s["days"])) + " วัน)")
    lines += ["",
              "การออกจากห้อง",
              "- ออกจริง: " + str(c.get("trip", 0)) + " ครั้ง",
              "- ออกแป๊บเดียว (ไม่เตือน): " + str(c.get("short_trip", 0)) + " ครั้ง",
              "- ปิดประตูจากในห้อง (เปิดค้างแล้วปิด): " + str(c.get("closed_inside", 0)) + " ครั้ง",
              "",
              "การเตือน",
              "- ส่งเช็คลิสต์: " + str(c.get("alert", 0)) + " ครั้ง"
              + " (ส่งเฉพาะของใหม่อีก " + str(c.get("alert_new", 0)) + " ครั้ง)",
              "- เตือนผิด (กด ยังไม่ได้ออก): " + str(c.get("false_alert", 0)) + " ครั้ง"]
    if s["false_rate"] is not None:
        lines.append("- อัตราเตือนผิด: " + "{:.0f}".format(s["false_rate"]) + "%")
    lines += ["- ประตูเปิดค้าง: " + str(c.get("open_long", 0)) + " ครั้ง",
              "- ไม่เตือนเพราะอยู่นอกช่วง/เตือนไปแล้ว: " + str(c.get("skip", 0)) + " ครั้ง",
              "",
              "ระยะเวลาออกแป๊บเดียว (วินาที)"]
    if s["shorts"]:
        lines.append("- น้อยสุด " + str(min(s["shorts"])) + " · กลาง "
                     + str(percentile(s["shorts"], 50)) + " · มากสุด " + str(max(s["shorts"])))
    lines += ["- OUT_DELAY ตอนนี้: " + str(s["out_delay"]) + " วิ",
              "- แนะนำ: " + (str(s["suggest"]) + " วิ" if s["suggest"] else "ยังแนะนำไม่ได้"),
              "  " + s["reason"].replace("\n", "\n  "),
              "",
              "ของที่ลืมบ่อย"]
    top = sorted(s["forget"].items(), key=lambda kv: -kv[1])[:5]
    lines += ["- " + name + ": " + str(n) + " ครั้ง" for name, n in top] or ["- (ยังไม่มี)"]
    if c.get("error"):
        lines += ["", "error ระหว่างทำงาน: " + str(c["error"]) + " ครั้ง (ดูรายละเอียดใน events.csv)"]
    return lines


def style_axes(ax, title):
    # แกน/เส้นตารางแบบเรียบ: เส้นตารางบาง สีจาง ตัวหนังสือสีเทาเข้ม (ไม่ใช้สีข้อมูล)
    from matplotlib.ticker import MaxNLocator
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=12, pad=10)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))   # จำนวนครั้ง = จำนวนเต็ม (ไม่มี 0.5)


def empty(ax):
    # ช่องที่ยังไม่มีข้อมูล: เอาแกนออกหมด เหลือแค่ข้อความ (แกน 0-1 ไม่มีความหมาย)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.text(0.5, 0.5, "(ยังไม่มีข้อมูล)", ha="center", va="center", color=MUTED,
            transform=ax.transAxes)


def draw(s, path, label):
    # วาดกราฟ 3 ช่องลง PNG · ไม่มี matplotlib = คืน False (รายงานตัวหนังสือยังใช้ได้)
    try:
        import matplotlib
        matplotlib.use("Agg")                    # วาดลงไฟล์ ไม่เปิดหน้าต่าง
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    plt.rcParams["font.family"] = THAI_FONTS
    fig, axes = plt.subplots(3, 1, figsize=(8, 11), facecolor=SURFACE)
    fig.suptitle("Door Buddy" + label, x=0.06, ha="left", color=INK, fontsize=15)

    # 1) ระยะเวลาออกแป๊บเดียว + เส้น OUT_DELAY ตอนนี้ / ที่แนะนำ
    ax = axes[0]
    style_axes(ax, "ออกแป๊บเดียวกี่วินาที (" + str(len(s["shorts"])) + " ครั้ง)")
    if s["shorts"]:
        top = max(max(s["shorts"]), s["out_delay"], s["suggest"] or 0) + 10
        ax.hist(s["shorts"], bins=range(0, top + 10, 10), color=SERIES_1,
                edgecolor=SURFACE, linewidth=2)                 # 2px ช่องว่างระหว่างแท่ง
        marks = [(s["out_delay"], "ตอนนี้ " + str(s["out_delay"]) + " วิ", INK_2)]
        if s["suggest"] and s["suggest"] != s["out_delay"]:
            marks.append((s["suggest"], "แนะนำ " + str(s["suggest"]) + " วิ", INK))
        marks.sort()
        y = ax.get_ylim()[1] * 0.92
        for i, (x, text, color) in enumerate(marks):
            ax.axvline(x, color=color, linewidth=1.5)
            # 2 เส้นใกล้กัน ป้ายไม่ให้ทับ: เส้นซ้ายป้ายอยู่ซ้ายเส้น · เส้นขวาป้ายอยู่ขวาเส้น
            if len(marks) == 2 and i == 0:
                ax.text(x - 2, y, text, color=color, fontsize=9, ha="right")
            else:
                ax.text(x + 2, y, text, color=color, fontsize=9, ha="left")
        ax.set_xlim(0, top + 25)                 # เผื่อที่ป้ายด้านขวา
        ax.set_xlabel("วินาที", color=MUTED, fontsize=9)
        ax.set_ylabel("ครั้ง", color=MUTED, fontsize=9)
    else:
        empty(ax)

    # 2) เตือนต่อวัน vs เตือนผิด (2 ชุดข้อมูล -> มีคำอธิบายสีเสมอ)
    ax = axes[1]
    false_total = s["count"].get("false_alert", 0)
    style_axes(ax, "เตือนต่อวัน เทียบกับเตือนผิด (เตือนผิด " + str(false_total)
               + " จาก " + str(s["alerts"]) + " ครั้ง)")
    days = sorted(s["per_day"])
    if days:
        xs = range(len(days))
        alerts = [s["per_day"][d]["alert"] for d in days]
        falses = [s["per_day"][d]["false_alert"] for d in days]
        ax.bar([x - 0.18 for x in xs], alerts, width=0.34, color=SERIES_1, label="เตือน")
        ax.bar([x + 0.18 for x in xs], falses, width=0.34, color=SERIES_2, label="เตือนผิด")
        ax.set_xticks(list(xs))
        ax.set_xticklabels([d[8:] + "/" + str(int(d[5:7])) for d in days])
        ax.set_xlim(-0.6, max(len(days), 7) - 0.4)   # วันน้อย แท่งไม่ใหญ่เต็มกรอบ
        # คำอธิบายสีไว้เหนือกราฟด้านขวา ไม่ทับแท่ง
        ax.legend(frameon=False, labelcolor=INK_2, fontsize=9, ncol=2,
                  loc="lower right", bbox_to_anchor=(1, 1.0))
        ax.set_ylabel("ครั้ง", color=MUTED, fontsize=9)
    else:
        empty(ax)

    # 3) ของที่ลืมบ่อย (แท่งแนวนอน ตัวเลขที่ปลายแท่ง)
    ax = axes[2]
    style_axes(ax, "ของที่ลืมบ่อย (จากคำสั่ง ลืม…)")
    ax.grid(False)
    top = sorted(s["forget"].items(), key=lambda kv: kv[1])[-5:]
    if top:
        names = [name for name, n in top]
        counts = [n for name, n in top]
        ax.barh(names, counts, height=0.35, color=SERIES_1)
        # เผื่อที่ 5 แถวเสมอ (ของน้อยแท่งก็ไม่หนา) · ชิดบน: ลืมบ่อยสุดอยู่บนสุด ที่ว่างอยู่ล่าง
        ax.set_ylim(len(top) - 5.4, len(top) - 0.4)
        for y, n in enumerate(counts):
            ax.text(n + max(counts) * 0.01, y, str(n), va="center", color=INK_2, fontsize=9)
        ax.set_xlim(0, max(counts) * 1.08)       # เผื่อที่ตัวเลขปลายแท่ง
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="y", colors=INK_2)
    else:
        empty(ax)

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return True


def make_sample(days=14, seed=1):
    # ข้อมูลจำลอง (ไว้ดูหน้าตารายงาน/กราฟก่อนมีข้อมูลจริง) · seed คงที่ = ได้ชุดเดิมทุกครั้ง
    rnd = random.Random(seed)
    rows = []
    for d in range(days):
        date = "2026-10-{:02d}".format(1 + d)
        for _ in range(rnd.randint(1, 4)):                     # ออกแป๊บเดียววันละ 1-4 ครั้ง
            rows.append([date, "07:{:02d}:00".format(rnd.randint(0, 59)), "short_trip",
                         int(rnd.triangular(5, 110, 35)), ""])
        for _ in range(rnd.randint(1, 3)):                     # ออกจริงวันละ 1-3 ครั้ง
            rows.append([date, "08:00:00", "alert", 0, ""])
            rows.append([date, "12:00:00", "trip", rnd.randint(600, 14400), ""])
        if rnd.random() < 0.2:
            rows.append([date, "08:05:00", "false_alert", 0, ""])
        if rnd.random() < 0.3:
            rows.append([date, "20:00:00", "forget", 0, rnd.choice(["ร่ม", "สายชาร์จ", "บัตรนักศึกษา"])])
    return rows


def main():
    config = storage.load_json("config.json")
    label = ""
    if "--sample" in sys.argv:
        folder = "data/sample"
        label = " (ข้อมูลจำลอง)"
        path = os.path.join(storage.ROOT, folder, "events.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(storage.EVENT_HEADER)
            writer.writerows(make_sample())
    elif "--demo" in sys.argv:
        folder = "data/demo"
        label = " (ข้อมูลโหมดเดโม)"
    else:
        folder = "data"
    events_path = os.path.join(storage.ROOT, folder, "events.csv")
    if not os.path.exists(events_path):
        print("ยังไม่มี " + events_path + " (ใช้ระบบสักพักก่อน หรือลอง python analyze.py --sample)")
        return
    s = summarize(load_events(events_path), config["OUT_DELAY"])
    text = "\n".join(report_lines(s, label))
    print(text)
    with open(os.path.join(storage.ROOT, folder, "report.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    png = os.path.join(storage.ROOT, folder, "report.png")
    if draw(s, png, label):
        print("\nบันทึกกราฟแล้ว: " + png)
    else:
        print("\nยังไม่ได้ติดตั้ง matplotlib จึงยังไม่มีกราฟ (รายงานตัวหนังสืออยู่ใน report.txt)")


if __name__ == "__main__":
    main()
