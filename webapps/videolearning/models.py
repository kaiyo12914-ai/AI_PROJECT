from django.db import models


class VideoCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "videolearning_category"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class VideoTag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "videolearning_tag"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class VideoAsset(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PROCESSING = "processing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    VISIBILITY_PRIVATE = "private"
    VISIBILITY_DEPT = "department"
    VISIBILITY_PUBLIC = "public"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private"),
        (VISIBILITY_DEPT, "Department"),
        (VISIBILITY_PUBLIC, "Public"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.ForeignKey(
        VideoCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="videos",
    )
    tags = models.ManyToManyField(VideoTag, blank=True, related_name="videos")
    file_path = models.CharField(max_length=1024)
    thumbnail_path = models.CharField(max_length=1024, blank=True, default="")
    duration_seconds = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    fps = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    video_bitrate_kbps = models.PositiveIntegerField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    owner = models.CharField(max_length=128, blank=True, default="")
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default=VISIBILITY_PRIVATE,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "videolearning_asset"
        ordering = ["-updated_at", "-id"]

    def __str__(self) -> str:
        return f"{self.id}:{self.title}"


class VideoPlaylist(models.Model):
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_DEPT = "department"
    VISIBILITY_PUBLIC = "public"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private"),
        (VISIBILITY_DEPT, "Department"),
        (VISIBILITY_PUBLIC, "Public"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    owner = models.CharField(max_length=128, blank=True, default="")
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default=VISIBILITY_PRIVATE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "videolearning_playlist"
        ordering = ["-updated_at", "-id"]

    def __str__(self) -> str:
        return f"{self.id}:{self.title}"


class VideoPlaylistItem(models.Model):
    playlist = models.ForeignKey(
        VideoPlaylist,
        on_delete=models.CASCADE,
        related_name="items",
    )
    video = models.ForeignKey(
        VideoAsset,
        on_delete=models.CASCADE,
        related_name="playlist_items",
    )
    order_index = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "videolearning_playlist_item"
        ordering = ["order_index", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["playlist", "video"],
                name="videolearning_playlist_item_unique_video_in_playlist",
            ),
            models.UniqueConstraint(
                fields=["playlist", "order_index"],
                name="videolearning_playlist_item_unique_order_in_playlist",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.playlist_id}:{self.video_id}@{self.order_index}"


class VideoTranscript(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_UPLOAD = "upload"
    SOURCE_AI = "ai"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_UPLOAD, "Upload"),
        (SOURCE_AI, "AI"),
    ]

    FORMAT_TXT = "txt"
    FORMAT_SRT = "srt"
    FORMAT_VTT = "vtt"
    FORMAT_CHOICES = [
        (FORMAT_TXT, "TXT"),
        (FORMAT_SRT, "SRT"),
        (FORMAT_VTT, "VTT"),
    ]

    video = models.ForeignKey(
        VideoAsset,
        on_delete=models.CASCADE,
        related_name="transcripts",
    )
    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_UPLOAD,
    )
    format = models.CharField(
        max_length=10,
        choices=FORMAT_CHOICES,
        default=FORMAT_TXT,
    )
    language = models.CharField(max_length=16, blank=True, default="zh-Hant")
    content = models.TextField()
    cues_json = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "videolearning_transcript"
        ordering = ["-updated_at", "-id"]

    def __str__(self) -> str:
        return f"{self.video_id}:{self.format}:{self.id}"


class VideoChapter(models.Model):
    video = models.ForeignKey(
        VideoAsset,
        on_delete=models.CASCADE,
        related_name="chapters",
    )
    transcript = models.ForeignKey(
        VideoTranscript,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chapters",
    )
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, default="")
    start_seconds = models.PositiveIntegerField()
    end_seconds = models.PositiveIntegerField()
    order_index = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "videolearning_chapter"
        ordering = ["order_index", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["video", "order_index"],
                name="videolearning_chapter_unique_order_in_video",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.video_id}:{self.order_index}:{self.title}"
