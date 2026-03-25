from __future__ import annotations

from pathlib import Path

from webapps.text2pptx.pptx2schema.template_cleaner.cleaner import clean_template_assets


def main() -> None:
    src = Path("input.pptx")
    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)
    cleaned = out_dir / "cleaned_template.pptx"
    schema = out_dir / "template_schema.json"
    result = clean_template_assets(
        input_pptx=src,
        output_cleaned_pptx=cleaned,
        output_schema_json=schema,
        source_file=str(src),
    )
    print("cleaned template:", cleaned)
    print("schema:", schema)
    print("shapes:", result.keep_remove_policy_summary.total_shapes)


if __name__ == "__main__":
    main()

