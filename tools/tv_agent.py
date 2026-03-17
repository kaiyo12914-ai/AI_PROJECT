import os
import io
import time
from typing import Optional

import mss
import pygetwindow as gw
from PIL import Image

import win32clipboard  # pywin32
import win32con


# ----------------------------
# Config
# ----------------------------
WINDOW_KEYWORD = os.getenv("TV_WINDOW_KEYWORD", "TeamViewer")
MAX_WIDTH = int(os.getenv("SCREEN_MAX_WIDTH", "1600"))  # 剪貼簿用 PNG，寬度可放大點更清楚
SLEEP_BEFORE_CAPTURE_SEC = float(os.getenv("CAPTURE_DELAY_SEC", "0.2"))


def find_window_by_keyword(keyword: str):
    """Return a pygetwindow Window or None."""
    keyword = (keyword or "").strip()
    if not keyword:
        return None

    titles = [t for t in gw.getAllTitles() if t and keyword.lower() in t.lower()]
    if not titles:
        return None

    # pick the first match
    wins = gw.getWindowsWithTitle(titles[0])
    if not wins:
        return None
    return wins[0]


def activate_window(win) -> None:
    """Try to restore and activate window."""
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
    except Exception:
        pass


def grab_window_image(win) -> Image.Image:
    """Capture a window region using mss and return PIL Image (RGB)."""
    # Some windows need a tiny delay after activation to paint correctly
    activate_window(win)
    time.sleep(SLEEP_BEFORE_CAPTURE_SEC)

    left, top, right, bottom = win.left, win.top, win.right, win.bottom
    width = max(1, right - left)
    height = max(1, bottom - top)

    with mss.mss() as sct:
        monitor = {"left": left, "top": top, "width": width, "height": height}
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.rgb)


def resize_keep_aspect(img: Image.Image, max_width: int) -> Image.Image:
    if max_width <= 0:
        return img
    if img.width <= max_width:
        return img
    new_h = int(max_width * img.height / img.width)
    return img.resize((max_width, new_h))


def copy_image_to_clipboard(img: Image.Image) -> None:
    """
    Copy PIL image to Windows clipboard as CF_DIB (device-independent bitmap).
    Windows clipboard expects DIB bytes without BMP file header.
    """
    # Convert to DIB bytes
    output = io.BytesIO()
    # BMP is easiest to convert to CF_DIB; we strip the 14-byte BMP header.
    img.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]  # remove BMP header
    output.close()

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()


def main():
    win = find_window_by_keyword(WINDOW_KEYWORD)
    if not win:
        # 友善：列出可用標題，方便你挑 keyword
        titles = [t for t in gw.getAllTitles() if t and t.strip()]
        sample = "\n".join(titles[:40])
        raise RuntimeError(
            f"找不到包含關鍵字 '{WINDOW_KEYWORD}' 的視窗。\n"
            f"請先確認視窗標題是否包含該字（建議設為 'TeamViewer'），\n"
            f"或用 PowerShell：$env:TV_WINDOW_KEYWORD='TeamViewer'\n\n"
            f"（目前前 40 個視窗標題如下）\n{sample}"
        )

    img = grab_window_image(win)
    img = resize_keep_aspect(img, MAX_WIDTH)

    copy_image_to_clipboard(img)

    print("✅ 已截圖並複製到剪貼簿。請直接到 ChatGPT 視窗 Ctrl+V 貼上提問。")
    print(f"   視窗：{win.title}")
    print(f"   尺寸：{img.width} x {img.height}")


if __name__ == "__main__":
    main()



# $env:TV_WINDOW_KEYWORD="Django"
# & H:/AI/Django/venv3.12/Scripts/python.exe h:/AI/Django/tv_agent.py