from pptx import Presentation
import os

def check_compatibility(template_dir):
    files = [f for f in os.listdir(template_dir) if f.lower().endswith('.pptx')]
    results = []
    
    # 邏輯對齊 views.py
    def _pick_layout_by_name(prs, name_contains):
        key = name_contains.strip().lower()
        for layout in prs.slide_layouts:
            if key in (getattr(layout, "name", "") or "").lower():
                return layout.name
        return None

    print(f"{'Filename':<40} | {'Cover Match':<20} | {'Content Match':<20}")
    print("-" * 85)

    for fn in files:
        path = os.path.join(template_dir, fn)
        try:
            prs = Presentation(path)
            cover = _pick_layout_by_name(prs, "cover") or _pick_layout_by_name(prs, "title slide")
            content = _pick_layout_by_name(prs, "content") or _pick_layout_by_name(prs, "title and content")
            
            cover_status = f"OK ({cover})" if cover else "FAIL"
            content_status = f"OK ({content})" if content else "FAIL"
            
            print(f"{fn[:38]:<40} | {cover_status:<20} | {content_status:<20}")
        except Exception as e:
            print(f"{fn[:38]:<40} | ERROR: {str(e)[:35]}")

if __name__ == "__main__":
    PPTX_TEMPLATE_DIR = r"H:\AI\Django\webapps\text2pptx\pptx_templates"
    check_compatibility(PPTX_TEMPLATE_DIR)
