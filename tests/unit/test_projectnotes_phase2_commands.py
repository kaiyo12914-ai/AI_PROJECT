import io
from types import SimpleNamespace

from django.core.management import call_command


class _FakeValuesList:
    def __init__(self, values):
        self._values = values

    def __getitem__(self, item):
        return self._values[item]


class _FakeActivityLogQuerySet:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, **kwargs):
        rows = self._rows
        for key, value in kwargs.items():
            if key == "created_at__gte":
                continue
            rows = [row for row in rows if row.get(key) == value]
        return _FakeActivityLogQuerySet(rows)

    def count(self):
        return len(self._rows)

    def values_list(self, field, flat=False):
        assert field == "detail_json"
        assert flat is True
        return _FakeValuesList([row.get("detail_json") for row in self._rows])


def test_projectnotes_weekly_report_uses_activity_log(monkeypatch):
    rows = [
        {"action": "chat_query", "detail_json": {"status": "insufficient", "latency_ms": 120}},
        {"action": "chat_query", "detail_json": {"status": "ok", "latency_ms": 80}},
        {"action": "citation_click", "detail_json": {}},
    ]
    fake_manager = SimpleNamespace(filter=lambda **kwargs: _FakeActivityLogQuerySet(rows))
    monkeypatch.setattr(
        "webapps.projectnotes.management.commands.projectnotes_weekly_report.ActivityLog.objects",
        fake_manager,
    )

    out = io.StringIO()
    call_command("projectnotes_weekly_report", stdout=out)
    text = out.getvalue()

    assert "usage_count: 3" in text
    assert "query_count: 2" in text
    assert "insufficient_count: 1" in text
    assert "citation_click_count: 1" in text
    assert "avg_latency_ms: 100.00" in text


def test_projectnotes_index_check_targets_current_tables(monkeypatch):
    seen = {}

    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def fetchall(self):
            return []

    class _FakeIntrospection:
        @staticmethod
        def table_names(_cursor):
            return [
                "projectnotes_document_chunk",
                "projectnotes_conversation",
                "projectnotes_message",
                "projectnotes_activity_log",
            ]

        @staticmethod
        def get_constraints(_cursor, table):
            seen.setdefault("tables", []).append(table)
            return {}

    fake_connection = SimpleNamespace(
        vendor="postgresql",
        cursor=lambda: _FakeCursor(),
        introspection=_FakeIntrospection(),
    )
    monkeypatch.setattr(
        "webapps.projectnotes.management.commands.projectnotes_index_check.connection",
        fake_connection,
    )

    out = io.StringIO()
    call_command("projectnotes_index_check", stdout=out)

    assert "projectnotes_document_chunk" in seen["tables"]
    assert "projectnotes_message" in seen["tables"]
    assert "projectnotes_activity_log" in seen["tables"]
    assert "projectnotes_turn" not in seen["tables"]
    assert "projectnotes_chunk" not in seen["tables"]

