from __future__ import annotations
from django.db import models
from django.utils import timezone

class DroneServiceQA(models.Model):
    """
    無人機客服系統 Q&A 知識庫
    """
    CATEGORY_CHOICES = [
        ('HARDWARE', '硬體故障'),
        ('SOFTWARE', '軟體更新'),
        ('FLIGHT', '飛行操作'),
        ('REPAIR', '維修進度'),
        ('OTHER', '其他諮詢'),
    ]

    question = models.TextField(verbose_name="提問內容")
    answer = models.TextField(verbose_name="管家回覆")
    category = models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES, 
        default='OTHER',
        verbose_name="類別"
    )
    is_frequent = models.BooleanField(default=False, verbose_name="是否為常見問題")
    view_count = models.PositiveIntegerField(default=0, verbose_name="查看次數")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="建立時間")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="最後更新")

    class Meta:
        db_table = "drone_service_qa"
        verbose_name = "無人機 Q&A"
        verbose_name_plural = "無人機 Q&A"
        ordering = ["-is_frequent", "-view_count", "-created_at"]

    def __str__(self) -> str:
        return f"[{self.category}] {self.question[:30]}..."
