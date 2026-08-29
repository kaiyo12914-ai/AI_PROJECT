import runpy
from pathlib import Path
from PIL import ImageGrab

runpy.run_path(r"H:\AI\AI_TOOLS\get_Window.py", run_name="__main__")
image = ImageGrab.grabclipboard()
if image is None or not hasattr(image, "save"):
    raise RuntimeError("get_Window.py完成後，Windows剪貼簿沒有可儲存的影像")
output = Path(r"H:\AI\AI_TOOLS\pb_source_vscode_latest.png")
image.save(output, "PNG")
print(f"saved={output}")
