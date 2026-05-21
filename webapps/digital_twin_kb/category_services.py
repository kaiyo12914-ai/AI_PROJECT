from .models import DigitalTwinCategory
from .taxonomy.knowledge_schema import DIGITAL_TWIN_LEVELS


def seed_digital_twin_categories():
    for item in DIGITAL_TWIN_LEVELS:
        DigitalTwinCategory.objects.update_or_create(
            twin_level=item["twin_level"],
            defaults={
                "level_name": item["level_name"],
                "description": item["description"],
                "related_systems": item["related_systems"],
                "example_data": item["example_data"],
                "use_cases": item["use_cases"],
            },
        )
