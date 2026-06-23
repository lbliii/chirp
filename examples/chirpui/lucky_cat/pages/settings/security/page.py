"""Settings → Security — GET /settings/security.

Passkey enrollment for the signed-in demo trader plus the remaining security
stub toggles (non-mutating GET form).
"""

import passkey_store

from chirp import Page, login_required


@login_required
def get() -> Page:
    from chirp import current_user

    user = current_user()
    return Page(
        "settings/security/page.html",
        "page_content",
        page_block_name="page_root",
        passkeys=passkey_store.list_for_user(user.id),
    )
