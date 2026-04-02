"""Auto-generated schema migrations.

Chirp's migration system: schema-from-SQL, not dataclass-to-schema.
Diffs your desired SQL against the current database to generate forward migrations.

Usage::

    chirp makemigrations --db sqlite:///app.db --schema schema.py
"""

from chirp.data.schema.diff import diff_schemas
from chirp.data.schema.generate import generate_migration
from chirp.data.schema.introspect import introspect
from chirp.data.schema.parse import parse_schema
from chirp.data.schema.types import SchemaSnapshot

__all__ = [
    "SchemaSnapshot",
    "diff_schemas",
    "generate_migration",
    "introspect",
    "parse_schema",
]
