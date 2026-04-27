"""
績效評語實體模型 - 資料庫儲存結構
"""

from django.db import models

class Evaluation(models.Model):
    """
    績效評語數據庫模型，記錄員工績效評估結果。
    """

    class GradeChoice(models.TextChoices):
        """績效等級選項"""
        EXCELLENT = "特優", "特優"
        ABOVE_AVERAGE = "甲上", "甲上"
        MEETS_EXPECTATIONS = "乙下", "乙下"
        BELOW_AVERAGE = "丙等", "丙等"

    student_name = models.CharField(
        max_length=100,
        verbose_name="員工姓名",
        help_text="受評價員工全名"
    )

    performance_grade = models.CharField(
        max_length=32,
        choices=GradeChoice.choices,
        blank=True,
        null=True,
        verbose_name="績效等級",
        help_text="員工績效等級（如特優/甲上等）"
    )

    comment_text = models.TextField(
        blank=True,
        null=True,
        verbose_name="評語內容",
        help_text="由系統或手動生成的績效評論文字"
    )

    traits = models.JSONField(
        blank=True,
        null=True,
        verbose_name="員工特質標籤",
        help_text="評估時選擇的員工表現特質（JSON格式）"
    )

    max_chars = models.IntegerField(
        default=80,
        verbose_name="評語最大字數限制",
        help_text="評語生成時的字數上限（預設80字）",
        choices=[
            (x, str(x)) for x in range(1, 121)
        ]
    )

    temperature = models.FloatField(
        default=0.7,
        verbose_name="LLM溫度參數",
        help_text="大語言模型生成評語時的創意參數（0~1之間）",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="生成時間",
        help_text="評語被創建或更新的時間戳記"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="最後更新時間",
        help_text="評語內容最新修改時間"
    )

    llm_provider = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="LLM提供商",
        help_text="生成評語的模型來源（如LM_STUDIO/OpenAI等）"
    )

    model_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="模型名稱",
        help_text="生成評語的模型名稱"
    )

    idno = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="員工帳號",
        help_text="被評價人員的系統帳號（如工號或識別碼）"
    )

    creator_account = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="生成人員",
        help_text="生成評語的人員帳號"
    )
    subPerformanceGrades = models.JSONField(
        blank=True,
        null=True,
        verbose_name="子績效評分細項",
        help_text="儲存子績效等級評分，如[{\"thoughtGradeOptions\": \"甲上\"}, ...]"
    )

    class Meta:
        """元選項配置"""
        verbose_name = "績效評語"
        verbose_name_plural = "績效評語列表"
        ordering = ["-created_at"]
        unique_together = [
            ("student_name", "performance_grade", "created_at")
        ]

    def __str__(self):
        """顯示模型實例字串"""
        return f"{self.student_name} ({self.get_performance_grade_display() or '無等級'})"

    @classmethod
    def create_from_api_request(cls, student_name: str, traits: list,
                               performance_grade: str = None,
                               comment_text: str = None,
                               sub_performance_grades=None,
                               llm_provider:str = None,
                               model_name:str=None,
                               creator_account:str=None, idno:str=None):
        """
        從API請求數據創建評語實例。

        Args:
            student_name (str): 员工姓名
            traits (list): 特質列表（如 ["團隊合作", "進取心強"]）
            performance_grade (str, optional): 績效等級. Defaults to None.
            comment_text (str, optional): 直接評語內容. Defaults to None.
            sub_performance_grades (list, optional): 子績效評分細項. Defaults to None.

        Returns:
            Evaluation: 新建實例
        """
        evaluation = cls(
            student_name=student_name,
            traits=traits if traits else [],
            performance_grade=performance_grade,
            comment_text=comment_text,
            max_chars=80,  # 預設值
            llm_provider=llm_provider,
            model_name = model_name,
            creator_account=creator_account,
            idno=idno,
            subPerformanceGrades=sub_performance_grades if sub_performance_grades else []
        )
        return evaluation

    def save(self, *args, **kwargs):
        """自動設置 LLM 提供商"""
        if not self.llm_provider and hasattr(self, 'comment_text'):
            from django.conf import settings
            # 預設為系統環境變數或指定的預設值
            self.llm_provider = getattr(settings, 'DEFAULT_LLM_PROVIDER', None)
        super().save(*args, **kwargs)

    @property
    def is_fully_populated(self) -> bool:
        """檢查評語是否已完整記錄（姓名+評論內容）"""
        return bool(self.student_name and self.comment_text)
