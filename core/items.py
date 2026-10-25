# ของ 1 ชิ้นในเช็คลิสต์ (ชื่อ, ที่มา, ความสำคัญ)

# ความสำคัญ: เลขน้อย = สำคัญกว่า = อยู่บนสุด
PRIORITY_ACTIVITY = 1   # กิจกรรมวันนั้น (by_date)
PRIORITY_SUBJECT = 2    # ตามวิชาในตารางเรียน
PRIORITY_WEATHER = 3    # ตามอากาศ
PRIORITY_WEEKDAY = 4    # ตามวันในสัปดาห์
PRIORITY_ALWAYS = 5     # ของทุกวัน


class Item:

    def __init__(self, name, source, priority, order=0):
        self.name = name          # ชื่อของ เช่น "ร่ม"
        self.source = source      # มาจากไหน เช่น "ฝน", "วิชาตัวอย่าง A"
        self.priority = priority  # เลขความสำคัญ (ดูค่าคงที่ด้านบน)
        self.order = order        # ลำดับของที่มา (เช่น วิชาคาบแรก = 0) ให้ของวิชาเดียวกันอยู่ติดกัน

    def __str__(self):
        return self.name + " (" + self.source + ")"

    def __lt__(self, other):
        # เรียงตาม ความสำคัญ -> ลำดับที่มา -> ชื่อ
        # (ใส่ชื่อด้วยเพื่อให้ผลเรียงเหมือนกันทุกครั้ง ทั้ง CPython และ MicroPython)
        if self.priority != other.priority:
            return self.priority < other.priority
        if self.order != other.order:
            return self.order < other.order
        return self.name < other.name
