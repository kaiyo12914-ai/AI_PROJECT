from django.urls import path
from . import views

urlpatterns = [
    path("", views.graph_page, name="graph_page"),
    path("build_text/", views.graph_build_text, name="graph_build_text"),
]
