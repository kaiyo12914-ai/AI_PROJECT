from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from webapps.projectnotes.models import ActivityLog


class Command(BaseCommand):
    help = "Generate weekly quality report for projectnotes."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--project-id", type=int, default=0)

    def handle(self, *args, **options):
        days = max(1, min(90, int(options.get("days") or 7)))
        project_id = int(options.get("project_id") or 0)

        since = timezone.now() - timedelta(days=days)
        qs = ActivityLog.objects.filter(created_at__gte=since)
        if project_id > 0:
            qs = qs.filter(project_id=project_id)

        total_queries = qs.filter(action="chat_query").count()
        citation_clicks = qs.filter(action="citation_click").count()
        usage_count = qs.count()
        insufficient = 0

        latency_vals = []
        for raw in qs.filter(action="chat_query").values_list("detail_json", flat=True)[:10000]:
            d = {}
            try:
                if isinstance(raw, dict):
                    d = raw
                else:
                    d = json.loads(raw or "{}")
            except Exception:
                d = {}
            if str(d.get("status") or "").strip().lower() == "insufficient":
                insufficient += 1
            try:
                v = float(d.get("latency_ms"))
                if v >= 0:
                    latency_vals.append(v)
            except Exception:
                pass
        avg_latency = (sum(latency_vals) / len(latency_vals)) if latency_vals else 0.0

        insufficient_rate = (insufficient / total_queries) if total_queries else 0.0
        click_rate = (citation_clicks / total_queries) if total_queries else 0.0

        self.stdout.write("=== ProjectNotes Weekly Report ===")
        self.stdout.write(f"range_days: {days}")
        self.stdout.write(f"project_id: {project_id if project_id > 0 else 'ALL'}")
        self.stdout.write(f"usage_count: {usage_count}")
        self.stdout.write(f"query_count: {total_queries}")
        self.stdout.write(f"insufficient_count: {insufficient}")
        self.stdout.write(f"insufficient_rate: {insufficient_rate:.4f}")
        self.stdout.write(f"citation_click_count: {citation_clicks}")
        self.stdout.write(f"citation_click_rate: {click_rate:.4f}")
        self.stdout.write(f"avg_latency_ms: {avg_latency:.2f}")

