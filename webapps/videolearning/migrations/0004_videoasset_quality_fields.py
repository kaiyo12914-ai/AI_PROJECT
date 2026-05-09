from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("videolearning", "0003_transcript_chapter_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="videoasset",
            name="fps",
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name="videoasset",
            name="height",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="videoasset",
            name="metadata_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="videoasset",
            name="video_bitrate_kbps",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="videoasset",
            name="width",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
