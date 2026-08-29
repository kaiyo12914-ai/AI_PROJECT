# webapps/wrent/services/billing_engine.py
from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any


class BillingEngine:
    """
    WRent 核心計費引擎（無狀態純演算法）
    支援：
    1. 時租計費與單日上限（階梯自動封頂保護）
    2. 跨日租借累計（整日日租 + 餘裕時租封頂）
    3. 行駛里程與能耗計費
    4. 逾時還車加成罰則
    5. 甲租乙還站點調度費與安心險加購
    """

    DEFAULT_CROSS_STATION_FEE = Decimal("200.00")
    DEFAULT_INSURANCE_DAILY_FEE = Decimal("150.00")
    GRACE_PERIOD_SECONDS = 300  # 5 分鐘還車寬限期

    @staticmethod
    def calculate_time_fee(
        hours: float,
        hourly_rate: Decimal | float,
        daily_cap_rate: Decimal | float,
    ) -> Decimal:
        """
        計算時間基本租金（含階梯封頂）
        """
        hourly_rate = Decimal(str(hourly_rate))
        daily_cap_rate = Decimal(str(daily_cap_rate))

        if hours <= 0:
            return Decimal("0.00")

        # 向上取整到小數點或滿小時（租車通常以小時計，未滿 1 小時以 1 小時計）
        billed_hours = Decimal(str(math.ceil(hours)))

        full_days = int(billed_hours // Decimal("24"))
        remaining_hours = billed_hours % Decimal("24")

        remaining_cost = min(remaining_hours * hourly_rate, daily_cap_rate)
        total_time_fee = (Decimal(str(full_days)) * daily_cap_rate) + remaining_cost
        return total_time_fee.quantize(Decimal("0.01"))

    @classmethod
    def calculate_quote(
        cls,
        start_time: datetime,
        end_time: datetime,
        hourly_rate: Decimal | float,
        daily_cap_rate: Decimal | float,
        is_cross_station: bool = False,
        has_insurance: bool = False,
        cross_station_fee: Decimal | float | None = None,
        insurance_daily_fee: Decimal | float | None = None,
    ) -> Dict[str, Any]:
        """
        預約前報價試算
        """
        if end_time <= start_time:
            raise ValueError("還車時間必須晚於取車時間")

        duration_seconds = (end_time - start_time).total_seconds()
        duration_hours = duration_seconds / 3600.0
        billed_hours = math.ceil(duration_hours)

        base_time_fee = cls.calculate_time_fee(duration_hours, hourly_rate, daily_cap_rate)

        cs_fee = Decimal(str(cross_station_fee if cross_station_fee is not None else cls.DEFAULT_CROSS_STATION_FEE))
        ins_daily = Decimal(str(insurance_daily_fee if insurance_daily_fee is not None else cls.DEFAULT_INSURANCE_DAILY_FEE))

        applied_cs_fee = cs_fee if is_cross_station else Decimal("0.00")

        # 保險依日數計算（不足一日以一日計）
        insurance_days = max(1, math.ceil(duration_hours / 24.0))
        applied_ins_fee = (ins_daily * Decimal(str(insurance_days))) if has_insurance else Decimal("0.00")

        total_estimated = base_time_fee + applied_cs_fee + applied_ins_fee

        return {
            "duration_hours": round(duration_hours, 2),
            "billed_hours": billed_hours,
            "base_time_fee": float(base_time_fee),
            "cross_station_fee": float(applied_cs_fee),
            "insurance_fee": float(applied_ins_fee),
            "total_estimated": float(total_estimated.quantize(Decimal("0.01"))),
        }

    @classmethod
    def calculate_final_bill(
        cls,
        reserved_end_time: datetime,
        actual_pickup_time: datetime,
        actual_return_time: datetime,
        pickup_mileage: Decimal | float,
        return_mileage: Decimal | float,
        hourly_rate: Decimal | float,
        daily_cap_rate: Decimal | float,
        mileage_rate: Decimal | float,
        overdue_hourly_rate: Decimal | float,
        is_cross_station: bool = False,
        has_insurance: bool = False,
        discount_amount: Decimal | float = 0.0,
        cross_station_fee: Decimal | float | None = None,
        insurance_daily_fee: Decimal | float | None = None,
    ) -> Dict[str, Any]:
        """
        還車結算最終帳單
        """
        if actual_return_time <= actual_pickup_time:
            raise ValueError("實際還車時間必須晚於實際取車時間")

        pickup_mileage = Decimal(str(pickup_mileage))
        return_mileage = Decimal(str(return_mileage))
        if return_mileage < pickup_mileage:
            raise ValueError("還車里程不得小於取車里程")

        distance_km = return_mileage - pickup_mileage
        mileage_fee = (distance_km * Decimal(str(mileage_rate))).quantize(Decimal("0.01"))

        # 計算實際總時長
        total_seconds = (actual_return_time - actual_pickup_time).total_seconds()
        total_hours = total_seconds / 3600.0

        # 計算逾時（超過預約還車時間，扣除寬限期 5 分鐘）
        overdue_fee = Decimal("0.00")
        overdue_hours = 0
        if actual_return_time > reserved_end_time:
            overdue_diff_seconds = (actual_return_time - reserved_end_time).total_seconds()
            if overdue_diff_seconds > cls.GRACE_PERIOD_SECONDS:
                overdue_hours = math.ceil(overdue_diff_seconds / 3600.0)
                overdue_fee = (Decimal(str(overdue_hours)) * Decimal(str(overdue_hourly_rate))).quantize(Decimal("0.01"))

        # 基礎時間租金：依原預訂時長（或實際租借扣除逾期時長）
        regular_seconds = max(0.0, total_seconds - (overdue_hours * 3600.0))
        regular_hours = regular_seconds / 3600.0
        base_time_fee = cls.calculate_time_fee(regular_hours, hourly_rate, daily_cap_rate)

        cs_fee = Decimal(str(cross_station_fee if cross_station_fee is not None else cls.DEFAULT_CROSS_STATION_FEE))
        applied_cs_fee = cs_fee if is_cross_station else Decimal("0.00")

        ins_daily = Decimal(str(insurance_daily_fee if insurance_daily_fee is not None else cls.DEFAULT_INSURANCE_DAILY_FEE))
        insurance_days = max(1, math.ceil(total_hours / 24.0))
        applied_ins_fee = (ins_daily * Decimal(str(insurance_days))) if has_insurance else Decimal("0.00")

        discount = Decimal(str(discount_amount)).quantize(Decimal("0.01"))

        total_amount = base_time_fee + mileage_fee + overdue_fee + applied_cs_fee + applied_ins_fee - discount
        if total_amount < Decimal("0.00"):
            total_amount = Decimal("0.00")

        return {
            "total_hours_billed": round(total_hours, 2),
            "regular_hours": round(regular_hours, 2),
            "overdue_hours": overdue_hours,
            "total_distance_km": float(distance_km),
            "base_time_fee": float(base_time_fee),
            "mileage_fee": float(mileage_fee),
            "overdue_fee": float(overdue_fee),
            "cross_station_fee": float(applied_cs_fee),
            "insurance_fee": float(applied_ins_fee),
            "discount_amount": float(discount),
            "total_amount": float(total_amount.quantize(Decimal("0.01"))),
        }
