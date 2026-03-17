from django.apps import AppConfig
import os


def _patch_staticfiles_handler_for_forced_script_name() -> None:
    """
    Django's dev StaticFilesHandler resolves files from request.path.
    With FORCE_SCRIPT_NAME and unstripped PATH_INFO this can become
    "/prefix/prefix/static/..." and break safe_join on Windows.
    Use request.path_info for static path extraction to avoid double-prefix.
    """
    try:
        from django.conf import settings
        from django.contrib.staticfiles.handlers import StaticFilesHandlerMixin
        from django.contrib.staticfiles.views import serve as static_serve
    except Exception:
        return

    force_script_name = getattr(settings, "FORCE_SCRIPT_NAME", None)
    if not force_script_name:
        return

    serve_fn = getattr(StaticFilesHandlerMixin, "serve", None)
    if getattr(serve_fn, "__name__", "") == "_serve_from_path_info":
        return

    def _serve_from_path_info(self, request):
        return static_serve(request, self.file_path(request.path_info), insecure=True)

    StaticFilesHandlerMixin.serve = _serve_from_path_info


class PortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "webapps.portal"
    label = "portal"

    def ready(self):
        _patch_staticfiles_handler_for_forced_script_name()
        
        # 啟動時列印 LLM 引用狀態 (僅在主 reloader 進程執行，避免雙重列印)
        import os  # Explicit local import to prevent NameError
        if os.environ.get('RUN_MAIN') == 'true':
            try:
                from webapps.llm.llm_factory import log_llm_config
                log_llm_config()
            except Exception:
                pass
