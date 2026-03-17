from __future__ import annotations

from django.db import models


class PortalUsageLog(models.Model):
    """
    Portal 功能使用紀錄

    記錄內容：
    - 使用日期
    - 程式代碼（功能代碼）
    - 使用者（ID / Name）
    - 來源 path / method / IP
    - ✅ 新增：whoami 診斷資訊 (JSON)
    """

    used_date = models.DateField(
        verbose_name="使用日期",
        db_index=True,
    )

    program_code = models.CharField(
        verbose_name="程式代碼",
        max_length=50,
        db_index=True,
    )

    user_id = models.CharField(
        verbose_name="使用者代碼",
        max_length=64,
        db_index=True,
        blank=True,
        default="",
    )

    user_name = models.CharField(
        verbose_name="使用者姓名",
        max_length=128,
        blank=True,
        default="",
    )

    path = models.CharField(
        verbose_name="請求路徑",
        max_length=255,
        blank=True,
        default="",
    )

    method = models.CharField(
        verbose_name="HTTP 方法",
        max_length=10,
        blank=True,
        default="GET",
    )

    ip = models.CharField(
        verbose_name="來源 IP",
        max_length=64,
        blank=True,
        default="",
    )

    # ✅ 新增：WHOAMI 資訊 (用於除錯環境前綴、Header 等問題)
    # 使用 TextField 存儲 JSON 字串，以利相容不同環境的 SQLite/Oracle
    whoami_json = models.TextField(
        verbose_name="WhoAmI 資訊",
        blank=True,
        default="{}",
    )

    created_at = models.DateTimeField(
        verbose_name="建立時間",
        auto_now_add=True,
    )

    class Meta:
        db_table = "portal_usage_log"
        verbose_name = "Portal 使用紀錄"
        verbose_name_plural = "Portal 使用紀錄"

        indexes = [
            models.Index(fields=["used_date", "program_code"], name="ix_pul_date_code"),
            models.Index(fields=["user_id"], name="ix_pul_user"),
            models.Index(fields=["program_code"], name="ix_pul_code"),
        ]

        ordering = ["-used_date", "-created_at"]

    def __str__(self) -> str:
        ts = self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else ""
        user = (self.user_id or "").strip()
        code = (self.program_code or "").strip()
        return f"{ts} | {code} | {user}"
