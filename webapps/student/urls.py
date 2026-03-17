from django.urls import path
from . import views

urlpatterns = [
    # page
    path("", views.index, name="student_page"),

    # downloads (for index.html buttons)
    path("download/txt/", views.download_txt, name="student_download_txt"),
    path("download/csv/", views.download_csv, name="student_download_csv"),
    path("download/word/", views.download_word, name="student_download_word"),
]
