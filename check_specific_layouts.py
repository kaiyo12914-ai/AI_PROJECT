from pptx import Presentation
import os

def list_layouts(path):
    print(f"\n--- Layouts for {os.path.basename(path)} ---")
    prs = Presentation(path)
    for i, l in enumerate(prs.slide_layouts):
        print(f"Index {i}: {l.name}")

if __name__ == "__main__":
    templates = [
        r"H:\AI\Django\webapps\text2pptx\pptx_templates\default.pptx",
        r"H:\AI\Django\webapps\text2pptx\pptx_templates\mpc_style.pptx"
    ]
    for t in templates:
        list_layouts(t)
