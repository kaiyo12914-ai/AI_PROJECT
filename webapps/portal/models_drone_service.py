from __future__ import annotations
from django.db import models
from django.utils import timezone

class DroneServiceRole(models.TextChoices):
    UNIT_USER = 'UNIT_USER', '部隊使用者'
    MANUFACTURER = 'MANUFACTURER', '無人機製造商'
    PRIME_CONTRACTOR_QC = 'PRIME_CONTRACTOR_QC', '主合約商品管人員'
    CONSULTANT = 'CONSULTANT', '無人機顧問'
    ADMIN = 'ADMIN', '系統管理員'

class DroneServiceTicket(models.Model):
    """
    軍用商規無人機客服工單系統
    用於記錄跨角色（部隊、廠商、品管、顧問）之通報與處置
    """
    STATUS_CHOICES = [
        ('OPEN', '通報中'),
        ('IN_REVIEW', '顧問/品管審閱中'),
        ('FIXING', '廠商修製中'),
        ('CLOSED', '已結案'),
    ]

    title = models.CharField(max_length=200, verbose_name="事件標題")
    content = models.TextField(verbose_name="詳細描述")
    
    # 關聯發起者與處置者
    creator_role = models.CharField(
        max_length=30, 
        choices=DroneServiceRole.choices,
        default=DroneServiceRole.UNIT_USER,
        verbose_name="通報者身分"
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='OPEN',
        verbose_name="當前狀態"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="通報時間")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="最後異動")

    class Meta:
        db_table = "drone_service_tickets"
        verbose_name = "無人機服務工單"
        verbose_name_plural = "無人機服務工單"

class DroneTicketThread(models.Model):
    """
    工單討論串（跨角色資訊交換）
    """
    ticket = models.ForeignKey(DroneServiceTicket, on_delete=models.CASCADE, related_name='replies')
    sender_name = models.CharField(max_length=100, verbose_name="發言人姓名")
    sender_role = models.CharField(max_length=30, choices=DroneServiceRole.choices, verbose_name="發言身分")
    message = models.TextField(verbose_name="交流內容")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "drone_ticket_threads"
        ordering = ['created_at']

class DroneFAQ(models.Model):
    """
    針對特定角色的 FAQ
    """
    target_role = models.CharField(
        max_length=30, 
        choices=DroneServiceRole.choices, 
        default=DroneServiceRole.UNIT_USER,
        verbose_name="對象角色"
    )
    question = models.TextField(verbose_name="問題")
    answer = models.TextField(verbose_name="標準處置")
    is_classified = models.BooleanField(default=False, verbose_name="是否包含敏感資訊")

    class Meta:
        db_table = "drone_faqs"

class DroneDocument(models.Model):
    """
    無人機產品文件管理（型錄、規格、手冊）
    """
    DOC_TYPE_CHOICES = [
        ('CATALOG', '產品型錄'),
        ('SPEC', '規格說明書'),
        ('MANUAL', '操作手冊'),
        ('TECH_GUIDE', '技術指南'),
    ]

    title = models.CharField(max_length=200, verbose_name="文件名稱")
    doc_type = models.CharField(
        max_length=20, 
        choices=DOC_TYPE_CHOICES, 
        default='MANUAL',
        verbose_name="文件類型"
    )
    version = models.CharField(max_length=20, default='1.0', verbose_name="版本號")
    
    file_path = models.CharField(max_length=500, verbose_name="檔案實體路徑")
    
    uploaded_by_role = models.CharField(
        max_length=30, 
        choices=DroneServiceRole.choices,
        verbose_name="上傳者身分"
    )
    
    is_classified = models.BooleanField(default=False, verbose_name="是否限制存取(軍規)")
    download_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "drone_documents"
        verbose_name = "無人機文件管理"
        verbose_name_plural = "無人機文件管理"
        ordering = ['-updated_at']

# --- 整體後勤規劃專項 (ILS - Integrated Logistics Support) ---

class DroneAsset(models.Model):
    """
    無人機實體資產管理 (序號追蹤)
    """
    serial_number = models.CharField(max_length=100, unique=True, verbose_name="機身序號")
    model_name = models.CharField(max_length=100, verbose_name="型號名稱")
    owning_unit = models.CharField(max_length=100, verbose_name="所屬部隊/單位")
    total_flight_hours = models.FloatField(default=0.0, verbose_name="累積飛行時數")
    last_maintenance_date = models.DateField(null=True, blank=True, verbose_name="最後維保日期")
    health_status = models.CharField(
        max_length=20, 
        default='GOOD',
        choices=[('GOOD', '良好'), ('WARNING', '待檢'), ('REPAIR', '維修中'), ('SCRAP', '汰除')],
        verbose_name="健康狀態"
    )

    class Meta:
        db_table = "drone_assets"
        verbose_name = "無人機資產"

class DroneComponent(models.Model):
    """
    關鍵後勤零件清單
    """
    part_number = models.CharField(max_length=100, unique=True, verbose_name="零件料號")
    name = models.CharField(max_length=100, verbose_name="零件名稱")
    manufacturer = models.CharField(max_length=100, verbose_name="製造廠商")
    mtbf_hours = models.IntegerField(verbose_name="平均故障間隔(小時)")
    stock_quantity = models.IntegerField(default=0, verbose_name="目前庫存")
    safety_stock_level = models.IntegerField(default=5, verbose_name="安全庫存水位")

    class Meta:
        db_table = "drone_components"
        verbose_name = "後勤零件"

class MaintenanceRecord(models.Model):
    """
    維修與保養紀錄
    """
    asset = models.ForeignKey(DroneAsset, on_delete=models.CASCADE, verbose_name="關聯機身")
    maint_type = models.CharField(max_length=50, choices=[('ROUTINE', '定期保養'), ('REPAIR', '損壞維修'), ('UPGRADE', '軟硬體升級')], verbose_name="維保類型")
    description = models.TextField(verbose_name="工作內容摘要")
    performer_role = models.CharField(max_length=30, choices=DroneServiceRole.choices, verbose_name="執行身分")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完工時間")

    class Meta:
        db_table = "drone_maintenance_logs"
        verbose_name = "維保紀錄"
