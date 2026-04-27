from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DocumentFormalizeLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.CharField(blank=True, default="", max_length=64)),
                ("user_name", models.CharField(blank=True, default="", max_length=128)),
                ("mode", models.CharField(max_length=32)),
                ("options_json", models.JSONField(blank=True, default=dict)),
                ("input_chars", models.IntegerField(default=0)),
                ("output_chars", models.IntegerField(default=0)),
                ("processing_ms", models.IntegerField(default=0)),
                ("status", models.CharField(default="ok", max_length=16)),
                ("source_masked", models.TextField(blank=True, default="")),
                ("result_masked", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-id"]},
        ),
    ]

