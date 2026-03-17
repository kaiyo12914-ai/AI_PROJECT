from __future__ import annotations
from django.db import models
from webapps.portal.models_drone_service import DroneServiceRole

class TelegramUserBinding(models.Model):
    """
    系統使用者與 Telegram 帳號之綁定關係
    """
    user_id = models.CharField(max_length=64, verbose_name="系統員工代號(PSID)", db_index=True)
    user_name = models.CharField(max_length=128, verbose_name="使用者姓名")
    role = models.CharField(max_length=30, choices=DroneServiceRole.choices, verbose_name="系統角色")
    
    tg_chat_id = models.CharField(max_length=100, verbose_name="Telegram Chat ID", unique=True)
    tg_username = models.CharField(max_length=100, null=True, blank=True, verbose_name="Telegram 用戶名")
    
    is_active = models.BooleanField(default=True, verbose_name="是否啟用通知")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "drone_tg_bindings"
        verbose_name = "Telegram 帳號綁定"

class DroneNotificationLog(models.Model):
    """
    Telegram 通知發送紀錄
    """
    recipient = models.ForeignKey(TelegramUserBinding, on_delete=models.CASCADE, verbose_name="接收者")
    message_type = models.CharField(
        max_length=20,
        choices=[('TICKET_NEW', '新工單通報'), ('TICKET_UPDATE', '工單狀態更新'), ('ALERT', '資安預警')],
        verbose_name="通知類型"
    )
    message_body = models.TextField(verbose_name="訊息內容")
    status = models.CharField(max_length=20, default='PENDING', verbose_name="發送狀態")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="發送時間")

    class Meta:
        db_table = "drone_tg_notif_logs"
