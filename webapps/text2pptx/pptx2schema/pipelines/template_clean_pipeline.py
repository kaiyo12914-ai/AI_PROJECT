from __future__ import annotations

from pathlib import Path

from webapps.text2pptx.pptx2schema.template_cleaner.cleaner import clean_template_assets
from webapps.text2pptx.pptx2schema.template_cleaner.models import CleanerConfig, TemplateCleanerSchema


def run_template_clean(
    input_pptx: str | Path,
    output_cleaned_pptx: str | Path,
    output_schema_json: str | Path,
    *,
    source_file: str | None = None,
    config: CleanerConfig | None = None,
) -> TemplateCleanerSchema:
    return clean_template_assets(
        input_pptx=input_pptx,
        output_cleaned_pptx=output_cleaned_pptx,
        output_schema_json=output_schema_json,
        source_file=source_file or str(input_pptx),
        config=config,
    )

