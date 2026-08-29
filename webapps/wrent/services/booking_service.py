# webapps/wrent/services/booking_service.py
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from django.db import transaction
from django.utils import timezone

from webapps.wrent.models import (
    WrentStation,
    WrentVehicleCategory,
    WrentVehicle,
    WrentReservation,
    WrentRentalRecord,
    WrentBillingInvoice,
)
from webapps.wrent.services.billing_engine import BillingEngine


class BookingService:
    BUFFER_MINUTES = 30

    @classmethod
    def get_overlapping_reservations(
        cls,
        vehicle_id: int,
        start_time: datetime,
        end_time: datetime,
        buffer_minutes: int = BUFFER_MINUTES,
        exclude_reservation_id: Optional[int] = None,
    ):
        """
        查詢特定車輛在時間範圍（含緩衝期）內是否已有有效預約
        """
        buffered_start = start_time - timedelta(minutes=buffer_minutes)
        buffered_end = end_time + timedelta(minutes=buffer_minutes)

        qs = WrentReservation.objects.filter(
            assigned_vehicle_id=vehicle_id,
            status__in=["CONFIRMED", "PICKED_UP"],
            start_time__lt=buffered_end,
            end_time__gt=buffered_start,
        )
        if exclude_reservation_id:
            qs = qs.exclude(id=exclude_reservation_id)
        return qs

    @classmethod
    def find_available_vehicles(
        cls,
        category_id: int,
        pickup_station_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> List[WrentVehicle]:
        """
        檢索指定站點與時段內可用之車輛
        """
        # 取出該站點、該車型且非停用或維修中車輛
        candidates = WrentVehicle.objects.filter(
            category_id=category_id,
            current_station_id=pickup_station_id,
            is_active=True,
        ).exclude(status__in=["MAINTENANCE"])

        available = []
        for v in candidates:
            overlaps = cls.get_overlapping_reservations(v.id, start_time, end_time)
            if not overlaps.exists():
                available.append(v)
        return available

    @classmethod
    def create_reservation(
        cls,
        user_name: str,
        user_phone: str,
        category_id: int,
        pickup_station_id: int,
        return_station_id: int,
        start_time: datetime,
        end_time: datetime,
        has_insurance: bool = False,
        vehicle_id: Optional[int] = None,
    ) -> WrentReservation:
        """
        建立租車預約單（含排程防撞期驗證與即時預估費用）
        """
        if end_time <= start_time:
            raise ValueError("預約還車時間必須大於取車時間")

        category = WrentVehicleCategory.objects.get(id=category_id)
        pickup_station = WrentStation.objects.get(id=pickup_station_id)
        return_station = WrentStation.objects.get(id=return_station_id)

        with transaction.atomic():
            # 配賦車輛
            assigned_vehicle: Optional[WrentVehicle] = None
            if vehicle_id:
                target_vehicle = WrentVehicle.objects.select_for_update().get(id=vehicle_id)
                overlaps = cls.get_overlapping_reservations(target_vehicle.id, start_time, end_time)
                if overlaps.exists():
                    raise ValueError(f"車輛 {target_vehicle.plate_number} 在該時段已有預約，請選擇其他車輛或時段")
                assigned_vehicle = target_vehicle
            else:
                available_vehicles = cls.find_available_vehicles(category_id, pickup_station_id, start_time, end_time)
                if not available_vehicles:
                    raise ValueError("該時段此站點已無可用車輛，請調整時間或更換車型")
                assigned_vehicle = available_vehicles[0]

            is_cross_station = pickup_station_id != return_station_id
            quote = BillingEngine.calculate_quote(
                start_time=start_time,
                end_time=end_time,
                hourly_rate=category.hourly_rate,
                daily_cap_rate=category.daily_cap_rate,
                is_cross_station=is_cross_station,
                has_insurance=has_insurance,
            )

            reservation_no = f"WR-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

            reservation = WrentReservation.objects.create(
                reservation_no=reservation_no,
                user_name=user_name,
                user_phone=user_phone,
                category=category,
                assigned_vehicle=assigned_vehicle,
                pickup_station=pickup_station,
                return_station=return_station,
                start_time=start_time,
                end_time=end_time,
                estimated_cost=quote["total_estimated"],
                has_insurance=has_insurance,
                status="CONFIRMED",
            )
            return reservation

    @classmethod
    def checkout_vehicle(
        cls,
        reservation_id: int,
        pickup_mileage: Optional[float] = None,
        pickup_fuel: int = 100,
        notes: str = "",
    ) -> WrentRentalRecord:
        """
        辦理取車核驗出車手續
        """
        with transaction.atomic():
            reservation = WrentReservation.objects.select_for_update().get(id=reservation_id)
            if reservation.status != "CONFIRMED":
                raise ValueError(f"預約單狀態為 {reservation.status}，無法辦理取車")

            vehicle = reservation.assigned_vehicle
            if not vehicle:
                raise ValueError("本預約單尚未配賦車輛")

            init_mileage = pickup_mileage if pickup_mileage is not None else float(vehicle.current_mileage)

            record = WrentRentalRecord.objects.create(
                reservation=reservation,
                vehicle=vehicle,
                actual_pickup_time=timezone.now(),
                pickup_mileage=init_mileage,
                pickup_fuel=pickup_fuel,
                checkout_notes=notes,
                status="IN_PROGRESS",
            )

            reservation.status = "PICKED_UP"
            reservation.save(update_fields=["status"])

            vehicle.status = "RENTED"
            vehicle.save(update_fields=["status"])

            return record

    @classmethod
    def checkin_vehicle(
        cls,
        rental_record_id: int,
        return_station_id: int,
        return_mileage: float,
        return_fuel: int,
        notes: str = "",
        discount_amount: float = 0.0,
    ) -> WrentBillingInvoice:
        """
        辦理還車驗收與即時帳單出具
        """
        with transaction.atomic():
            record = WrentRentalRecord.objects.select_for_update().get(id=rental_record_id)
            if record.status != "IN_PROGRESS":
                raise ValueError("此租借單非進行中狀態，無法還車")

            reservation = record.reservation
            vehicle = record.vehicle
            category = reservation.category
            now = timezone.now()

            record.actual_return_time = now
            record.return_mileage = return_mileage
            record.return_fuel = return_fuel
            record.checkin_notes = notes
            record.status = "RETURNED"
            record.save()

            is_cross = reservation.pickup_station_id != return_station_id

            bill = BillingEngine.calculate_final_bill(
                reserved_end_time=reservation.end_time,
                actual_pickup_time=record.actual_pickup_time,
                actual_return_time=now,
                pickup_mileage=float(record.pickup_mileage),
                return_mileage=float(return_mileage),
                hourly_rate=category.hourly_rate,
                daily_cap_rate=category.daily_cap_rate,
                mileage_rate=category.mileage_rate,
                overdue_hourly_rate=category.overdue_hourly_rate,
                is_cross_station=is_cross,
                has_insurance=reservation.has_insurance,
                discount_amount=discount_amount,
            )

            invoice_no = f"INV-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
            invoice = WrentBillingInvoice.objects.create(
                invoice_no=invoice_no,
                rental_record=record,
                total_hours_billed=bill["total_hours_billed"],
                total_distance_km=bill["total_distance_km"],
                base_time_fee=bill["base_time_fee"],
                mileage_fee=bill["mileage_fee"],
                overdue_fee=bill["overdue_fee"],
                cross_station_fee=bill["cross_station_fee"],
                insurance_fee=bill["insurance_fee"],
                discount_amount=bill["discount_amount"],
                total_amount=bill["total_amount"],
                payment_status="PAID",
            )

            # 更新車況與站點
            vehicle.status = "CLEANING"
            vehicle.current_mileage = return_mileage
            vehicle.fuel_or_battery_level = return_fuel
            vehicle.current_station_id = return_station_id
            vehicle.save(update_fields=["status", "current_mileage", "fuel_or_battery_level", "current_station"])

            reservation.status = "COMPLETED"
            reservation.save(update_fields=["status"])

            return invoice
