from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="VideoCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "videolearning_category",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="VideoTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "videolearning_tag",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="VideoAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("file_path", models.CharField(max_length=1024)),
                ("thumbnail_path", models.CharField(blank=True, default="", max_length=1024)),
                ("duration_seconds", models.PositiveIntegerField(default=0)),
                ("owner", models.CharField(blank=True, default="", max_length=128)),
                (
                    "visibility",
                    models.CharField(
                        choices=[("private", "Private"), ("department", "Department"), ("public", "Public")],
                        default="private",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("processing", "Processing"),
                            ("ready", "Ready"),
                            ("failed", "Failed"),
                            ("archived", "Archived"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="videos",
                        to="videolearning.videocategory",
                    ),
                ),
                ("tags", models.ManyToManyField(blank=True, related_name="videos", to="videolearning.videotag")),
            ],
            options={
                "db_table": "videolearning_asset",
                "ordering": ["-updated_at", "-id"],
            },
        ),
    ]
