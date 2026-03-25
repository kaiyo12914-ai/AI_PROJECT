from __future__ import annotations

import sys

from webapps.text2pptx.pptx2schema.pipelines.render_pipeline import run_render


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: python -m ...render_demo <bundle.json> <content.json> <output.pptx>")
        raise SystemExit(1)
    run_render(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"Saved {sys.argv[3]}")


if __name__ == "__main__":
    main()
