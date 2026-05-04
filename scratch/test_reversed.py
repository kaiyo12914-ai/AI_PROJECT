import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from webapps.projectnotes.models import Message
qs = Message.objects.all().order_by("-created_at")[:6]
try:
    for m in reversed(qs):
        pass
    print("Success")
except Exception as e:
    print("Error:", type(e), e)
