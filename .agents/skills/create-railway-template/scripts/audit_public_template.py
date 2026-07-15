#!/usr/bin/env python3
"""Audit a public Railway template for zero-input Chirp deployment."""

from __future__ import annotations

import argparse
import http.client
import json
import sys
from typing import Any

HOST = "backboard.railway.com"
PATH = "/graphql/v2"
QUERY = """
query template($code: String!) {
  template(code: $code) { id code name serializedConfig }
}
"""
POSTGRES_REQUIRED = (
    "PGDATA",
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGDATABASE",
    "PGPASSWORD",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "RAILWAY_DEPLOYMENT_DRAINING_SECONDS",
)
POSTGRES_MOUNT = "/var/lib/postgresql/data"


def fetch_template(code: str) -> dict[str, Any]:
    payload = json.dumps({"query": QUERY, "variables": {"code": code}}).encode()
    connection = http.client.HTTPSConnection(HOST, timeout=20)
    try:
        connection.request(
            "POST",
            PATH,
            body=payload,
            headers={
                "content-type": "application/json",
                "user-agent": "chirp-railway-template-audit/1",
            },
        )
        response = connection.getresponse()
        if response.status >= 400:
            raise OSError(f"Railway returned HTTP {response.status}")
        result = json.loads(response.read())
    finally:
        connection.close()
    if result.get("errors"):
        raise RuntimeError(result["errors"][0].get("message", "Railway query failed"))
    template = result.get("data", {}).get("template")
    if not template:
        raise RuntimeError(f"Railway template {code!r} was not found")
    return template


def services(template: dict[str, Any]) -> list[dict[str, Any]]:
    config = template.get("serializedConfig") or {}
    return list((config.get("services") or {}).values())


def postgres_service(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for service in items:
        image = str((service.get("source") or {}).get("image") or "").lower()
        if "postgres" in image:
            return service
    return None


def default(variable: dict[str, Any] | None) -> str:
    if not variable:
        return ""
    value = variable.get("defaultValue")
    return value if isinstance(value, str) else ""


def normalized(value: str) -> str:
    return "".join(value.split())


def audit(code: str, required_generated: list[str]) -> list[str]:
    target = fetch_template(code)
    target_services = services(target)
    official_postgres = postgres_service(services(fetch_template("postgres")))
    target_postgres = postgres_service(target_services)
    errors: list[str] = []

    if not target_services:
        return ["template defines no services"]

    for service in target_services:
        service_name = service.get("name") or "<unnamed>"
        for name, variable in (service.get("variables") or {}).items():
            if not variable.get("isOptional", False) and not default(variable):
                errors.append(f"{service_name}.{name} has no default")

    if target_postgres is None:
        errors.append("template has no PostgreSQL service")
    elif official_postgres is None:
        errors.append("Railway official postgres template could not be identified")
    else:
        target_vars = target_postgres.get("variables") or {}
        official_vars = official_postgres.get("variables") or {}
        for name in POSTGRES_REQUIRED:
            expected = default(official_vars.get(name))
            actual = default(target_vars.get(name))
            if normalized(actual) != normalized(expected):
                errors.append(f"Postgres.{name} default differs from Railway official postgres")
        required_mount = (target_postgres.get("deploy") or {}).get("requiredMountPath")
        if required_mount not in (None, POSTGRES_MOUNT):
            errors.append(f"Postgres requiredMountPath must be {POSTGRES_MOUNT}")
        mounts = target_postgres.get("volumeMounts") or {}
        if len(mounts) != 1:
            errors.append(f"Postgres must define exactly one volume mount; found {len(mounts)}")
        if POSTGRES_MOUNT not in {
            value.get("mountPath") for value in mounts.values() if isinstance(value, dict)
        }:
            errors.append(f"Postgres volume must mount at {POSTGRES_MOUNT}")

        postgres_name = target_postgres.get("name") or "Postgres"
        expected_reference = f"${{{{{postgres_name}.DATABASE_URL}}}}"
        app_references = [
            default((service.get("variables") or {}).get("DATABASE_URL"))
            for service in target_services
            if service is not target_postgres
        ]
        if normalized(expected_reference) not in {normalized(value) for value in app_references}:
            errors.append(f"application DATABASE_URL must reference {expected_reference}")

    all_variables = {
        name: variable
        for service in target_services
        for name, variable in (service.get("variables") or {}).items()
    }
    for name in required_generated:
        value = default(all_variables.get(name))
        if "secret(" not in normalized(value):
            errors.append(f"{name} must use a Railway secret() default")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template_code")
    parser.add_argument(
        "--require-generated",
        action="append",
        default=[],
        metavar="NAME",
        help="require NAME to have a Railway secret() default; repeat as needed",
    )
    args = parser.parse_args()

    try:
        errors = audit(args.template_code, args.require_generated)
    except (OSError, RuntimeError, ValueError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2

    if errors:
        for error in errors:
            sys.stdout.write(f"FAIL: {error}\n")
        return 1
    sys.stdout.write(f"PASS: {args.template_code} is configured for zero-input deployment\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
