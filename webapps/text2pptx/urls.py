from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="pptx_page"),
    path("generate/", views.generate_pptx, name="pptx_generate"),
]
