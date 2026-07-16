from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

_SCRIPT = (
    Path(__file__).parents[1]
    / ".agents"
    / "skills"
    / "create-railway-template"
    / "scripts"
    / "audit_public_template.py"
)


def _load_audit_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("audit_public_template", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _variable(value: str) -> dict[str, Any]:
    return {"defaultValue": value, "isOptional": False}


def _postgres_service(
    required_variables: tuple[str, ...], mount_paths: list[str]
) -> dict[str, Any]:
    return {
        "name": "Postgres",
        "source": {"image": "ghcr.io/railwayapp-templates/postgres-ssl:18"},
        "variables": {name: _variable(f"value-for-{name}") for name in required_variables},
        "volumeMounts": {
            f"volume-{index}": {"mountPath": path} for index, path in enumerate(mount_paths)
        },
    }


def _template(services: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "serializedConfig": {
            "services": {f"service-{index}": service for index, service in enumerate(services)}
        }
    }


def _audit_with_mounts(mount_paths: list[str]) -> list[str]:
    audit = _load_audit_module()
    postgres = _postgres_service(audit.POSTGRES_REQUIRED, mount_paths)
    target = _template(
        [
            {
                "name": "web",
                "source": {"repo": "example/chirp-hookbox"},
                "variables": {"DATABASE_URL": _variable("${{Postgres.DATABASE_URL}}")},
            },
            postgres,
        ]
    )
    official = _template([_postgres_service(audit.POSTGRES_REQUIRED, [audit.POSTGRES_MOUNT])])

    def fetch_template(code: str) -> dict[str, Any]:
        return official if code == "postgres" else target

    audit.fetch_template = fetch_template
    return audit.audit("chirp-hookbox", [])


def test_audit_accepts_one_postgres_volume_mount() -> None:
    assert _audit_with_mounts(["/var/lib/postgresql/data"]) == []


def test_audit_rejects_duplicate_postgres_volume_mounts() -> None:
    errors = _audit_with_mounts(["/var/lib/postgresql/data", "/var/lib/postgresql/data"])

    assert "Postgres must define exactly one volume mount; found 2" in errors


def test_audit_requires_exact_generated_secret_expression() -> None:
    audit = _load_audit_module()
    postgres = _postgres_service(
        audit.POSTGRES_REQUIRED,
        [audit.POSTGRES_MOUNT],
    )
    target = _template(
        [
            {
                "name": "web",
                "source": {"repo": "example/chirp-queue"},
                "variables": {
                    "DATABASE_URL": _variable("${{Postgres.DATABASE_URL}}"),
                    "QUEUE_ADMIN_TOKEN": _variable("prefix-secret(32)-suffix"),
                },
            },
            postgres,
        ]
    )
    official = _template([_postgres_service(audit.POSTGRES_REQUIRED, [audit.POSTGRES_MOUNT])])
    audit.fetch_template = lambda code: official if code == "postgres" else target

    errors = audit.audit("chirp-queue", ["web.QUEUE_ADMIN_TOKEN"])

    assert "web.QUEUE_ADMIN_TOKEN must use an exact Railway secret() expression" in errors


def test_audit_accepts_service_qualified_generated_secret() -> None:
    audit = _load_audit_module()
    postgres = _postgres_service(
        audit.POSTGRES_REQUIRED,
        [audit.POSTGRES_MOUNT],
    )
    target = _template(
        [
            {
                "name": "web",
                "source": {"repo": "example/chirp-queue"},
                "variables": {
                    "DATABASE_URL": _variable("${{Postgres.DATABASE_URL}}"),
                    "QUEUE_ADMIN_TOKEN": _variable(
                        '${{ secret(32, "abcdefghijklmnopqrstuvwxyz") }}'
                    ),
                },
            },
            postgres,
        ]
    )
    official = _template([_postgres_service(audit.POSTGRES_REQUIRED, [audit.POSTGRES_MOUNT])])
    audit.fetch_template = lambda code: official if code == "postgres" else target

    assert audit.audit("chirp-queue", ["web.QUEUE_ADMIN_TOKEN"]) == []


def test_audit_rejects_ambiguous_unqualified_generated_variable() -> None:
    audit = _load_audit_module()
    postgres = _postgres_service(
        audit.POSTGRES_REQUIRED,
        [audit.POSTGRES_MOUNT],
    )
    generated = _variable('${{ secret(32, "abcdefghijklmnopqrstuvwxyz") }}')
    target = _template(
        [
            {
                "name": "web",
                "source": {"repo": "example/chirp-queue"},
                "variables": {
                    "DATABASE_URL": _variable("${{Postgres.DATABASE_URL}}"),
                    "SHARED_TOKEN": generated,
                },
            },
            {
                "name": "worker",
                "source": {"repo": "example/chirp-queue"},
                "variables": {"SHARED_TOKEN": generated},
            },
            postgres,
        ]
    )
    official = _template([_postgres_service(audit.POSTGRES_REQUIRED, [audit.POSTGRES_MOUNT])])
    audit.fetch_template = lambda code: official if code == "postgres" else target

    errors = audit.audit("chirp-queue", ["SHARED_TOKEN"])

    assert (
        "generated variable SHARED_TOKEN is ambiguous across web, worker; use SERVICE.VARIABLE"
    ) in errors
