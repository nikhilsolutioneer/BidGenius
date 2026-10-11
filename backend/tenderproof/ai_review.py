"""Select evidence gaps after the complete deterministic extraction pass.

Ordinary descriptive context and unresolved supplier prices are not extraction
failures. Only an explicit missing field, source contradiction, or unhandled
source candidate can cause an AI request.
"""
from __future__ import annotations

from collections import defaultdict

from .models import Issue, PageRecord, Position, SourceSpan


REVIEW_VERSION = "1.0"
TECHNICAL_CONFLICTS = {"dimension_conflict", "technical_conflict", "system_conflict"}


def reviewable_position(position: Position) -> bool:
    return (position.origin != "manual" and position.review_state == "pending"
            and position.status not in {"out_of_scope", "non_priceable"}
            and position.pricing_basis != "included_elsewhere" and not position.included_in)


def build_review_batches(pages: list[PageRecord], spans: list[SourceSpan],
                         positions: list[Position], issues: list[Issue]) -> list[dict]:
    """Return bounded, JSON-serializable requests containing only unresolved work.

    Source dispositions must be the persisted post-local-extraction values.
    Context is restricted to selected positions and nearby blocks on target
    pages; unrelated pages and already classified descriptive text are not tasks.
    """
    page_map = {page.page: page for page in pages}
    source_map = {span.id: span for span in spans if span.page in page_map and span.text.strip()}
    by_page: dict[int, list[SourceSpan]] = defaultdict(list)
    for span in source_map.values():
        by_page[span.page].append(span)
    for source in by_page.values():
        source.sort(key=lambda span: (span.top, span.x0, span.id))
    covered = {source for position in positions for source in position.source_span_ids}
    candidates = [position for position in positions if reviewable_position(position)]
    tasks: dict[int, dict] = {}

    def add(page: int, targets: list[str], reason: dict, context: list[str] | tuple = ()) -> None:
        targets = [source for source in targets if source in source_map and source_map[source].page == page]
        if not targets:
            return
        task = tasks.setdefault(page, {"target_source_ids": set(), "position_ids": set(),
                                       "reasons": [], "context_source_ids": set()})
        task["target_source_ids"].update(targets)
        task["position_ids"].update(reason["position_ids"])
        task["reasons"].append(reason)
        task["context_source_ids"].update(source for source in context if source in source_map)

    def anchor(position: Position) -> str | None:
        quantity = position.field_sources.get("quantity", [])
        choices = [*quantity, *reversed(position.source_span_ids)]
        return next((source for source in choices if source in source_map
                     and source_map[source].page == position.source_page), None)

    pending_issues = {issue.id: issue for issue in issues if issue.review_state == "pending"}
    pending_issues.update({issue.id: issue for position in candidates for issue in position.warnings
                           if issue.review_state == "pending"})
    for position in candidates:
        target = anchor(position)
        if target is None:
            continue
        missing = []
        if position.quantity is None:
            missing.append("quantity")
        if not position.unit:
            missing.append("unit")
        if position.category.casefold() in {"", "unclassified", "unknown"}:
            missing.append("category")
        if position.system.casefold() in {"", "unassigned", "unknown"}:
            missing.append("system")
        for field in missing:
            add(position.source_page, [target], {
                "kind": f"missing_{field}", "field": field,
                "detail": f"Local extraction could not identify the {field}; recover it only if the supplied evidence supports it.",
                "source_span_ids": [target], "position_ids": [position.id]}, position.source_span_ids)
        conflicts = [issue for issue in pending_issues.values() if issue.kind in TECHNICAL_CONFLICTS
                     and (position.id in issue.position_ids
                          or set(position.source_span_ids).intersection(issue.source_span_ids)
                          or (issue.kind == "system_conflict" and any(
                              source in source_map and source_map[source].page == position.source_page
                              for source in issue.source_span_ids)))]
        for issue in conflicts:
            add(position.source_page, [target], {
                "kind": issue.kind, "detail": issue.detail, "issue_id": issue.id,
                "source_span_ids": list(dict.fromkeys([target, *issue.source_span_ids])),
                "position_ids": [position.id]}, [*position.source_span_ids, *issue.source_span_ids])
        if position.attributes.get("technical_conflict") and not conflicts:
            add(position.source_page, [target], {
                "kind": "technical_conflict", "detail": "Local extraction found conflicting technical values; explain both claims and preserve their evidence.",
                "source_span_ids": [target], "position_ids": [position.id]}, position.source_span_ids)

    for span in source_map.values():
        if (span.disposition != "unresolved" or span.id in covered
                or span.kind in {"boilerplate", "heading", "context"} or span.kind.startswith("package")):
            continue
        add(span.page, [span.id], {"kind": "unresolved_source", "detail": "This source candidate was not identified by local extraction; determine whether it is a position, requirement, or context.",
                                 "source_span_ids": [span.id], "position_ids": []})

    # Select small amounts of neighbouring context, including the nearest heading.
    for page_number, task in tasks.items():
        source = by_page[page_number]
        for index, span in enumerate(source):
            if span.id not in task["target_source_ids"]:
                continue
            task["context_source_ids"].update(block.id for block in source[max(0, index - 2):index + 3]
                                              if block.kind != "boilerplate")
            heading = next((block for block in reversed(source[:index]) if block.kind == "heading"), None)
            if heading:
                task["context_source_ids"].add(heading.id)

    groups: list[list[int]] = []
    section = None
    current: list[int] = []
    for page in sorted(pages, key=lambda page: page.page):
        if page.system != section:
            section = page.system
            current = []
        if page.page not in tasks:
            continue
        if not current or len(current) == 4:
            current = []
            groups.append(current)
        current.append(page.page)

    batches = []
    for numbers in groups:
        selected = [tasks[number] for number in numbers]
        targets = set().union(*(task["target_source_ids"] for task in selected))
        context = set().union(*(task["context_source_ids"] for task in selected))
        context = {source for source in context if source_map[source].page in numbers} - targets
        ordered = lambda ids: sorted(ids, key=lambda source: (source_map[source].page, source_map[source].top,
                                                            source_map[source].x0, source))
        allowed = targets | context
        reasons = [{**reason, "source_span_ids": [source for source in reason["source_span_ids"] if source in allowed]}
                   for task in selected for reason in task["reasons"]]
        batches.append({"pages": numbers, "target_source_ids": ordered(targets),
                        "position_ids": sorted(set().union(*(task["position_ids"] for task in selected))),
                        "reasons": reasons,
                        "context_source_ids": ordered(context)})
    return batches
