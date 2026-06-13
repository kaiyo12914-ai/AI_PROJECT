import os
import io
from PIL import Image
import mss

import win32clipboard
import win32con


# ----------------------------
# Config
# ----------------------------
MAX_WIDTH = int(os.getenv("SCREEN_MAX_WIDTH", "1600"))


def grab_desktop_1() -> Image.Image:
    """Capture Desktop 1 (primary monitor)."""
    with mss.mss() as sct:
        mon = sct.monitors[1]   # 👈 桌面 1（主螢幕）
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.rgb)


def resize_keep_aspect(img: Image.Image, max_width: int) -> Image.Image:
    if max_width <= 0 or img.width <= max_width:
        return img
    new_h = int(max_width * img.height / img.width)
    return img.resize((max_width, new_h))


def copy_image_to_clipboard(img: Image.Image) -> None:
    output = io.BytesIO()
    img.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]  # 移除 BMP header
    output.close()

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()


def main():
    img = grab_desktop_1()
    img = resize_keep_aspect(img, MAX_WIDTH)
    copy_image_to_clipboard(img)

    print("✅ 已抓取【桌面 1（主螢幕）】並複製到剪貼簿")
    print(f"   尺寸：{img.width} x {img.height}")


if __name__ == "__main__":
    main()
# ../venv3.12/Scripts/python.exe ./tools/get_Window.py
