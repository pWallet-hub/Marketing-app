"""Template placeholders. Only the keys below are allowed, and values are escaped when they go into HTML."""

import re
from html import escape

ALLOWED_KEYS = ("name", "organisation", "email", "unsubscribe_url", "form_url")
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


class TemplateError(ValueError):
    pass


def unknown_placeholders(text):
    return sorted({key for key in _PLACEHOLDER.findall(text) if key not in ALLOWED_KEYS})


def render(text, values, html=True):
    def substitute(match):
        value = str(values.get(match.group(1), ""))
        return escape(value, quote=True) if html else value

    return _PLACEHOLDER.sub(substitute, text)


def html_to_text(html):
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h[1-6])>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
