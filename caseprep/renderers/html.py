"""Pure HTML renderers for CasePrep artifacts."""

from __future__ import annotations

import html as _html


def render_bound_images_html(schema: dict) -> str:
    """HTML <figure> blocks for image-bank figures bound to the imaging section."""
    section = schema.get("imaging_review")
    if not isinstance(section, dict):
        return ""
    bound = section.get("bound_images") or []
    if not bound:
        return ""
    parts: list[str] = ['<section class="bound-images"><h3>Prep Images From Image Bank</h3>']
    for img in bound:
        caption = _html.escape(str(img.get("caption", "")))
        path = _html.escape(str(img.get("local_path", "")))
        pmcid = _html.escape(str(img.get("pmcid", "")))
        link = (
            f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else ""
        )
        src_html = (
            f' — source: <a href="{link}">{pmcid}</a>' if link else ""
        )
        parts.append(
            f'<figure><img src="{path}" alt="{caption}">'
            f"<figcaption>{caption}{src_html}</figcaption></figure>"
        )
    parts.append("</section>")
    return "\n".join(parts)


def render_resource_links_html(topic: str, links: dict[str, str]) -> str:
    """Render the resource-links HTML artifact."""
    items = "\n".join(
        f'  <li><a href="{url}" target="_blank" rel="noopener">{name}</a></li>'
        for name, url in links.items()
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>Resource Links — {topic}</title>\n"
        "<style>\n"
        "  body { font-family: system-ui, sans-serif; max-width: 700px; margin: 2em auto; padding: 0 1em; }\n"
        "  h1 { font-size: 1.4em; }\n"
        "  ul { list-style: none; padding: 0; }\n"
        "  li { margin: 0.5em 0; }\n"
        "  a { color: #1a56db; }\n"
        "</style>\n</head>\n<body>\n"
        f"<h1>Resource Links — {topic}</h1>\n<ul>\n{items}\n</ul>\n"
        "</body>\n</html>\n"
    )
