# webapps/excelproc/urls.py
from django.urls import path
from . import views

app_name = "excelproc"

urlpatterns = [
    # =========================
    # page
    # =========================
    path("", views.index, name="page"),

    # ✅ alias：給 portal/index.html 用
    path("", views.index, name="excelproc_page"),

    # =========================
    # actions
    # =========================
    path("run/", views.run, name="run"),
]
