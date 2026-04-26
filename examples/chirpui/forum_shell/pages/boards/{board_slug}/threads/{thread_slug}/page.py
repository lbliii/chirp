from dataclasses import dataclass

from forum_store import store

from chirp import OOB, Fragment, Page, Request, form_from
from chirp.contracts import FormContract, contract


@dataclass(frozen=True, slots=True)
class ReplyForm:
    character_id: int
    body: str
    mention_ids: list[int]


def _context(thread_slug: str):
    thread = store.thread(thread_slug)
    return {
        "thread": thread,
        "characters": store.characters(),
        "character_name": store.character_name,
        "unread_count": store.unread_count(),
    }


def get(thread_slug: str):
    return Page.mounted(
        "boards/{board_slug}/threads/{thread_slug}/page.html",
        **_context(thread_slug),
    )


@contract(
    form=FormContract(
        ReplyForm,
        "boards/{board_slug}/threads/{thread_slug}/page.html",
        "reply_form",
    )
)
async def post(request: Request, thread_slug: str):
    form = await form_from(request, ReplyForm)
    store.reply(
        thread_slug,
        character_id=form.character_id,
        body=form.body,
        mention_ids=form.mention_ids,
    )
    template = "boards/{board_slug}/threads/{thread_slug}/page.html"
    context = _context(thread_slug)
    return OOB(
        Page.mounted(template, **context),
        Fragment("_layout.html", "unread_count_oob", target="forum-unread-count", **context),
    )
