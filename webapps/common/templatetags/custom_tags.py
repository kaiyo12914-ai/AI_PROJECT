from django import template
from django.urls import reverse
from django.templatetags.static import static as django_static

register = template.Library()

@register.simple_tag(takes_context=True)
def custom_static(context, path):
    url = django_static(path)
    request = context.get("request")
    prefix = (getattr(request, "script_name", "") or "").rstrip("/")
    if prefix and url.startswith("/") and not url.startswith("//"):
        if url != prefix and not url.startswith(prefix + "/"):
            return f"{prefix}{url}"
    return url
