from __future__ import annotations

from django.apps import AppConfig


class VannaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "webapps.vanna"
    label = "vanna_integration"
    verbose_name = "Vanna 2.0 NL2SQL"
