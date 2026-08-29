# tests/integration/wrent/test_wrent_api.py
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
)


@pytest.mark.django_db
def test_wrent_api_meta_and_quote():
    client = Client()

    # 1. 建立測試站點與車型
    station_a = WrentStation.objects.create(
        station_code="ST-TEST-01",
        name="台北車站站",
        address="台北市中正區北平西路3號",
        capacity=10,
    )
    station_b = WrentStation.objects.create(
        station_code="ST-TEST-02",
        name="板橋站",
        address="新北市板橋區縣民大道二段7號",
        capacity=8,
    )
    cat_compact = WrentVehicleCategory.objects.create(
        category_code="SEDAN-TEST",
        name="經濟型轎車",
        hourly_rate=120.00,
        daily_cap_rate=1200.00,
        mileage_rate=3.20,
        overdue_hourly_rate=180.00,
    )

    # 2. 測試 GET /wrent/api/meta/
    res_meta = client.get("/wrent/api/meta/")
    assert res_meta.status_code == 200
    data_meta = res_meta.json()
    assert data_meta["status"] == "ok"
    assert len(data_meta["data"]["stations"]) >= 2
    assert len(data_meta["data"]["categories"]) >= 1

    # 3. 測試 POST /wrent/api/quote/ (3 小時 + 跨站 + 安心險)
    now = timezone.now()
    start_dt = now + timedelta(hours=2)
    end_dt = start_dt + timedelta(hours=3)

    quote_payload = {
        "category_id": cat_compact.id,
        "pickup_station_id": station_a.id,
        "return_station_id": station_b.id,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "has_insurance": True,
    }
    res_quote = client.post(
        "/wrent/api/quote/",
        data=json.dumps(quote_payload),
        content_type="application/json",
    )
    assert res_quote.status_code == 200
    data_quote = res_quote.json()
    assert data_quote["status"] == "ok"
    # 3 小時 * 120 = 360，跨站 200，保險 150 -> 710
    assert data_quote["data"]["total_estimated"] == 710.0
