"""Starter designs for new templates. Inline styles only: mail clients strip <style> blocks and most CSS.

Each body goes inside the standard layout (header with the organisation's name, footer with address and unsubscribe),
so these hold only the message itself.
"""

_BUTTON = (
    '<p style="margin:24px 0"><a href="https://example.org" style="display:inline-block;background:#1f5fbf;'
    'color:#ffffff;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:6px">{label}</a></p>'
)

STARTERS = [
    {
        "key": "newsletter",
        "name": "Newsletter",
        "description": "A greeting, a lead story and two short updates.",
        "subject": "{{name}}, here is what is new at AFS",
        "preheader": "Our latest stories and updates.",
        "body_html": (
            "<p>Dear {{name}},</p>"
            "<p>Here is a short round-up of what has happened at AFS this month.</p>"
            '<h2 style="font-size:20px;margin:24px 0 8px">Lead story</h2>'
            "<p>Write two or three sentences that make the reader want to know more.</p>"
            + _BUTTON.format(label="Read the full story")
            + '<h3 style="font-size:17px;margin:20px 0 6px">Update one</h3>'
            "<p>A short paragraph about the second item.</p>"
            '<h3 style="font-size:17px;margin:20px 0 6px">Update two</h3>'
            "<p>A short paragraph about the third item.</p>"
            "<p>With best wishes,<br>The AFS team</p>"
        ),
    },
    {
        "key": "announcement",
        "name": "Announcement",
        "description": "One piece of news with a clear call to action.",
        "subject": "Announcing: [your news]",
        "preheader": "One thing we want you to know about.",
        "body_html": (
            "<p>Dear {{name}},</p>"
            '<h1 style="font-size:24px;line-height:1.3;margin:8px 0 12px">Your headline goes here</h1>'
            "<p>Explain the news in a few sentences: what it is, why it matters, and what happens next.</p>"
            + _BUTTON.format(label="Find out more")
            + "<p>Thank you,<br>The AFS team</p>"
        ),
    },
    {
        "key": "event",
        "name": "Event invitation",
        "description": "Date, place and a button to register.",
        "subject": "You are invited: [event name]",
        "preheader": "Join us on [date].",
        "body_html": (
            "<p>Dear {{name}},</p>"
            "<p>We would be delighted if you could join us.</p>"
            '<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:#f3f4f6;'
            'border-radius:8px;margin:16px 0"><tr><td style="padding:16px 20px">'
            "<strong>[Event name]</strong><br>Date: [date and time]<br>Place: [venue, Kigali]</td></tr></table>"
            "<p>Tell people what to expect and who will be there.</p>"
            + _BUTTON.format(label="Register now")
            + "<p>We look forward to seeing you,<br>The AFS team</p>"
        ),
    },
    {
        "key": "media_invite",
        "name": "Media invitation to join AFS",
        "description": "For media contacts: their blog account and how to join.",
        "subject": "{{name}}, an invitation to write with AFS",
        "preheader": "Your AFS blog account is ready.",
        "body_html": (
            "<p>Dear {{name}},</p>"
            "<p>As a journalist with {{organisation}}, we would like to invite you to join the Alliance for Science "
            "Rwanda network of media correspondents.</p>"
            "<p>A blog account has been prepared for you at {{email}}. Sign up with this address to start "
            "publishing and to receive our story briefs.</p>"
            + _BUTTON.format(label="Join AFS")
            + "<p>Kind regards,<br>The AFS communications team</p>"
        ),
    },
    {
        "key": "information_request",
        "name": "Information request",
        "description": "Asks staff or partners to update their details. Includes the personal form link.",
        "subject": "{{name}}, please confirm your details",
        "preheader": "It takes two minutes.",
        "body_html": (
            "<p>Dear {{name}},</p>"
            "<p>We are updating our records so that we can work with {{organisation}} more easily. "
            "Please take two minutes to check and complete your details.</p>"
            '<p style="margin:24px 0"><a href="{{form_url}}" style="display:inline-block;background:#1f5fbf;'
            'color:#ffffff;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:6px">'
            "Update my details</a></p>"
            "<p>The link is personal and works once, for 30 days.</p>"
            "<p>Thank you,<br>The AFS team</p>"
        ),
    },
    {
        "key": "plain",
        "name": "Plain letter",
        "description": "Text only, like a personal email.",
        "subject": "",
        "preheader": "",
        "body_html": "<p>Dear {{name}},</p><p></p><p>Kind regards,<br>The AFS team</p>",
    },
]
