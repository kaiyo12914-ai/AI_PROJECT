from django.urls import path

from . import views
from . import views_speech

app_name = "englishchat"

urlpatterns = [
    path("", views.index, name="page"),
    path("start/", views.api_start, name="start"),
    path("chat/", views.api_chat, name="chat"),
    path("quiz/fill_blank/", views.api_fill_blank_quiz, name="fill_blank_quiz"),
    path("quiz/check/", views.api_check_fill_blank, name="check_fill_blank"),
    path("quiz/reorder/", views.api_reorder_quiz, name="reorder_quiz"),
    path("quiz/reorder/check/", views.api_check_reorder, name="check_reorder"),
    path("quiz/translate/", views.api_translation_quiz, name="translation_quiz"),
    path("quiz/translate/evaluate/", views.api_evaluate_translation, name="evaluate_translation"),
    path("practice/summary/", views.api_practice_summary, name="practice_summary"),
    path("speech/tts/", views_speech.api_speech_tts, name="speech_tts"),
    path("speech/stt/", views_speech.api_speech_stt, name="speech_stt"),
    path("speech/evaluate/", views_speech.api_speech_evaluate, name="speech_evaluate"),
]

