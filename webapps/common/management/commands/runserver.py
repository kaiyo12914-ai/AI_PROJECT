from __future__ import annotations

import os
import sys
from django.core.management.commands.runserver import (
    Command as DjangoRunserverCommand,
    get_docs_version,
)


class Command(DjangoRunserverCommand):
    """
    Project runserver override:
    - Hide system-check banner lines by default.
    - Hide datetime/Django-version/settings lines by default.
    - Keep "Starting development server at ...".

    Toggle behavior with env vars:
    - RUNSERVER_SHOW_CHECKS=1  -> show "Performing system checks..." block.
    - RUNSERVER_SHOW_BANNER=1  -> show original Django banner in full.
    """

    def inner_run(self, *args, **options):
        if (os.environ.get("RUNSERVER_SHOW_CHECKS", "0") or "").strip().lower() not in (
            "1",
            "true",
            "yes",
            "on",
        ):
            options["skip_checks"] = True
        return super().inner_run(*args, **options)

    def on_bind(self, server_port):
        show_banner = (os.environ.get("RUNSERVER_SHOW_BANNER", "0") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if show_banner:
            return super().on_bind(server_port)

        if self._raw_ipv6:
            addr = f"[{self.addr}]"
        elif self.addr == "0":
            addr = "0.0.0.0"
        else:
            addr = self.addr

        quit_command = "CTRL-BREAK" if sys.platform == "win32" else "CONTROL-C"
        self.stdout.write(f"Starting development server at {self.protocol}://{addr}:{server_port}/")
        self.stdout.write(f"Quit the server with {quit_command}.")

        if os.environ.get("DJANGO_RUNSERVER_HIDE_WARNING") != "true":
            docs_version = get_docs_version()
            self.stdout.write(
                self.style.WARNING(
                    "WARNING: This is a development server. Do not use it in a "
                    "production setting. Use a production WSGI or ASGI server "
                    "instead.\nFor more information on production servers see: "
                    f"https://docs.djangoproject.com/en/{docs_version}/howto/"
                    "deployment/"
                )
            )
