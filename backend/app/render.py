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


_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def email_layout(body_html, *, org_name, brand_color, org_address="", org_website="", preheader="", footer_html=""):
    """Wrap a message body in the standard branded email: hidden preheader, header band, white card, footer.

    Tables and inline styles are used because mail clients (Outlook in particular) ignore most CSS. Values that come
    from settings are escaped; the body and footer are trusted HTML built by this app.
    """
    color = brand_color if _COLOR.match(brand_color or "") else "#1f5fbf"
    name = escape(org_name)
    address = f'<div style="margin-top:6px">{escape(org_address)}</div>' if org_address else ""
    website = (
        f'<div style="margin-top:6px"><a href="{escape(org_website, quote=True)}" style="color:#6b7280">'
        f"{escape(org_website.removeprefix('https://').removeprefix('http://'))}</a></div>"
        if org_website
        else ""
    )
    hidden = (
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all">'
        f"{escape(preheader)}{'&nbsp;&zwnj;' * 40}</div>"
        if preheader
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{name}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;-webkit-text-size-adjust:100%">
{hidden}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px">
<tr><td style="background:{color};border-radius:10px 10px 0 0;padding:18px 28px;font:600 18px/1.3 Arial,Helvetica,sans-serif;color:#ffffff">{name}</td></tr>
<tr><td style="background:#ffffff;padding:28px;font:16px/1.6 Arial,Helvetica,sans-serif;color:#1f2937;border-radius:0 0 10px 10px">
{body_html}
</td></tr>
<tr><td style="padding:18px 28px;font:12px/1.5 Arial,Helvetica,sans-serif;color:#6b7280;text-align:center">
<div style="font-weight:600">{name}</div>{address}{website}{footer_html}
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""
