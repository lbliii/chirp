"""E2 codec family: arbitrary-precision ``numeric`` / ``decimal`` ↔ :class:`decimal.Decimal`.

PostgreSQL's ``numeric`` is a base-10000 ("NBASE") big-decimal: a sign, a base-10000
exponent (``weight``), a display scale (``dscale`` — the number of fractional *decimal*
digits to render), and a run of base-10000 digit groups most-significant first. The binary
wire layout produced by ``numeric_send`` / consumed by ``numeric_recv`` is::

    int16  ndigits   -- count of base-10000 digit groups that follow
    int16  weight    -- base-10000 exponent of the FIRST group (group value = digit * 10000^weight)
    uint16 sign      -- 0x0000 positive, 0x4000 negative,
                        0xC000 NaN, 0xD000 +Infinity, 0xF000 -Infinity (PG14+)
    int16  dscale    -- display scale: number of fractional decimal digits
    uint16[ndigits]  -- base-10000 digit groups, 0..9999, most-significant first

Decoding reconstructs the exact :class:`~decimal.Decimal`, preserving ``dscale`` as the
result's scale (so ``Decimal('1.50')`` round-trips as ``1.50``, not ``1.5``). Encoding goes
the other way: it splits a ``Decimal``'s decimal digits into base-10000 groups aligned on the
decimal point, normalizes off leading/trailing zero groups, and carries the original scale
through ``dscale``. The special-value sign codes carry :data:`~decimal.Decimal` ``NaN`` /
``Infinity`` with no digit groups.

The text format defers to ``Decimal(str)`` — PostgreSQL emits the canonical decimal string.
``prefers_binary`` stays ``True`` so the hot path takes the exact base-10000 route and never
round-trips through a lossy float. This module touches no socket and no anyio: bytes in,
``Decimal`` out.
"""

from __future__ import annotations

import struct
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from chirp.data.drivers._pelt._codecs import Codec
from chirp.data.drivers._pelt.errors import ProtocolError

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- type OID (from pg_type.dat) --------------------------------------------
OID_NUMERIC = 1700

# --- base-10000 ("NBASE") constants -----------------------------------------
_NBASE = 10000
_DEC_DIGITS = 4  # decimal digits per base-10000 group

# --- sign-word codes carried in the uint16 ``sign`` field -------------------
_NUMERIC_POS = 0x0000
_NUMERIC_NEG = 0x4000
_NUMERIC_NAN = 0xC000
_NUMERIC_PINF = 0xD000
_NUMERIC_NINF = 0xF000

# Header = int16 ndigits, int16 weight, uint16 sign, int16 dscale.
_HEADER = struct.Struct(">hhHh")
_DIGIT = struct.Struct(">H")


def _build_decimal(sign_bit: int, unscaled: int, point_exp: int, *, target_exp: int) -> Decimal:
    """Build ``unscaled * 10**point_exp`` exactly with result exponent pinned to ``target_exp``.

    Uses the precision-independent ``Decimal((sign, digit_tuple, exponent))`` constructor — it
    never consults ``getcontext().prec`` and never rounds, so the result is exact regardless of
    which thread runs it (the ambient decimal context is thread-local; relying on it would
    silently round on a worker whose context still carries the default ``prec=28``).

    The display scale ``target_exp = -dscale`` is honored without ever discarding a nonzero
    digit: if it is coarser than ``point_exp`` we append trailing zeros; if it is finer we drop
    trailing *zero* digits, but never below the resolution of the last nonzero digit (PG's
    ``dscale`` always covers every stored fractional digit, so a finer ``point_exp`` only ever
    carries zeros — but we stay exact even if it does not).
    """
    if point_exp >= target_exp:
        # Coarser native exponent: pad zeros so unscaled * 10**point_exp == scaled * 10**target_exp.
        scaled = unscaled * 10 ** (point_exp - target_exp)
        digit_tuple = tuple(int(c) for c in str(scaled))
        return Decimal((sign_bit, digit_tuple, target_exp))
    # Finer native exponent: drop trailing zero digits to reach target_exp, but not past it and
    # never through a nonzero digit. Whatever exponent remains keeps the value bit-exact.
    drop = target_exp - point_exp
    exp = point_exp
    while drop > 0 and unscaled != 0 and unscaled % 10 == 0:
        unscaled //= 10
        exp += 1
        drop -= 1
    digit_tuple = tuple(int(c) for c in str(unscaled))
    return Decimal((sign_bit, digit_tuple, exp))


def _decode_numeric_binary(data: bytes) -> Decimal:
    """Reconstruct an exact :class:`~decimal.Decimal` from the base-10000 wire layout."""
    if len(data) < _HEADER.size:
        msg = f"numeric binary payload too short: {len(data)} byte(s), need >= {_HEADER.size}"
        raise ProtocolError(msg)
    ndigits, weight, sign, dscale = _HEADER.unpack_from(data, 0)

    if sign == _NUMERIC_NAN:
        return Decimal("NaN")
    if sign == _NUMERIC_PINF:
        return Decimal("Infinity")
    if sign == _NUMERIC_NINF:
        return Decimal("-Infinity")
    if sign not in (_NUMERIC_POS, _NUMERIC_NEG):
        msg = f"invalid numeric sign word 0x{sign:04x}"
        raise ProtocolError(msg)

    expected = _HEADER.size + ndigits * _DIGIT.size
    if ndigits < 0 or len(data) < expected:
        msg = (
            f"numeric binary payload truncated: ndigits={ndigits} needs {expected} byte(s), "
            f"have {len(data)}"
        )
        raise ProtocolError(msg)

    groups = [_DIGIT.unpack_from(data, _HEADER.size + i * _DIGIT.size)[0] for i in range(ndigits)]
    for group in groups:
        if group >= _NBASE:
            msg = f"invalid base-10000 digit group {group} (must be < {_NBASE})"
            raise ProtocolError(msg)

    # Build the integer formed by the digit groups (most-significant first), then place the
    # decimal point. The least-significant group sits at base-10000 exponent (weight - ndigits
    # + 1), i.e. decimal exponent _DEC_DIGITS * (weight - ndigits + 1).
    unscaled = 0
    for group in groups:
        unscaled = unscaled * _NBASE + group
    point_exp = _DEC_DIGITS * (weight - ndigits + 1)

    # The exact value is ``unscaled * 10**point_exp``. PostgreSQL renders ``dscale`` fractional
    # digits, so the canonical result exponent is ``-dscale``. We reconstruct via
    # ``Decimal((sign, digit_tuple, exponent))`` — the tuple constructor is *precision-
    # independent*: it never consults ``getcontext().prec`` and never rounds, unlike ``scaleb``
    # or ``quantize`` (which silently round / raise InvalidOperation on a worker thread whose
    # context still carries the default prec=28). This keeps decode exact on every thread under
    # free threading, with no global context mutation.
    sign_bit = 1 if sign == _NUMERIC_NEG else 0
    return _build_decimal(sign_bit, unscaled, point_exp, target_exp=-dscale)


def _decode_numeric_text(data: bytes) -> Decimal:
    return Decimal(data.decode("ascii"))


def _encode_numeric_binary(value: Any) -> bytes:
    """Encode a :class:`~decimal.Decimal` (or numeric-coercible) into the base-10000 layout."""
    dec = value if isinstance(value, Decimal) else Decimal(str(value))

    if dec.is_nan():
        return _HEADER.pack(0, 0, _NUMERIC_NAN, 0)
    if dec.is_infinite():
        sign = _NUMERIC_NINF if dec.is_signed() else _NUMERIC_PINF
        return _HEADER.pack(0, 0, sign, 0)

    sign_word = _NUMERIC_NEG if dec.is_signed() else _NUMERIC_POS
    _sign, digits_tuple, raw_exponent = dec.as_tuple()
    # ``exponent`` is a concrete ``int`` here: the special-value sentinels ('n'/'N'/'F') were
    # already handled by the is_nan()/is_infinite() guards above, so this narrowing is safe.
    exponent = int(raw_exponent)
    # ``dscale`` is the count of fractional decimal digits = -exponent, clamped at 0.
    dscale = -exponent if exponent < 0 else 0

    # Form the unscaled integer from the digit tuple; zero is the dedicated empty-group case
    # (PostgreSQL sends ndigits=0 with the sign + the requested dscale).
    unscaled = 0
    for digit in digits_tuple:
        unscaled = unscaled * 10 + digit
    if unscaled == 0:
        return _HEADER.pack(0, 0, sign_word, dscale)

    # The value equals ``unscaled * 10**exponent``. We render the full run of decimal digits
    # (significant digits plus any trailing zeros for a positive exponent), then align that
    # run on base-10000 group boundaries that sit on multiples of _DEC_DIGITS *decimal places*.
    # ``lo_exp`` is the decimal exponent of the least-significant digit of the rendered run.
    decimal_str = "".join(str(d) for d in digits_tuple)
    if exponent > 0:
        decimal_str += "0" * exponent  # scale up: append trailing zeros, point at the end
    lo_exp = exponent if exponent < 0 else 0  # decimal exponent of the run's last digit

    # A base-10000 group's lowest digit must sit on a decimal exponent that is a multiple of
    # _DEC_DIGITS. ``lsg_exp`` is the largest such multiple <= ``lo_exp`` (floor division floors
    # toward -inf, which is what we want); pad the right end down to it, then pad the left end
    # up so the whole run is an integral number of groups.
    lsg_exp = (lo_exp // _DEC_DIGITS) * _DEC_DIGITS
    right_pad = lo_exp - lsg_exp
    padded = decimal_str + "0" * right_pad
    left_pad = (-len(padded)) % _DEC_DIGITS
    padded = "0" * left_pad + padded

    total_groups = len(padded) // _DEC_DIGITS
    # weight is the base-10000 exponent of the FIRST (most-significant) group.
    weight = lsg_exp // _DEC_DIGITS + total_groups - 1

    groups = [int(padded[i : i + _DEC_DIGITS]) for i in range(0, len(padded), _DEC_DIGITS)]
    # Strip leading zero groups (adjusting weight) and trailing zero groups (weight unchanged).
    start = 0
    while start < len(groups) - 1 and groups[start] == 0:
        start += 1
        weight -= 1
    end = len(groups)
    while end - 1 > start and groups[end - 1] == 0:
        end -= 1
    groups = groups[start:end]

    ndigits = len(groups)
    out = bytearray(_HEADER.pack(ndigits, weight, sign_word, dscale))
    for group in groups:
        out += _DIGIT.pack(group)
    return bytes(out)


def _encode_numeric_text(value: Any) -> bytes:
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    return str(dec).encode("ascii")


def _numeric_codec() -> Codec:
    return Codec(
        oid=OID_NUMERIC,
        name="numeric",
        decode_binary=_decode_numeric_binary,
        decode_text=_decode_numeric_text,
        encode_binary=_encode_numeric_binary,
        encode_text=_encode_numeric_text,
    )


# Every non-parametric codec in this family, ready for the registry to wire uniformly.
LEAF_CODECS: tuple[Codec, ...] = (_numeric_codec(),)


def numeric_codec() -> Codec:
    """The ``numeric``/``decimal`` codec (OID 1700) as a standalone instance."""
    return _numeric_codec()


__all__: Sequence[str] = (
    "LEAF_CODECS",
    "OID_NUMERIC",
    "numeric_codec",
)
