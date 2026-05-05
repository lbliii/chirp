"""Shared networked benchmark payloads."""

from dataclasses import dataclass

JSON_PAYLOAD = {"message": "hello", "count": 42}
TEMPLATE_TITLE = "Benchmark Items"


@dataclass(frozen=True, slots=True)
class TemplateItem:
    name: str
    value: int


TEMPLATE_ITEMS = tuple(TemplateItem(name=f"Item {i}", value=i) for i in range(20))

KIDA_TEMPLATE = """
<main>
  <h1>{{ title }}</h1>
  <ul>
    {% for item in items %}
    <li><span>{{ item.name }}</span><strong>{{ item.value }}</strong></li>
    {% end %}
  </ul>
</main>
""".strip()

JINJA_TEMPLATE = """
<main>
  <h1>{{ title }}</h1>
  <ul>
    {% for item in items %}
    <li><span>{{ item.name }}</span><strong>{{ item.value }}</strong></li>
    {% endfor %}
  </ul>
</main>
""".strip()


def cpu_work(iterations: int = 50_000) -> int:
    """CPU-bound work: repeated hashing."""
    h = 0
    for i in range(iterations):
        h = hash((h, i))
    return h
