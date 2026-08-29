# webapps/wrent/views_api.py
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from webapps.portal.decorators import require_node
from webapps.wrent.models import (
    WrentStation,
    WrentVehicleCategory,
    WrentVehicle,
    WrentReservation,
    WrentRentalRecord,
    WrentBillingInvoice,
)
from webapps.wrent.services.billing_engine import BillingEngine
from webapps.wrent.services.booking_service import BookingService


def _json_ok(data=None, message: str = ""):
    resp = {"status": "ok"}
    if message:
        resp["message"] = message
    if data is not None:
        resp["data"] = data
    return JsonResponse(resp, json_dumps_params={"ensure_ascii": False})


def _json_err(message: str, code: str = "ERROR", status: int = 400):
    return JsonResponse({"status": "error", "code": code, "message": message}, status=status, json_dumps_params={"ensure_ascii": False})


@require_node("wrent", api=True)
@require_GET
def api_get_meta(request: HttpRequest) -> JsonResponse:
    """取得站點與車型基礎定義清單"""
    stations = list(
        WrentStation.objects.filter(is_active=True).values(
            "id", "station_code", "name", "address", "capacity"
        )
    )
    categories = list(
        WrentVehicleCategory.objects.all().values(
            "id",
            "category_code",
            "name",
            "hourly_rate",
            "daily_cap_rate",
            "mileage_rate",
            "overdue_hourly_rate",
            "deposit_amount",
            "description",
        )
    )
    return _json_ok({"stations": stations, "categories": categories})


@require_node("wrent", api=True)
@require_GET
def api_get_available_vehicles(request: HttpRequest) -> JsonResponse:
    """查詢某站點、特定車型與預約時段內的可用車輛"""
    try:
        category_id = int(request.GET.get("category_id", 0))
        station_id = int(request.GET.get("station_id", 0))
        start_str = request.GET.get("start_time", "").strip()
        end_str = request.GET.get("end_time", "").strip()

        if not (category_id and station_id and start_str and end_str):
            return _json_err("缺少必要參數 (category_id, station_id, start_time, end_time)")

        start_dt = parse_datetime(start_str)
        end_dt = parse_datetime(end_str)
        if not start_dt or not end_dt:
            return _json_err("日期時間格式無效 (需為 ISO 格式)")
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)

        vehicles = BookingService.find_available_vehicles(category_id, station_id, start_dt, end_dt)
        data = [
            {
                "id": v.id,
                "plate_number": v.plate_number,
                "model_name": v.model_name,
                "current_mileage": float(v.current_mileage),
                "fuel_or_battery_level": v.fuel_or_battery_level,
                "status": v.status,
            }
            for v in vehicles
        ]
        return _json_ok({"available_vehicles": data, "count": len(data)})
    except Exception as e:
        return _json_err(str(e))


@require_node("wrent", api=True)
@csrf_exempt
@require_POST
def api_calculate_quote(request: HttpRequest) -> JsonResponse:
    """即時費用試算報價"""
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        category_id = int(payload.get("category_id", 0))
        start_str = payload.get("start_time", "").strip()
        end_str = payload.get("end_time", "").strip()
        pickup_station_id = int(payload.get("pickup_station_id", 0))
        return_station_id = int(payload.get("return_station_id", 0))
        has_insurance = bool(payload.get("has_insurance", False))

        category = WrentVehicleCategory.objects.get(id=category_id)
        start_dt = parse_datetime(start_str)
        end_dt = parse_datetime(end_str)
        if not start_dt or not end_dt:
            return _json_err("時間格式無效")
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)

        is_cross = pickup_station_id != return_station_id if (pickup_station_id and return_station_id) else False
        quote = BillingEngine.calculate_quote(
            start_time=start_dt,
            end_time=end_dt,
            hourly_rate=category.hourly_rate,
            daily_cap_rate=category.daily_cap_rate,
            is_cross_station=is_cross,
            has_insurance=has_insurance,
        )
        return _json_ok(quote)
    except WrentVehicleCategory.DoesNotExist:
        return _json_err("車型不存在", status=404)
    except Exception as e:
        return _json_err(str(e))


@require_node("wrent", api=True)
@csrf_exempt
@require_POST
def api_create_reservation(request: HttpRequest) -> JsonResponse:
    """建立預約排程"""
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        user_name = payload.get("user_name", "").strip()
        user_phone = payload.get("user_phone", "").strip()
        category_id = int(payload.get("category_id", 0))
        pickup_station_id = int(payload.get("pickup_station_id", 0))
        return_station_id = int(payload.get("return_station_id", 0))
        start_str = payload.get("start_time", "").strip()
        end_str = payload.get("end_time", "").strip()
        has_insurance = bool(payload.get("has_insurance", False))
        vehicle_id = payload.get("vehicle_id")

        if not user_name or not category_id or not pickup_station_id or not return_station_id:
            return _json_err("請完整填寫預約人與站點資訊")

        start_dt = parse_datetime(start_str)
        end_dt = parse_datetime(end_str)
        if not start_dt or not end_dt:
            return _json_err("時間格式無效")
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)

        reservation = BookingService.create_reservation(
            user_name=user_name,
            user_phone=user_phone,
            category_id=category_id,
            pickup_station_id=pickup_station_id,
            return_station_id=return_station_id,
            start_time=start_dt,
            end_time=end_dt,
            has_insurance=has_insurance,
            vehicle_id=int(vehicle_id) if vehicle_id else None,
        )

        return _json_ok({
            "reservation_id": reservation.id,
            "reservation_no": reservation.reservation_no,
            "plate_number": reservation.assigned_vehicle.plate_number if reservation.assigned_vehicle else "",
            "estimated_cost": float(reservation.estimated_cost),
            "status": reservation.status,
        }, message="預約建立成功！")
    except Exception as e:
        return _json_err(str(e))


@require_node("wrent", api=True)
@csrf_exempt
@require_POST
def api_checkout_vehicle(request: HttpRequest) -> JsonResponse:
    """辦理取車出車"""
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        reservation_id = int(payload.get("reservation_id", 0))
        pickup_mileage = payload.get("pickup_mileage")
        pickup_fuel = int(payload.get("pickup_fuel", 100))
        notes = payload.get("notes", "").strip()

        record = BookingService.checkout_vehicle(
            reservation_id=reservation_id,
            pickup_mileage=float(pickup_mileage) if pickup_mileage is not None else None,
            pickup_fuel=pickup_fuel,
            notes=notes,
        )
        return _json_ok({
            "rental_record_id": record.id,
            "plate_number": record.vehicle.plate_number,
            "pickup_mileage": float(record.pickup_mileage),
            "actual_pickup_time": record.actual_pickup_time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": record.status,
        }, message="取車成功，祝您行車平安！")
    except Exception as e:
        return _json_err(str(e))


@require_node("wrent", api=True)
@csrf_exempt
@require_POST
def api_checkin_vehicle(request: HttpRequest) -> JsonResponse:
    """辦理還車驗收與即時帳單出具"""
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        rental_record_id = int(payload.get("rental_record_id", 0))
        return_station_id = int(payload.get("return_station_id", 0))
        return_mileage = float(payload.get("return_mileage", 0))
        return_fuel = int(payload.get("return_fuel", 100))
        notes = payload.get("notes", "").strip()
        discount = float(payload.get("discount_amount", 0.0))

        invoice = BookingService.checkin_vehicle(
            rental_record_id=rental_record_id,
            return_station_id=return_station_id,
            return_mileage=return_mileage,
            return_fuel=return_fuel,
            notes=notes,
            discount_amount=discount,
        )

        return _json_ok({
            "invoice_no": invoice.invoice_no,
            "total_hours_billed": float(invoice.total_hours_billed),
            "total_distance_km": float(invoice.total_distance_km),
            "base_time_fee": float(invoice.base_time_fee),
            "mileage_fee": float(invoice.mileage_fee),
            "overdue_fee": float(invoice.overdue_fee),
            "cross_station_fee": float(invoice.cross_station_fee),
            "insurance_fee": float(invoice.insurance_fee),
            "discount_amount": float(invoice.discount_amount),
            "total_amount": float(invoice.total_amount),
            "payment_status": invoice.payment_status,
        }, message="還車手續辦理完成，帳單已結算！")
    except Exception as e:
        return _json_err(str(e))


@require_node("wrent", api=True)
@require_GET
def api_list_records(request: HttpRequest) -> JsonResponse:
    """查詢預約與租賃行程歷史"""
    reservations = WrentReservation.objects.all().order_by("-id")[:30]
    data = []
    for r in reservations:
        rec = getattr(r, "rental_record", None)
        inv = getattr(rec, "invoice", None) if rec else None
        data.append({
            "reservation_id": r.id,
            "reservation_no": r.reservation_no,
            "user_name": r.user_name,
            "category_name": r.category.name,
            "plate_number": r.assigned_vehicle.plate_number if r.assigned_vehicle else "尚未指派",
            "start_time": r.start_time.strftime("%Y-%m-%d %H:%M"),
            "end_time": r.end_time.strftime("%Y-%m-%d %H:%M"),
            "pickup_station": r.pickup_station.name,
            "return_station": r.return_station.name,
            "estimated_cost": float(r.estimated_cost),
            "status": r.status,
            "rental_record_id": rec.id if rec else None,
            "invoice_no": inv.invoice_no if inv else None,
            "actual_total_amount": float(inv.total_amount) if inv else None,
        })
    return _json_ok({"records": data})
