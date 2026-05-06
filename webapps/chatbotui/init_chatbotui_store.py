from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webapps.chatbotui.repository import ChatbotUIRepository


def main() -> None:
    repo = ChatbotUIRepository()
    repo.ensure_schema()
    print("ChatbotUI PostgreSQL schema is ready.")


if __name__ == "__main__":
    main()
