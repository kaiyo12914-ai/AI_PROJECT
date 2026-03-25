from __future__ import annotations

import json
from pathlib import Path

import typer

from webapps.text2pptx.pptx2schema.evaluators.similarity import rough_similarity_score
from webapps.text2pptx.pptx2schema.evaluators.visual_diff import diff_stub
from webapps.text2pptx.pptx2schema.pipelines.analyze_pipeline import run_analyze
from webapps.text2pptx.pptx2schema.pipelines.extract_pipeline import run_extract
from webapps.text2pptx.pptx2schema.pipelines.render_pipeline import run_render
from webapps.text2pptx.pptx2schema.template_cleaner.cleaner import clean_template_assets

app = typer.Typer(help="PPTX reverse engineering and reconstruction tool")


@app.command()
def extract(input_path: str, output_path: str) -> None:
    result = run_extract(input_path, source_file=input_path)
    Path(output_path).write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    typer.echo(f"Saved to {output_path}")


@app.command()
def analyze(input_path: str, output_path: str) -> None:
    result = run_analyze(input_path)
    Path(output_path).write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    typer.echo(f"Saved to {output_path}")


@app.command()
def render(schema_path: str, content_path: str, output_path: str) -> None:
    run_render(schema_path, content_path, output_path)
    typer.echo(f"Saved PPTX to {output_path}")


@app.command()
def diff(base_path: str, candidate_path: str, output_path: str) -> None:
    base = run_extract(base_path)
    cand = run_extract(candidate_path)
    report = {
        "similarity": rough_similarity_score(
            base_slide_count=base.meta.slide_count,
            candidate_slide_count=cand.meta.slide_count,
        ),
        "visual": diff_stub(),
    }
    Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"Saved diff report to {output_path}")


@app.command("clean-template")
def clean_template(input_path: str, output_pptx_path: str, output_schema_path: str) -> None:
    schema = clean_template_assets(
        input_pptx=input_path,
        output_cleaned_pptx=output_pptx_path,
        output_schema_json=output_schema_path,
        source_file=input_path,
    )
    typer.echo(f"Saved cleaned template to {output_pptx_path}")
    typer.echo(f"Saved template schema to {output_schema_path}")
    typer.echo(
        "Policy summary: "
        f"total={schema.keep_remove_policy_summary.total_shapes}, "
        f"keep={schema.keep_remove_policy_summary.kept_shapes}, "
        f"clear_text={schema.keep_remove_policy_summary.cleared_text_shapes}, "
        f"remove={schema.keep_remove_policy_summary.removed_shapes}"
    )


if __name__ == "__main__":
    app()
