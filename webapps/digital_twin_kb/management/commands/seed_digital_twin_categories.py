from django.core.management.base import BaseCommand

from webapps.digital_twin_kb.category_services import seed_digital_twin_categories


class Command(BaseCommand):
    help = "Seed digital twin category data."

    def handle(self, *args, **options):
        seed_digital_twin_categories()
        self.stdout.write(self.style.SUCCESS("Digital twin categories seeded."))
