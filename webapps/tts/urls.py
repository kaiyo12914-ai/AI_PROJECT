
from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="tts_page"),

    # Text -> Speech
    path("generate/", views.api_tts_generate, name="tts_generate"),
    path("generate_from_file/", views.api_tts_generate_from_file, name="tts_generate_from_file"),

    # Speech -> Text
    path("transcribe/", views.api_stt_transcribe, name="stt_transcribe"),

    # 匯出
    path("export_txt/", views.api_export_txt, name="stt_export_txt"),
    path("export_docx/", views.api_export_docx, name="stt_export_docx"),

]