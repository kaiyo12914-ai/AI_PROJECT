# tests/unit/wrent/test_billing_engine.py
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from webapps.wrent.services.billing_engine import BillingEngine


def test_time_fee_within_single_day_under_cap():
    """測試未達日租封頂時的時租累計"""
    hourly_rate = Decimal("120.00")
    daily_cap_rate = Decimal("1200.00")

    # 3 小時租借：3 * 120 = 360
    fee = BillingEngine.calculate_time_fee(3.0, hourly_rate, daily_cap_rate)
    assert fee == Decimal("360.00")

    # 0.5 小時租借（未滿 1 小時以 1 小時計）：1 * 120 = 120
    fee_fraction = BillingEngine.calculate_time_fee(0.5, hourly_rate, daily_cap_rate)
    assert fee_fraction == Decimal("120.00")


def test_time_fee_hitting_daily_cap():
    """測試達到並超過單日封頂時，自動以日租上限計算"""
    hourly_rate = Decimal("120.00")
    daily_cap_rate = Decimal("1200.00")

    # 10 小時：10 * 120 = 1200，剛好達到封頂
    fee_10h = BillingEngine.calculate_time_fee(10.0, hourly_rate, daily_cap_rate)
    assert fee_10h == Decimal("1200.00")

    # 15 小時：大於 10 小時但未滿 24 小時，依然封頂在 1200
    fee_15h = BillingEngine.calculate_time_fee(15.0, hourly_rate, daily_cap_rate)
    assert fee_15h == Decimal("1200.00")

    # 24 小時整：依然為單日封頂 1200
    fee_24h = BillingEngine.calculate_time_fee(24.0, hourly_rate, daily_cap_rate)
    assert fee_24h == Decimal("1200.00")


def test_time_fee_multi_day_with_remainder():
    """測試跨日租借：完整天數日租 + 剩餘時數封頂計算"""
    hourly_rate = Decimal("120.00")
    daily_cap_rate = Decimal("1200.00")

    # 28 小時 = 1 天 (1200) + 4 小時 (4 * 120 = 480) = 1680
    fee_28h = BillingEngine.calculate_time_fee(28.0, hourly_rate, daily_cap_rate)
    assert fee_28h == Decimal("1680.00")

    # 36 小時 = 1 天 (1200) + 12 小時 (已封頂 1200) = 2400
    fee_36h = BillingEngine.calculate_time_fee(36.0, hourly_rate, daily_cap_rate)
    assert fee_36h == Decimal("2400.00")


def test_calculate_quote_options():
    """測試預估報價試算（含跨站與保險）"""
    start = datetime(2026, 9, 1, 10, 0, 0)
    end = start + timedelta(hours=5)

    # 5 小時 * 120 = 600，跨站 200，保險 1 天 150 -> 950
    quote = BillingEngine.calculate_quote(
        start_time=start,
        end_time=end,
        hourly_rate=Decimal("120.00"),
        daily_cap_rate=Decimal("1200.00"),
        is_cross_station=True,
        has_insurance=True,
    )

    assert quote["duration_hours"] == 5.0
    assert quote["billed_hours"] == 5
    assert quote["base_time_fee"] == 600.0
    assert quote["cross_station_fee"] == 200.0
    assert quote["insurance_fee"] == 150.0
    assert quote["total_estimated"] == 950.0


def test_calculate_final_bill_overdue_and_mileage():
    """測試還車結算帳單：包含逾期懲罰、里程耗能費與折扣"""
    reserved_start = datetime(2026, 9, 1, 10, 0, 0)
    reserved_end = reserved_start + timedelta(hours=4)  # 預約 4 小時

    actual_pickup = reserved_start
    # 逾期 1 小時 20 分鐘還車（總計約 5.33 小時）
    actual_return = reserved_end + timedelta(hours=1, minutes=20)

    bill = BillingEngine.calculate_final_bill(
        reserved_end_time=reserved_end,
        actual_pickup_time=actual_pickup,
        actual_return_time=actual_return,
        pickup_mileage=1000.0,
        return_mileage=1050.0,  # 行駛 50 km
        hourly_rate=Decimal("120.00"),
        daily_cap_rate=Decimal("1200.00"),
        mileage_rate=Decimal("3.20"),       # 里程費 50 * 3.2 = 160.0
        overdue_hourly_rate=Decimal("180.00"), # 逾期 1h20m 進位為 2 小時逾期 = 2 * 180 = 360.0
        is_cross_station=False,
        has_insurance=False,
        discount_amount=50.0,
    )

    # 基礎預約時間 4 小時 * 120 = 480.0
    # 里程費 50 * 3.2 = 160.0
    # 逾期費 2 * 180 = 360.0
    # 折扣 -50
    # 總額 = 480 + 160 + 360 - 50 = 950.0
    assert bill["base_time_fee"] == 480.0
    assert bill["mileage_fee"] == 160.0
    assert bill["overdue_hours"] == 2
    assert bill["overdue_fee"] == 360.0
    assert bill["total_distance_km"] == 50.0
    assert bill["discount_amount"] == 50.0
    assert bill["total_amount"] == 950.0


def test_final_bill_negative_distance_protection():
    """防呆測試：還車里程小於取車里程應拋出異常"""
    t1 = datetime(2026, 9, 1, 10, 0)
    t2 = t1 + timedelta(hours=2)

    with pytest.raises(ValueError, match="還車里程不得小於取車里程"):
        BillingEngine.calculate_final_bill(
            reserved_end_time=t2,
            actual_pickup_time=t1,
            actual_return_time=t2,
            pickup_mileage=1200.0,
            return_mileage=1100.0,  # 錯誤數據
            hourly_rate=120.0,
            daily_cap_rate=1200.0,
            mileage_rate=3.2,
            overdue_hourly_rate=180.0,
        )
