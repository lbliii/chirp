"""Dependency index mapping context paths to template blocks."""

from __future__ import annotations

from typing import Any

from kida import Environment

from chirp.pages.reactive.events import BlockRef, _extract_sse_swap_elements


class DependencyIndex:
    """Maps context paths to the template blocks that depend on them.

    Built at app startup from kida's ``BlockMetadata.depends_on`` sets.
    Thread-safe after construction (read-only).

    Supports **derived paths** — computed relationships between context
    paths.  When a source path changes, all paths derived from it are
    automatically included in the affected set::

        index = DependencyIndex()
        index.register_template(env, "doc/{doc_id}/_layout.html")
        index.derive("doc.word_count", from_paths={"doc.content"})

        # Changing "doc.content" now also invalidates blocks that
        # depend on "doc.word_count", without the store needing to
        # know about derived paths.
        affected = index.affected_blocks(frozenset({"doc.content"}))

    Derivations are transitive: if A derives from B and B derives
    from C, changing C invalidates both B and A.
    """

    __slots__ = ("_path_to_blocks", "_prefix_to_paths", "_source_to_derived")

    def __init__(self) -> None:
        # context_path -> list of BlockRef
        self._path_to_blocks: dict[str, list[BlockRef]] = {}
        # source_path -> list of derived paths that depend on it
        self._source_to_derived: dict[str, list[str]] = {}
        # prefix segment -> set of full registered paths sharing that prefix
        # e.g. "doc" -> {"doc", "doc.version", "doc.title"}
        self._prefix_to_paths: dict[str, set[str]] = {}

    def register_template(
        self,
        env: Environment,
        template_name: str,
        *,
        block_names: list[str] | None = None,
        dom_id_map: dict[str, str] | None = None,
    ) -> None:
        """Register a template's blocks into the dependency index.

        Uses kida's static analysis to extract dependencies.

        Args:
            env: Kida environment.
            template_name: Template to analyze.
            block_names: If given, only register these blocks.
                Otherwise all blocks are registered.
            dom_id_map: Mapping of block_name -> DOM element ID.
                If a block isn't in this map, block_name is used.
        """
        template = env.get_template(template_name)
        metadata = template.block_metadata()
        dom_ids = dom_id_map or {}

        for name, block_meta in metadata.items():
            if block_names is not None and name not in block_names:
                continue
            ref = BlockRef(
                template_name=template_name,
                block_name=name,
                dom_id=dom_ids.get(name),
            )
            for dep_path in block_meta.depends_on:
                self._path_to_blocks.setdefault(dep_path, []).append(ref)
                # Index all ancestor prefixes for fast prefix matching
                parts = dep_path.split(".")
                for i in range(len(parts)):
                    prefix = ".".join(parts[: i + 1])
                    self._prefix_to_paths.setdefault(prefix, set()).add(dep_path)

    def register_from_sse_swaps(
        self,
        env: Environment,
        template_name: str,
        template_source: str,
        *,
        exclude_blocks: set[str] | None = None,
    ) -> int:
        """Auto-register blocks that have matching ``sse-swap`` elements.

        Scans the raw template source for elements with both ``sse-swap``
        and ``id`` attributes, finds the ``{% block %}`` inside each,
        and registers only those blocks — with the correct ``dom_id``
        mapping.

        Blocks listed in *exclude_blocks* are skipped (e.g.,
        client-managed ``contenteditable`` blocks that should never be
        re-rendered via SSE).

        Returns the number of blocks auto-registered.

        Example::

            index = DependencyIndex()
            source = env.loader.get_source(env, "page.html")[0]
            n = index.register_from_sse_swaps(env, "page.html", source)
            # Registers only blocks inside sse-swap elements
        """
        exclude = exclude_blocks or set()

        # 1. Find elements with sse-swap (and optionally id)
        #    Pattern: <tag ... sse-swap="event" ... id="dom_id" ...>
        #    or:      <tag ... id="dom_id" ... sse-swap="event" ...>
        sse_swap_elements = _extract_sse_swap_elements(template_source)

        if not sse_swap_elements:
            return 0

        # 2. For each sse-swap element, find the {% block %} inside it.
        #    Convention: the block is a direct child of the element.
        block_to_dom_id: dict[str, str] = {}
        block_to_event: dict[str, str] = {}

        for elem in sse_swap_elements:
            block_name = elem.inner_block
            if block_name is None or block_name in exclude:
                continue
            if elem.dom_id:
                block_to_dom_id[block_name] = elem.dom_id
            block_to_event[block_name] = elem.swap_event

        if not block_to_dom_id:
            return 0

        # 3. Register via the standard method (uses kida static analysis)
        self.register_template(
            env,
            template_name,
            block_names=list(block_to_dom_id),
            dom_id_map=block_to_dom_id,
        )

        return len(block_to_dom_id)

    # ------------------------------------------------------------------
    # Derived Paths
    # ------------------------------------------------------------------

    def derive(
        self,
        path: str,
        *,
        from_paths: set[str] | frozenset[str],
    ) -> None:
        """Declare a derived path relationship.

        When any path in *from_paths* changes, *path* is automatically
        included in the expanded change set — so blocks that depend on
        *path* are re-rendered without the store needing to emit it.

        Multiple calls for the same *path* are **additive**: source
        paths are merged, not replaced.

        Derivations are **transitive**: if ``"a"`` derives from
        ``"b"`` and ``"b"`` derives from ``"c"``, changing ``"c"``
        expands to ``{"c", "b", "a"}``.

        Args:
            path: The derived context path (e.g., ``"doc.word_count"``).
            from_paths: Source paths that *path* is computed from
                (e.g., ``{"doc.content"}``).

        Example::

            index.derive("doc.word_count", from_paths={"doc.content"})
            index.derive("doc.summary", from_paths={"doc.content", "doc.title"})
        """
        for source in from_paths:
            self._source_to_derived.setdefault(source, []).append(path)

    def _expand_paths(self, changed_paths: frozenset[str]) -> frozenset[str]:
        """Expand changed paths through the derivation graph (BFS).

        Follows ``_source_to_derived`` edges transitively.  Handles
        cycles safely (each path is visited at most once).

        Returns:
            The original *changed_paths* plus all transitively derived paths.
        """
        expanded: set[str] = set(changed_paths)
        frontier: set[str] = set(changed_paths)
        while frontier:
            next_frontier: set[str] = set()
            for path in frontier:
                for derived in self._source_to_derived.get(path, ()):
                    if derived not in expanded:
                        expanded.add(derived)
                        next_frontier.add(derived)
            frontier = next_frontier
        return frozenset(expanded)

    @property
    def derivations(self) -> dict[str, frozenset[str]]:
        """Return ``{derived_path: frozenset_of_source_paths}`` for inspection.

        Inverts the internal ``_source_to_derived`` mapping so callers
        can see which sources feed each derived path.
        """
        result: dict[str, set[str]] = {}
        for source, derived_list in self._source_to_derived.items():
            for derived in derived_list:
                result.setdefault(derived, set()).add(source)
        return {k: frozenset(v) for k, v in result.items()}

    def explain_affected(
        self,
        changed_paths: frozenset[str],
    ) -> dict[str, Any]:
        """Debug helper: show the full expansion chain and affected blocks.

        Returns a dict with ``original_paths``, ``expanded_paths``,
        ``derived_paths`` (the difference), and ``affected_blocks``.
        """
        expanded = self._expand_paths(changed_paths) if self._source_to_derived else changed_paths
        blocks = self.affected_blocks(changed_paths)
        return {
            "original_paths": changed_paths,
            "expanded_paths": expanded,
            "derived_paths": expanded - changed_paths,
            "affected_blocks": [
                {
                    "template": ref.template_name,
                    "block": ref.block_name,
                    "target": ref.target_id,
                }
                for ref in blocks
            ],
        }

    def affected_blocks(self, changed_paths: frozenset[str]) -> list[BlockRef]:
        """Find all blocks affected by a set of changed context paths.

        First expands *changed_paths* through the derivation graph
        (if any derivations are registered), then checks direct and
        prefix matches against the block dependency index.

        Prefix matching: if ``"doc.version"`` changed and a block
        depends on ``"doc"``, it's considered affected (and vice versa).

        Returns:
            List of unique ``BlockRef`` objects.
        """
        # Expand through derivation graph before lookup
        effective = self._expand_paths(changed_paths) if self._source_to_derived else changed_paths

        seen: set[tuple[str, str]] = set()
        result: list[BlockRef] = []

        for changed in effective:
            # Direct match
            for ref in self._path_to_blocks.get(changed, []):
                key = (ref.template_name, ref.block_name)
                if key not in seen:
                    seen.add(key)
                    result.append(ref)

            # Registered paths that are children of the changed path
            # e.g., changed="doc", finds registered "doc.version", "doc.title"
            for registered_path in self._prefix_to_paths.get(changed, ()):
                if registered_path != changed:
                    for ref in self._path_to_blocks.get(registered_path, []):
                        key = (ref.template_name, ref.block_name)
                        if key not in seen:
                            seen.add(key)
                            result.append(ref)

            # Registered paths that are ancestors of the changed path
            # e.g., changed="doc.version", finds registered "doc"
            parts = changed.split(".")
            for i in range(1, len(parts)):
                ancestor = ".".join(parts[:i])
                for ref in self._path_to_blocks.get(ancestor, []):
                    key = (ref.template_name, ref.block_name)
                    if key not in seen:
                        seen.add(key)
                        result.append(ref)

        return result
