"""Generate structured case-prep output folder."""

import webbrowser
from pathlib import Path

from .links import build_search_links
from .renderers.html import render_resource_links_html
from .schema import build_caseprep_schema, render_caseprep_files

# Template sections for each generated markdown file.
# {topic} is replaced with the user-supplied topic string.

TEMPLATES: dict[str, str] = {
    "README.md": """\
# {topic}

## Case Overview

- **Topic:** {topic}
- **Date:** (fill in)
- **Presenter:** (fill in)

## Quick Reference

- See `anatomy.md` for relevant anatomy.
- See `approach.md` for surgical approach details.
- See `literature.md` for key papers and search links.
- See `complications.md` for potential complications.
- Open `resource-links.html` in a browser for direct search links.
""",
    "anatomy.md": """\
# Relevant Anatomy — {topic}

## Key Structures

- (list relevant structures)

## Vascular Supply

- (arteries, veins)

## Adjacent / At-Risk Structures

- (nerves, tracts, cisterns)

## Anatomic Variants

- (common variants to be aware of)
""",
    "approach.md": """\
# Surgical Approach — {topic}

## Approach Selection

- **Approach:**
- **Rationale:**

## Positioning

- (supine, prone, lateral, sitting, etc.)

## Key Steps

1.
2.
3.

## Intraoperative Monitoring

- (SSEP, MEP, EMG, BAER, etc.)

## Pitfalls

- (common errors and how to avoid them)
""",
    "literature.md": """\
# Literature Review — {topic}

## Search Links

{search_links}

## Key Papers

### Landmark / Classic

- (citation, key findings)

### Recent / Relevant

- (citation, key findings)

## Guidelines

- (society guidelines, class of evidence)
""",
    "complications.md": """\
# Potential Complications — {topic}

## Intraoperative

- (vascular injury, neurological deficit, etc.)

## Postoperative

- (CSF leak, infection, hematoma, etc.)

## Long-Term

- (recurrence, radiation effects, etc.)

## Risk Mitigation

- (prevention strategies for each category)
""",
}

RESOURCE_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Resource Links — {topic}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 700px; margin: 2em auto; padding: 0 1em; }}
  h1 {{ font-size: 1.4em; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ margin: 0.5em 0; }}
  a {{ color: #1a56db; }}
</style>
</head>
<body>
<h1>Resource Links — {topic}</h1>
<ul>
{link_items}
</ul>
</body>
</html>
"""


def _slugify(topic: str) -> str:
    """Turn a topic string into a filesystem-safe slug."""
    return topic.strip().lower().replace(" ", "-")


def _link_items_html(links: dict[str, str]) -> str:
    return "\n".join(
        f'  <li><a href="{url}" target="_blank" rel="noopener">{name}</a></li>'
        for name, url in links.items()
    )


def _search_links_markdown(links: dict[str, str]) -> str:
    return "\n".join(f"- [{name}]({url})" for name, url in links.items())


def generate_caseprep(
    topic: str,
    output_dir: Path,
    *,
    open_browser: bool = False,
) -> Path:
    """Create a case-prep folder and populate it with structured files.

    Returns the path to the generated resource-links.html file.
    """
    slug = _slugify(topic)
    out = Path(output_dir)
    if not out.is_absolute():
        out = Path.cwd() / out
    out.mkdir(parents=True, exist_ok=True)

    links = build_search_links(topic)

    schema = build_caseprep_schema(topic)
    rendered_files = render_caseprep_files(
        schema,
        literature_summary="## Search Links\n\n" + _search_links_markdown(links),
    )
    for filename, content in rendered_files.items():
        (out / filename).write_text(content, encoding="utf-8")

    # resource-links.html
    html_content = render_resource_links_html(topic, links)
    resource_path = out / "resource-links.html"
    resource_path.write_text(html_content, encoding="utf-8")

    if open_browser:
        webbrowser.open(str(resource_path))

    return resource_path
