from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from nl2sql_sync_oracle_schema import build_arg_parser, main


_ARG_PARSER = build_arg_parser()
_ARG_DESTS = {
    action.dest
    for action in _ARG_PARSER._actions
    if action.option_strings and action.dest != "help"
}


class Command(BaseCommand):
    help = "Sync Oracle CT_*/DT_* tables/views/materialized views into nl2sql_schema_object and nl2sql_schema_embedding."

    def add_arguments(self, parser):
        for action in _ARG_PARSER._actions:
            if action.option_strings and action.dest != "help":
                parser._add_action(action)

    def handle(self, *args, **options):
        argv: list[str] = []
        for key, value in options.items():
            if key not in _ARG_DESTS:
                continue
            if isinstance(value, bool):
                if value:
                    argv.append(f"--{key.replace('_', '-')}")
                continue
            if value is None or value == "":
                continue
            argv.extend([f"--{key.replace('_', '-')}", str(value)])

        try:
            return main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if code == 0:
                return 0
            raise CommandError(str(exc)) from exc
