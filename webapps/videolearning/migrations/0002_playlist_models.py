from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("videolearning", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="VideoPlaylist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("owner", models.CharField(blank=True, default="", max_length=128)),
                (
                    "visibility",
                    models.CharField(
                        choices=[("private", "Private"), ("department", "Department"), ("public", "Public")],
                        default="private",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "videolearning_playlist",
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="VideoPlaylistItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order_index", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "playlist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="videolearning.videoplaylist",
                    ),
                ),
                (
                    "video",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="playlist_items",
                        to="videolearning.videoasset",
                    ),
                ),
            ],
            options={
                "db_table": "videolearning_playlist_item",
                "ordering": ["order_index", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="videoplaylistitem",
            constraint=models.UniqueConstraint(
                fields=("playlist", "video"),
                name="videolearning_playlist_item_unique_video_in_playlist",
            ),
        ),
        migrations.AddConstraint(
            model_name="videoplaylistitem",
            constraint=models.UniqueConstraint(
                fields=("playlist", "order_index"),
                name="videolearning_playlist_item_unique_order_in_playlist",
            ),
        ),
    ]
