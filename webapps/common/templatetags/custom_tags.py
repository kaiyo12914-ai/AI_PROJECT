from django import template
from django.urls import reverse
from webproj.settings import env_str
from django.templatetags.static import static as django_static

register = template.Library()

@register.simple_tag
def custom_static(path):
    url = django_static(path)
    PROXY_PREFIX=env_str("PROXY_PREFIX", "")
    if PROXY_PREFIX and not url.startswith(PROXY_PREFIX):
        return f"{PROXY_PREFIX}{url}"
    return url