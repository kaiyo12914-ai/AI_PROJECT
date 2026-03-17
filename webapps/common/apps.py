# webapps/common/apps.py
from __future__ import annotations

from django.apps import AppConfig

from .net import ensure_no_proxy


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "webapps.common"

    def ready(self) -> None:
        # ✅ 全站啟動一次（可重複呼叫也沒副作用）
        ensure_no_proxy([
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            # ✅ 你指定要加的
            "mpcai.mpc.mil.tw",
        ])
