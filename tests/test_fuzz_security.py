"""Property-based (Hypothesis) fuzzing for the security normalizers.

Targets three attacker-influenced surfaces:

- ``is_safe_url`` — open-redirect guard for redirect targets.
- ``_sanitize_upload_filename`` — basename hardening for multipart uploads.
- ``SSEEvent.encode`` — Server-Sent Events wire framing.

These are *invariant* tests: they assert properties that must hold for every
input, so they fail loudly if a normalizer regresses (e.g. a new bypass for the
safe-URL guard, a traversal escape in the filename sanitizer, or a framing /
event-injection break in the SSE encoder).
"""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from chirp.http.forms import _sanitize_upload_filename
from chirp.realtime.events import SSEEvent
from chirp.security.urls import is_safe_url

# ---------------------------------------------------------------------------
# is_safe_url — generated off-site targets must never be accepted.
# ---------------------------------------------------------------------------

# Bytes a browser strips from the *start* of a URL before resolving it.
_LEADING_NOISE = st.text(alphabet="".join(chr(c) for c in range(0x21)) + "\x7f", max_size=6)
# Slash-ish authority introducers a browser may normalize ("\" -> "/").
_SLASHES = st.lists(st.sampled_from(["/", "\\"]), min_size=2, max_size=4).map("".join)
_SCHEMES = st.sampled_from(
    ["http", "https", "ftp", "javascript", "data", "vbscript", "file", "HtTpS"]
)
_HOSTS = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-",
    min_size=1,
    max_size=20,
).filter(lambda h: h not in (".", ".."))


@st.composite
def offsite_targets(draw: st.DrawFn) -> str:
    """Generate redirect targets that all point off the current origin.

    Every value here, once browser-normalized (leading control/whitespace
    stripped, "\\" -> "/"), is either protocol-relative ("//host") or carries an
    explicit scheme ("scheme://host") — i.e. it leaves the origin. None of them
    may ever be accepted by ``is_safe_url``.
    """
    noise = draw(_LEADING_NOISE)
    host = draw(_HOSTS)
    kind = draw(st.sampled_from(["protocol_relative", "scheme", "leading_backslash"]))
    if kind == "protocol_relative":
        body = draw(_SLASHES) + host
    elif kind == "scheme":
        scheme = draw(_SCHEMES)
        body = f"{scheme}://{host}"
    else:  # leading_backslash — "\host" / "\\host" normalize to /host or //host
        body = draw(st.sampled_from(["\\", "\\\\", "\\/", "/\\"])) + host
    return noise + body


@given(offsite_targets())
def test_is_safe_url_rejects_offsite(target: str) -> None:
    assert is_safe_url(target) is False


@given(st.text())
def test_is_safe_url_never_raises_and_returns_bool(value: str) -> None:
    # Total function: any string yields a bool, never an exception.
    assert isinstance(is_safe_url(value), bool)


@given(st.text())
def test_is_safe_url_accepts_imply_same_origin_path(value: str) -> None:
    """If accepted, the browser-normalized form is a single-slash root path.

    This is the core safety contract: an accepted value can never resolve to a
    protocol-relative ("//") or scheme ("://") target after the browser applies
    the same control-strip + backslash normalization the guard models.
    """
    if not is_safe_url(value):
        return
    leading = "".join(chr(c) for c in range(0x21)) + "\x7f"
    normalized = value.lstrip(leading).replace("\\", "/")
    assert normalized.startswith("/")
    assert not normalized.startswith("//")
    assert "://" not in normalized


# ---------------------------------------------------------------------------
# _sanitize_upload_filename — traversal/null/separator inputs stay basename.
# ---------------------------------------------------------------------------

_FILENAME_ALPHABET = st.text(
    alphabet=st.characters(
        # Include the dangerous bytes deliberately so the strategy probes them.
        codec="utf-8",
        exclude_categories=("Cs",),  # surrogates are not valid filename content
    ),
    max_size=60,
)


@given(_FILENAME_ALPHABET)
def test_sanitized_filename_has_no_separators_or_nul(raw: str) -> None:
    safe = _sanitize_upload_filename(raw)
    assert "/" not in safe
    assert "\\" not in safe
    assert "\x00" not in safe


@given(_FILENAME_ALPHABET)
def test_sanitized_filename_is_never_traversal(raw: str) -> None:
    safe = _sanitize_upload_filename(raw)
    # The sanitized name can never be a traversal token or empty — it is a leaf
    # basename usable inside a chosen directory without escaping it.
    assert safe not in ("", ".", "..")


@given(_FILENAME_ALPHABET)
def test_sanitized_filename_cannot_escape_chosen_dir(raw: str) -> None:
    """Joining the sanitized name onto a base dir never escapes that dir."""
    from pathlib import PurePosixPath

    base = PurePosixPath("/srv/uploads")
    safe = _sanitize_upload_filename(raw)
    # The sanitized name is a single path component, so joining it onto the base
    # directory yields exactly one extra part and never re-roots or escapes.
    composed = base / safe
    assert ".." not in composed.parts
    assert composed.parts[: len(base.parts)] == base.parts
    assert len(composed.parts) == len(base.parts) + 1


@given(st.lists(st.sampled_from(["..", ".", "etc", "passwd", "x"]), min_size=1, max_size=6))
def test_traversal_payloads_reduce_to_basename(parts: list[str]) -> None:
    for sep in ("/", "\\"):
        payload = sep.join(parts)
        safe = _sanitize_upload_filename(payload)
        assert "/" not in safe
        assert "\\" not in safe
        assert safe not in ("", ".", "..")


# ---------------------------------------------------------------------------
# SSEEvent.encode — CR/LF/NUL must not break framing or inject a 2nd event.
# ---------------------------------------------------------------------------

# Text that intentionally includes the framing-hostile bytes. Built from
# fragments (not a char alphabet) so multi-char tokens like CRLF and blank-line
# separators are exercised — these are exactly what could break SSE framing.
_SSE_FRAGMENTS = st.one_of(
    st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E), max_size=8),
    st.sampled_from(["\r", "\n", "\x00", "\r\n", "\r\n\r\n", "\n\n", "\x00\n", "data: x"]),
)
_SSE_TEXT = st.lists(_SSE_FRAGMENTS, max_size=12).map("".join)
# event/id reject CR/LF/NUL at construction, so generate clean header values.
_SSE_HEADER = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    max_size=40,
)


def _parse_sse_frames(wire: str) -> list[dict[str, list[str]]]:
    """Parse an SSE byte stream into discrete events per the WHATWG spec.

    Events are separated by a blank line. Returns one dict per dispatched
    event, mapping field name -> list of field values (in order).
    """
    events: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {}
    have_field = False
    # The spec dispatches on a blank line; lines are split on LF (encode()
    # normalizes CR/CRLF -> LF first, so a raw stream uses LF separators).
    for line in wire.split("\n"):
        if line == "":
            if have_field:
                events.append(current)
            current = {}
            have_field = False
            continue
        have_field = True
        if ":" in line:
            field, _, val = line.partition(":")
            if val.startswith(" "):
                val = val[1:]
        else:
            field, val = line, ""
        current.setdefault(field, []).append(val)
    return events


@given(data=_SSE_TEXT, event=st.none() | _SSE_HEADER, ident=st.none() | _SSE_HEADER)
def test_sse_encode_emits_exactly_one_event(
    data: str, event: str | None, ident: str | None
) -> None:
    evt = SSEEvent(data=data, event=event or None, id=ident or None)
    wire = evt.encode()
    frames = _parse_sse_frames(wire)
    # Exactly one dispatched event — no injection of a second frame regardless
    # of CR/LF/NUL in the data payload.
    assert len(frames) == 1
    # The reconstructed data (LF-joined per spec) round-trips the payload after
    # the encoder's documented CR/CRLF -> LF normalization.
    expected = data.replace("\r\n", "\n").replace("\r", "\n")
    reconstructed = "\n".join(frames[0].get("data", []))
    assert reconstructed == expected


@given(data=_SSE_TEXT, event=st.none() | _SSE_HEADER, ident=st.none() | _SSE_HEADER)
def test_sse_encode_has_no_bare_cr(data: str, event: str | None, ident: str | None) -> None:
    # A stray CR could let a proxy/client resync mid-frame; the encoder must
    # collapse all CR into LF so the wire form contains no carriage returns.
    wire = SSEEvent(data=data, event=event or None, id=ident or None).encode()
    assert "\r" not in wire


@given(data=_SSE_TEXT)
def test_sse_encode_no_blank_line_before_terminator(data: str) -> None:
    """No interior blank line: only the single trailing terminator is blank.

    An interior blank line would dispatch (and thus split) the event early.
    """
    wire = SSEEvent(data=data).encode()
    # Each frame ends with a single blank-line terminator ("\n\n"): the "" line
    # encode() appends, plus the final "\n". That is the only blank line.
    assert wire.endswith("\n\n")
    lines = wire.split("\n")
    # split() on the trailing "\n\n" yields two empty tail entries; every
    # *interior* line must be non-blank, or an event would dispatch early.
    interior = lines[:-2]
    assert all(line != "" for line in interior)


@given(event=_SSE_HEADER, ident=_SSE_HEADER)
def test_sse_header_fields_reject_framing_chars(event: str, ident: str) -> None:
    # Sanity: clean headers construct fine and never carry CR/LF/NUL through.
    assume(not any(c in event for c in "\r\n\x00"))
    assume(not any(c in ident for c in "\r\n\x00"))
    wire = SSEEvent(data="ok", event=event or None, id=ident or None).encode()
    assert "\r" not in wire


@st.composite
def header_with_framing_char(draw: st.DrawFn) -> str:
    """A header string guaranteed to contain at least one CR/LF/NUL byte.

    Built constructively (clean prefix/suffix + a guaranteed framing char)
    rather than by filtering, so generation stays cheap and the invariant —
    "contains a framing char" — always holds.
    """
    clean = st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E), max_size=8)
    prefix = draw(clean)
    bad_char = draw(st.sampled_from(["\r", "\n", "\x00"]))
    suffix = draw(clean)
    return prefix + bad_char + suffix


@given(bad=header_with_framing_char())
def test_sse_event_field_raises_on_framing_chars(bad: str) -> None:
    # event/id carrying CR/LF/NUL must be rejected at construction, not silently
    # smuggled into the wire form where they could inject fields/events.
    assert any(c in bad for c in "\r\n\x00")  # invariant the strategy guarantees
    with pytest.raises(ValueError, match="must not contain"):
        SSEEvent(data="ok", event=bad)
    with pytest.raises(ValueError, match="must not contain"):
        SSEEvent(data="ok", id=bad)
