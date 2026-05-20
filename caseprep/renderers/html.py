"""Pure HTML renderers for CasePrep artifacts."""

from __future__ import annotations


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
