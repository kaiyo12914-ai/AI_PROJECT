from django.urls import path

from . import views

app_name = "videolearning"

urlpatterns = [
    path("", views.index, name="page"),
    path("import/", views.import_page, name="import_page"),
    path("transcode/", views.transcode_page, name="transcode_page"),
    path("videos/<int:video_id>/", views.detail, name="detail"),
    path("api/health/", views.api_health, name="api_health"),
    path("api/videos/", views.api_video_list, name="api_video_list"),
    path("api/videos/<int:video_id>/", views.api_video_detail, name="api_video_detail"),
    path("api/videos/upload/", views.api_video_upload, name="api_video_upload"),
    path("api/videos/import-youtube/", views.api_video_import_youtube, name="api_video_import_youtube"),
    path("api/videos/create/", views.api_video_create, name="api_video_create"),
    path("api/videos/<int:video_id>/update/", views.api_video_update, name="api_video_update"),
    path("api/videos/<int:video_id>/delete/", views.api_video_delete, name="api_video_delete"),
    path(
        "api/videos/<int:video_id>/transcript/upload/",
        views.api_transcript_upload,
        name="api_transcript_upload",
    ),
    path(
        "api/videos/<int:video_id>/chapters/",
        views.api_chapter_list,
        name="api_chapter_list",
    ),
    path(
        "api/videos/<int:video_id>/chapters/generate/",
        views.api_chapter_generate,
        name="api_chapter_generate",
    ),
    path("api/playlists/", views.api_playlist_list, name="api_playlist_list"),
    path("api/playlists/create/", views.api_playlist_create, name="api_playlist_create"),
    path("api/playlists/<int:playlist_id>/", views.api_playlist_detail, name="api_playlist_detail"),
    path(
        "api/playlists/<int:playlist_id>/add-video/",
        views.api_playlist_add_video,
        name="api_playlist_add_video",
    ),
    path(
        "api/playlists/<int:playlist_id>/reorder/",
        views.api_playlist_reorder,
        name="api_playlist_reorder",
    ),
]
