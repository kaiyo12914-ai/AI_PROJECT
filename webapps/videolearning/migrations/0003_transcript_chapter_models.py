from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("videolearning", "0002_playlist_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="VideoTranscript",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "source_type",
                    models.CharField(
                        choices=[("manual", "Manual"), ("upload", "Upload"), ("ai", "AI")],
                        default="upload",
                        max_length=20,
                    ),
                ),
                (
                    "format",
                    models.CharField(
                        choices=[("txt", "TXT"), ("srt", "SRT"), ("vtt", "VTT")],
                        default="txt",
                        max_length=10,
                    ),
                ),
                ("language", models.CharField(blank=True, default="zh-Hant", max_length=16)),
                ("content", models.TextField()),
                ("cues_json", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "video",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transcripts",
                        to="videolearning.videoasset",
                    ),
                ),
            ],
            options={
                "db_table": "videolearning_transcript",
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="VideoChapter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("summary", models.TextField(blank=True, default="")),
                ("start_seconds", models.PositiveIntegerField()),
                ("end_seconds", models.PositiveIntegerField()),
                ("order_index", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "transcript",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="chapters",
                        to="videolearning.videotranscript",
                    ),
                ),
                (
                    "video",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chapters",
                        to="videolearning.videoasset",
                    ),
                ),
            ],
            options={
                "db_table": "videolearning_chapter",
                "ordering": ["order_index", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="videochapter",
            constraint=models.UniqueConstraint(
                fields=("video", "order_index"),
                name="videolearning_chapter_unique_order_in_video",
            ),
        ),
    ]
