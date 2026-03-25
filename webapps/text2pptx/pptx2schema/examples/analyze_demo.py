from __future__ import annotations

import json
import sys

from webapps.text2pptx.pptx2schema.pipelines.analyze_pipeline import run_analyze


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m ...analyze_demo <input.pptx> <output.bundle.json>")
        raise SystemExit(1)
    bundle = run_analyze(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(bundle.model_dump(), f, ensure_ascii=False, indent=2)
    print(f"Saved {sys.argv[2]}")


if __name__ == "__main__":
    main()
