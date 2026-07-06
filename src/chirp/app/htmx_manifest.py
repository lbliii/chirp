"""Frozen internal provisioning records for managed htmx assets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from chirp.errors import ConfigurationError

HTMX_ROLLBACK_VERSION = "2.0.10"
HTMX4_PREVIEW_VERSION = "4.0.0-beta5"
_CDN = "https://cdn.jsdelivr.net/npm"


@dataclass(frozen=True, slots=True)
class HtmxAsset:
    """One exact browser asset in the managed htmx bundle."""

    role: Literal["core", "compat", "sse"]
    url: str
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class HtmxClientPolicy:
    """Immutable browser-default contract for one managed htmx tier."""

    no_swap_statuses: tuple[int | str, ...]
    default_timeout_ms: int
    inheritance: Literal["implicit-compat", "explicit"]
    history: Literal["cache", "refetch"]
    oob_order: Literal["oob-first", "main-first"]
    delete_form_data: Literal["implicit", "explicit"]
    queue: Literal["trigger-modifier", "hx-sync"]
    compat_swap_error_responses: bool = False


@dataclass(frozen=True, slots=True)
class HtmxProvisioningManifest:
    """One freeze-time htmx provisioning decision published to runtime readers."""

    enabled: bool
    tier: Literal["disabled", "2-managed", "4-preview"]
    version: str
    assets: tuple[HtmxAsset, ...]
    compatibility_features: tuple[str, ...] = ()
    rollback_version: str = HTMX_ROLLBACK_VERSION
    client_policy: HtmxClientPolicy | None = None


def _asset(version: str, role: Literal["core", "compat", "sse"], path: str) -> HtmxAsset:
    return HtmxAsset(role=role, url=f"{_CDN}/htmx.org@{version}/{path}")


def compile_htmx_manifest(*, enabled: bool, version: str) -> HtmxProvisioningManifest:
    """Compile the configured htmx pin into one immutable runtime truth."""
    if not enabled:
        return HtmxProvisioningManifest(
            enabled=False,
            tier="disabled",
            version=version,
            assets=(),
        )

    if version == HTMX4_PREVIEW_VERSION:
        return HtmxProvisioningManifest(
            enabled=True,
            tier="4-preview",
            version=version,
            assets=(
                HtmxAsset(
                    role="core",
                    url=f"{_CDN}/htmx.org@{version}/dist/htmx.min.js",
                    sha256="192d2d425dda6834bd15973a10f55940cea217a3a840f3f819ffd16063be9a68",
                ),
                HtmxAsset(
                    role="compat",
                    url=f"{_CDN}/htmx.org@{version}/dist/ext/htmx-2-compat.min.js",
                    sha256="7d7fe881d6ae6d4e661b0113e8504bb15acfc1dc1970f07db109bb20c432e53d",
                ),
                HtmxAsset(
                    role="sse",
                    url=f"{_CDN}/htmx.org@{version}/dist/ext/hx-sse.min.js",
                    sha256="fcc844a52779d8450c1c4796feea8d038943f908b9ee974322c276230e6c86cc",
                ),
            ),
            compatibility_features=("htmx-2-compat", "native-sse"),
            client_policy=HtmxClientPolicy(
                no_swap_statuses=(204, 304, "5xx"),
                default_timeout_ms=60_000,
                inheritance="implicit-compat",
                history="refetch",
                oob_order="main-first",
                delete_form_data="explicit",
                queue="hx-sync",
                compat_swap_error_responses=True,
            ),
        )

    lowered = version.lower()
    if lowered == "4" or lowered.startswith(("4.", "4-", "v4")):
        msg = (
            f"Unsupported htmx 4 preview pin {version!r}. "
            f"Use the exact provisional pin {HTMX4_PREVIEW_VERSION!r}, or roll back to "
            f"the verified baseline {HTMX_ROLLBACK_VERSION!r}."
        )
        raise ConfigurationError(msg)

    # Preserve the pre-existing contract for explicitly selected non-4 pins.
    return HtmxProvisioningManifest(
        enabled=True,
        tier="2-managed",
        version=version,
        assets=(_asset(version, "core", "dist/htmx.min.js"),),
    )
