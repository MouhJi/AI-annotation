from html import escape

APP_NAME = "Data Annotation Platform"


def action_email(kind, url, name="", workspace=""):
    """No external assets; escape all user-controlled text and URL attributes."""
    if kind == "verification":
        heading, button, subject = "Welcome! Verify your email", "Verify Email", f"Verify your email — {APP_NAME}"
        description = "Confirm your email address to receive workspace invitations and collaborate with your team."
        expiry = "This single-use link expires in 24 hours."
    elif kind == "password_reset":
        heading, button, subject = "Reset your password", "Reset Password", f"Reset your password — {APP_NAME}"
        description = "We received a request to reset your password. Choose a new password using the link below."
        expiry = "This single-use link expires in 30 minutes."
    elif kind == "invitation":
        heading, button, subject = "You are invited to a workspace", "View Invitation", f"Workspace invitation — {APP_NAME}"
        description = f"You have been invited to {workspace}. Sign in with this email address and verify it before accepting."
        expiry = "This single-use invitation expires in 7 days."
    else:
        raise ValueError("Unknown email template")
    greeting = f"Hello {name}," if name else "Hello,"
    security = "If you did not request this email, you can safely ignore it."
    text = f"{APP_NAME}\n\n{greeting}\n{heading}\n{description}\n\n{button}:\n{url}\n\n{expiry}\n{security}\n"
    html = f'''<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;background:#f0f9ff;font-family:Arial,sans-serif;color:#0f172a">
<table role="presentation" style="width:100%;padding:24px 12px"><tr><td align="center">
<table role="presentation" style="width:100%;max-width:560px;background:#fff;border:1px solid #bae6fd;border-radius:16px;padding:28px">
<tr><td><p style="color:#0284c7;font-weight:bold">{APP_NAME}</p><p>{escape(greeting)}</p>
<h1 style="font-size:24px;line-height:1.3">{escape(heading)}</h1><p style="line-height:1.6">{escape(description)}</p>
<p style="padding:18px 0"><a href="{escape(url, quote=True)}" style="background:#0284c7;color:#fff;text-decoration:none;padding:14px 24px;border-radius:8px;display:inline-block;font-weight:bold">{escape(button)}</a></p>
<p>{escape(expiry)}</p><p style="font-size:13px;color:#475569">If the button does not work, open this link:</p>
<p style="overflow-wrap:anywhere;font-size:12px"><a href="{escape(url, quote=True)}">{escape(url)}</a></p>
<p style="border-top:1px solid #e2e8f0;padding-top:16px;color:#64748b;font-size:12px">{security}</p>
</td></tr></table></td></tr></table></body></html>'''
    return subject, text, html
