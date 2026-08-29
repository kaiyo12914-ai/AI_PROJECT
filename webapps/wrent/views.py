# webapps/wrent/views.py
from __future__ import annotations

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse

from webapps.portal.decorators import require_node
from webapps.wrent.models import WrentStation, WrentVehicleCategory, WrentVehicle


@require_node("wrent")
def index_view(request: HttpRequest) -> HttpResponse:
    """WRent 租車預約計費系統主頁面"""
    stations = WrentStation.objects.filter(is_active=True).order_id() if hasattr(WrentStation.objects, "order_id") else WrentStation.objects.filter(is_active=True).order_by("id")
    categories = WrentVehicleCategory.objects.all().order_by("id")
    vehicles = WrentVehicle.objects.select_related("category", "current_station").filter(is_active=True).order_by("id")

    context = {
        "app_base_url": request.script_name or "",
        "stations": stations,
        "categories": categories,
        "vehicles": vehicles,
    }
    return render(request, "wrent/index.html", context)
