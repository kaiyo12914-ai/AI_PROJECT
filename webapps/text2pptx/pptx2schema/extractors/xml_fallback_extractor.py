from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Dict, List


def list_xml_parts(pptx_path: str | Path) -> List[str]:
    with zipfile.ZipFile(str(pptx_path), "r") as zf:
        return sorted([n for n in zf.namelist() if n.endswith(".xml")])


def extract_theme_xml(pptx_path: str | Path) -> Dict[str, str]:
    with zipfile.ZipFile(str(pptx_path), "r") as zf:
        for name in zf.namelist():
            if name.startswith("ppt/theme/") and name.endswith(".xml"):
                return {"theme_part": name}
    return {}
