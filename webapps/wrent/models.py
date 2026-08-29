from django.db import models
from django.utils import timezone


class WrentStation(models.Model):
    """租賃站點表"""
    station_code = models.CharField("站點代碼", max_length=30, unique=True)
    name = models.CharField("站點名稱", max_length=100)
    address = models.CharField("地址", max_length=255)
    capacity = models.PositiveIntegerField("車位容量", default=10)
    contact_phone = models.CharField("聯絡電話", max_length=50, blank=True, default="")
    is_active = models.BooleanField("是否營運中", default=True)
    created_at = models.DateTimeField("建立時間", auto_now_add=True)

    class Meta:
        db_table = "wrent_station"
        verbose_name = "租賃站點"
        verbose_name_plural = "租賃站點列表"

    def __str__(self):
        return f"{self.name} ({self.station_code})"


class WrentVehicleCategory(models.Model):
    """車型等級與費率表"""
    category_code = models.CharField("車型代碼", max_length=30, unique=True)
    name = models.CharField("車型名稱", max_length=100)
    hourly_rate = models.DecimalField("時租費率 (元/小時)", max_digits=10, decimal_places=2, default=120.00)
    daily_cap_rate = models.DecimalField("單日封頂費率 (元/日)", max_digits=10, decimal_places=2, default=1200.00)
    mileage_rate = models.DecimalField("里程費率 (元/公里)", max_digits=10, decimal_places=2, default=3.20)
    overdue_hourly_rate = models.DecimalField("逾期加成費率 (元/小時)", max_digits=10, decimal_places=2, default=180.00)
    deposit_amount = models.DecimalField("押金金額 (元)", max_digits=10, decimal_places=2, default=1000.00)
    description = models.TextField("車型說明", blank=True, default="")

    class Meta:
        db_table = "wrent_vehicle_category"
        verbose_name = "車型等級費率"
        verbose_name_plural = "車型等級費率列表"

    def __str__(self):
        return f"{self.name} (時租:{self.hourly_rate}/日上限:{self.daily_cap_rate})"


class WrentVehicle(models.Model):
    """車輛實體表"""
    STATUS_CHOICES = [
        ("AVAILABLE", "可租借 (AVAILABLE)"),
        ("RESERVED", "已預約 (RESERVED)"),
        ("RENTED", "租賃中 (RENTED)"),
        ("CLEANING", "整備清潔中 (CLEANING)"),
        ("MAINTENANCE", "保養維修中 (MAINTENANCE)"),
    ]

    plate_number = models.CharField("車牌號碼", max_length=20, unique=True)
    category = models.ForeignKey(
        WrentVehicleCategory, on_delete=models.PROTECT, related_name="vehicles", verbose_name="所屬車型"
    )
    current_station = models.ForeignKey(
        WrentStation, on_delete=models.PROTECT, related_name="vehicles", verbose_name="所在站點"
    )
    model_name = models.CharField("車輛廠牌型號", max_length=100, default="Toyota Vios")
    status = models.CharField("車況狀態", max_length=20, choices=STATUS_CHOICES, default="AVAILABLE")
    current_mileage = models.DecimalField("目前總里程 (km)", max_digits=12, decimal_places=2, default=1000.00)
    fuel_or_battery_level = models.PositiveIntegerField("剩餘油/電量百分比 (%)", default=100)
    is_active = models.BooleanField("是否上線運作", default=True)
    created_at = models.DateTimeField("建立時間", auto_now_add=True)

    class Meta:
        db_table = "wrent_vehicle"
        verbose_name = "租賃車輛實體"
        verbose_name_plural = "租賃車輛實體列表"

    def __str__(self):
        return f"{self.plate_number} - {self.model_name} [{self.get_status_display()}]"


class WrentReservation(models.Model):
    """預約排程單"""
    STATUS_CHOICES = [
        ("CONFIRMED", "已確認 (CONFIRMED)"),
        ("PICKED_UP", "已取車 (PICKED_UP)"),
        ("COMPLETED", "已還車結算 (COMPLETED)"),
        ("CANCELLED", "已取消 (CANCELLED)"),
        ("NO_SHOW", "逾時未取 (NO_SHOW)"),
    ]

    reservation_no = models.CharField("預約單號", max_length=50, unique=True)
    user_name = models.CharField("預約人姓名/帳號", max_length=100)
    user_phone = models.CharField("預約人電話", max_length=30, blank=True, default="")
    category = models.ForeignKey(
        WrentVehicleCategory, on_delete=models.PROTECT, verbose_name="預約車型"
    )
    assigned_vehicle = models.ForeignKey(
        WrentVehicle, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="指定/配賦車輛"
    )
    pickup_station = models.ForeignKey(
        WrentStation, on_delete=models.PROTECT, related_name="pickup_reservations", verbose_name="預計取車站點"
    )
    return_station = models.ForeignKey(
        WrentStation, on_delete=models.PROTECT, related_name="return_reservations", verbose_name="預計還車站點"
    )
    start_time = models.DateTimeField("預約取車時間")
    end_time = models.DateTimeField("預約還車時間")
    estimated_cost = models.DecimalField("預估租金 (元)", max_digits=10, decimal_places=2, default=0.00)
    has_insurance = models.BooleanField("加購安心保險", default=False)
    status = models.CharField("預約狀態", max_length=20, choices=STATUS_CHOICES, default="CONFIRMED")
    created_at = models.DateTimeField("預約建立時間", auto_now_add=True)

    class Meta:
        db_table = "wrent_reservation"
        verbose_name = "租車預約單"
        verbose_name_plural = "租車預約單列表"

    def __str__(self):
        return f"{self.reservation_no} - {self.user_name} ({self.start_time.strftime('%m/%d %H:%M')}~{self.end_time.strftime('%m/%d %H:%M')})"


class WrentRentalRecord(models.Model):
    """實際租借出車/還車核驗記錄"""
    STATUS_CHOICES = [
        ("IN_PROGRESS", "行程進行中 (IN_PROGRESS)"),
        ("RETURNED", "已驗車還車 (RETURNED)"),
    ]

    reservation = models.OneToOneField(
        WrentReservation, on_delete=models.CASCADE, related_name="rental_record", verbose_name="關聯預約"
    )
    vehicle = models.ForeignKey(
        WrentVehicle, on_delete=models.PROTECT, related_name="rental_records", verbose_name="租借車輛"
    )
    actual_pickup_time = models.DateTimeField("實際取車時間", default=timezone.now)
    actual_return_time = models.DateTimeField("實際還車時間", null=True, blank=True)
    pickup_mileage = models.DecimalField("取車里程 (km)", max_digits=12, decimal_places=2)
    return_mileage = models.DecimalField("還車里程 (km)", max_digits=12, decimal_places=2, null=True, blank=True)
    pickup_fuel = models.PositiveIntegerField("取車油/電量 (%)", default=100)
    return_fuel = models.PositiveIntegerField("還車油/電量 (%)", null=True, blank=True)
    checkout_notes = models.TextField("取車車況記錄與備註", blank=True, default="")
    checkin_notes = models.TextField("還車車況驗收備註", blank=True, default="")
    status = models.CharField("租賃狀態", max_length=20, choices=STATUS_CHOICES, default="IN_PROGRESS")

    class Meta:
        db_table = "wrent_rental_record"
        verbose_name = "實際租賃記錄"
        verbose_name_plural = "實際租賃記錄列表"

    def __str__(self):
        return f"租賃#{self.id} (車牌:{self.vehicle.plate_number})"


class WrentBillingInvoice(models.Model):
    """結算電子帳單明細"""
    PAYMENT_STATUS_CHOICES = [
        ("UNPAID", "待扣款/待繳費"),
        ("PAID", "已扣款完成"),
        ("REFUNDED", "已退款"),
    ]

    invoice_no = models.CharField("帳單號碼", max_length=50, unique=True)
    rental_record = models.OneToOneField(
        WrentRentalRecord, on_delete=models.CASCADE, related_name="invoice", verbose_name="關聯租借單"
    )
    total_hours_billed = models.DecimalField("計費時長 (小時)", max_digits=8, decimal_places=2, default=0.00)
    total_distance_km = models.DecimalField("行駛里程 (公里)", max_digits=10, decimal_places=2, default=0.00)
    base_time_fee = models.DecimalField("基礎時間租金 (元)", max_digits=10, decimal_places=2, default=0.00)
    mileage_fee = models.DecimalField("里程耗能費用 (元)", max_digits=10, decimal_places=2, default=0.00)
    overdue_fee = models.DecimalField("逾時還車罰則 (元)", max_digits=10, decimal_places=2, default=0.00)
    cross_station_fee = models.DecimalField("跨站調度費 (元)", max_digits=10, decimal_places=2, default=0.00)
    insurance_fee = models.DecimalField("保險費 (元)", max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField("折抵優惠金額 (元)", max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField("應付總金額 (元)", max_digits=10, decimal_places=2, default=0.00)
    payment_status = models.CharField("扣款狀態", max_length=20, choices=PAYMENT_STATUS_CHOICES, default="PAID")
    created_at = models.DateTimeField("出帳時間", auto_now_add=True)

    class Meta:
        db_table = "wrent_billing_invoice"
        verbose_name = "租車結算帳單"
        verbose_name_plural = "租車結算帳單列表"

    def __str__(self):
        return f"{self.invoice_no} - 總計: NT$ {self.total_amount}"
