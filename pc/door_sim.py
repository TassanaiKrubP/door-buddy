# ตัวจำลองประตูด้วยคีย์บอร์ด (ใช้ได้บน Windows)
# o = เปิด, c = ปิด · อ่านแบบไม่รอ เพื่อให้ลูปหลักเรียก tick ได้ทุกวินาที
import msvcrt


def read_key():
    # คืนตัวอักษรที่กด (ตัวเล็ก) หรือ None ถ้ายังไม่ได้กดอะไร
    if msvcrt.kbhit():
        return msvcrt.getwch().lower()
    return None
