import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")

import django

django.setup()

from django.conf import settings


def pytest_configure(config):
    config.addinivalue_line("markers", "django_db: mark test as requiring database access")


def _ensure_test_hosts():
    hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
    changed = False
    for h in ("testserver", "localhost", "127.0.0.1"):
        if h not in hosts:
            hosts.append(h)
            changed = True
    if changed:
        settings.ALLOWED_HOSTS = hosts


_ensure_test_hosts()
