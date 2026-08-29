# webapps/wrent/urls.py
from __future__ import annotations

from django.urls import path
from webapps.wrent import views, views_api

app_name = "wrent"

urlpatterns = [
    path("", views.index_view, name="index"),
    # APIs
    path("api/meta/", views_api.api_get_meta, name="api_meta"),
    path("api/vehicles/available/", views_api.api_get_available_vehicles, name="api_vehicles_available"),
    path("api/quote/", views_api.api_calculate_quote, name="api_quote"),
    path("api/reservations/", views_api.api_create_reservation, name="api_create_reservation"),
    path("api/checkout/", views_api.api_checkout_vehicle, name="api_checkout"),
    path("api/checkin/", views_api.api_checkin_vehicle, name="api_checkin"),
    path("api/records/", views_api.api_list_records, name="api_records"),
]
