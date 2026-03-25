# pptx2schema (Integrated MVP)

`pptx2schema` is integrated under `webapps/text2pptx` so it can be used by the existing Django `text2pptx` subsystem.

## Goals (MVP)

- Extract raw slide/shape/text/theme structure from `.pptx`
- Build semantic slide hints and template DNA
- Render a simple new pptx from bundle schema + new content

## CLI

```bash
python -m webapps.text2pptx.pptx2schema.cli extract in.pptx out.raw.json
python -m webapps.text2pptx.pptx2schema.cli analyze in.pptx out.bundle.json
python -m webapps.text2pptx.pptx2schema.cli render out.bundle.json new_content.json out.new.pptx
python -m webapps.text2pptx.pptx2schema.cli diff base.pptx candidate.pptx out.diff.json
python -m webapps.text2pptx.pptx2schema.cli clean-template in.pptx out.cleaned_template.pptx out.template_schema.json
```

## Django integration

- API endpoint: `text2pptx/schema/extract/`
- Accepts uploaded `.pptx` and returns `PresentationRaw` JSON.

## Template cleaner

`pptx_template_cleaner` is implemented in:

- `webapps/text2pptx/pptx2schema/template_cleaner/`

Output artifacts:

- `cleaned_template.pptx`
- `template_schema.json`

Core behavior:

- keeps placeholders but clears placeholder text
- removes most one-off content shapes
- keeps repeated decorative shapes
- removes images by default unless repeated large background-like assets
