# tests/e2e/wrent/test_wrent_workflow.py
import json
import pytest
from datetime import timedelta
from django.utils import timezone
from django.test import Client

from webapps.wrent.models import (
    WrentStation,
    WrentVehicleCategory,
    WrentVehicle,
    WrentReservation,
    WrentRentalRecord,
    WrentBillingInvoice,
)


@pytest.mark.django_db
def test_wrent_full_lifecycle_workflow():
    client = Client()

    # 1. 準備基礎設施
    station = WrentStation.objects.create(
        station_code="ST-E2E-MAIN",
        name="信義旗艦站",
        address="台北市信義區松高路1號",
    )
    category = WrentVehicleCategory.objects.create(
        category_code="SUV-E2E",
        name="旗艦休旅車",
        hourly_rate=180.00,
        daily_cap_rate=1800.00,
        mileage_rate=3.80,
        overdue_hourly_rate=250.00,
    )
    vehicle = WrentVehicle.objects.create(
        plate_number="E2E-8888",
        category=category,
        current_station=station,
        model_name="Toyota RAV4 Hybrid",
        status="AVAILABLE",
        current_mileage=5000.00,
        fuel_or_battery_level=100,
    )

    now = timezone.now()
    start_dt = now + timedelta(hours=1)
    end_dt = start_dt + timedelta(hours=4)

    # 2. 建立預約 (Reservation)
    res_payload = {
        "user_name": "王大明",
        "user_phone": "0988-123-456",
        "category_id": category.id,
        "pickup_station_id": station.id,
        "return_station_id": station.id,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "has_insurance": False,
        "vehicle_id": vehicle.id,
    }

    res_create = client.post(
        "/wrent/api/reservations/",
        data=json.dumps(res_payload),
        content_type="application/json",
    )
    assert res_create.status_code == 200
    create_data = res_create.json()
    assert create_data["status"] == "ok"
    reservation_id = create_data["data"]["reservation_id"]
    assert create_data["data"]["plate_number"] == "E2E-8888"

    # 3. 辦理取車核驗 (Checkout)
    checkout_payload = {
        "reservation_id": reservation_id,
        "pickup_mileage": 5000.0,
        "pickup_fuel": 100,
        "notes": "全車檢視良好，鑰匙已交給顧客",
    }
    res_checkout = client.post(
        "/wrent/api/checkout/",
        data=json.dumps(checkout_payload),
        content_type="application/json",
    )
    assert res_checkout.status_code == 200
    checkout_data = res_checkout.json()
    assert checkout_data["status"] == "ok"
    rental_record_id = checkout_data["data"]["rental_record_id"]

    # 驗證車輛狀態為 RENTED
    vehicle.refresh_from_db()
    assert vehicle.status == "RENTED"

    # 4. 辦理還車驗收與結算 (Checkin)
    checkin_payload = {
        "rental_record_id": rental_record_id,
        "return_station_id": station.id,
        "return_mileage": 5080.0,  # 行駛 80 公里
        "return_fuel": 90,
        "notes": "準時歸還，油箱尚有 90%",
        "discount_amount": 0.0,
    }
    res_checkin = client.post(
        "/wrent/api/checkin/",
        data=json.dumps(checkin_payload),
        content_type="application/json",
    )
    assert res_checkin.status_code == 200
    checkin_data = res_checkin.json()
    assert checkin_data["status"] == "ok"

    invoice_info = checkin_data["data"]
    assert invoice_info["total_distance_km"] == 80.0
    # 里程費 80 * 3.8 = 304.0
    assert invoice_info["mileage_fee"] == 304.0
    assert invoice_info["payment_status"] == "PAID"

    # 5. 驗證資料庫狀態閉環
    vehicle.refresh_from_db()
    assert vehicle.status == "CLEANING"
    assert float(vehicle.current_mileage) == 5080.0
    assert vehicle.fuel_or_battery_level == 90

    reservation = WrentReservation.objects.get(id=reservation_id)
    assert reservation.status == "COMPLETED"

    # 驗證歷史紀錄端點包含此筆資料
    res_records = client.get("/wrent/api/records/")
    assert res_records.status_code == 200
    records_data = res_records.json()
    assert len(records_data["data"]["records"]) >= 1
