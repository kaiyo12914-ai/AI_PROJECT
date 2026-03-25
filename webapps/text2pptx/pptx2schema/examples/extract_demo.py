from __future__ import annotations

import json
import sys

from webapps.text2pptx.pptx2schema.pipelines.extract_pipeline import run_extract


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m ...extract_demo <input.pptx> <output.raw.json>")
        raise SystemExit(1)
    raw = run_extract(sys.argv[1], source_file=sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(raw.model_dump(), f, ensure_ascii=False, indent=2)
    print(f"Saved {sys.argv[2]}")


if __name__ == "__main__":
    main()
