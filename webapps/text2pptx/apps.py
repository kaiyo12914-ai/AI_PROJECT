from django.apps import AppConfig
import logging


logger = logging.getLogger(__name__)

class Text2PptxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "webapps.text2pptx"
    _pptx_checked = False

    def ready(self):
        if Text2PptxConfig._pptx_checked:
            return
        Text2PptxConfig._pptx_checked = True
        try:
            import pptx  # noqa: F401
        except Exception as e:
            logger.error("text2pptx startup check failed: python-pptx unavailable: %s", e)
