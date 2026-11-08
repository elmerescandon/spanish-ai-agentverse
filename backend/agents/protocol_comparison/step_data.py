"""Turn comparison results into the /demo PEERS step (StepData). Pure.

Builds on to_recommendations, so each Decision says what the matching
Recommendation says (title, severity, claim, facts), then adds what the
/demo page shows: evidence, a reasoning trace, options, a peer table and
a chart.

The draft's values come from its registry record. A value whose quote
also appears in the uploaded PDF is cited from the protocol with its
page; the rest are cited from the registry record, with a step warning.
"""

import re
from collections.abc import Sequence
from datetime import date

from pydantic import TypeAdapter
from pydantic_core import to_jsonable_python

from backend.agents.protocol_comparison.agent import AGENT_NAME
from backend.agents.protocol_comparison.comparison import (
    Category,
    CategoryResult,
    DimensionComparison,
    PeerEvidence,
)
from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.agents.protocol_comparison.recommendations import (
    Finding,
    formatted_value,
    to_recommendations,
)
from backend.agents.protocol_comparison.review import (
    Leaning,
    ReasoningStatus,
    SuggestionCard,
)
from backend.api.schemas import (
    Chart,
    ChartKind,
    ChartPoint,
    ChartSeries,
    DataSource,
    DataTable,
    Decision,
    DecisionOption,
    DetailMap,
    Evidence,
    EvidenceSource,
    Metric,
    MetricBenchmark,
    MetricTone,
    ProposedChange,
    ProtocolLocation,
    Recommendation,
    StepData,
    StepId,
    StepStatus,
    StepWarning,
    TableColumn,
    TraceEntry,
    TraceKind,
)
from backend.clients.clinicaltrials_gov import (
    NCT_ID_PATTERN,
    STUDY_PAGE_URL_TEMPLATE,
)
from backend.shared.messages import ProtocolDocument

TRACE_AGENT = "Comparison"  # agent name shown on reasoning trace entries
STEP_TITLE = "Protocol Comparison"
REGISTRY_URL = "https://clinicaltrials.gov"
# Source texts quote the verbatim part, e.g. registry minimumAge "10 Years".
QUOTED_TEXT_PATTERN = re.compile(r'"([^"]+)"')
WHITESPACE_PATTERN = re.compile(r"\s+")
# Short quotes such as "10 Years" turn up anywhere in a protocol, so only
# quotes this long are looked up in the PDF; shorter ones cite the registry.
MIN_PDF_QUOTE_LENGTH = 25
ELIGIBILITY_SECTION = "Eligibility criteria"
SAMPLE_SIZE_SECTION = "Sample size"
DETAIL_MAP_ADAPTER: TypeAdapter[DetailMap] = TypeAdapter(DetailMap)


def quoted_text(source: str) -> str:
    """The verbatim part of a value's source, or the whole source."""
    match = QUOTED_TEXT_PATTERN.search(source)
    return match.group(1) if match else source


def _normalised(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip().casefold()


def find_quote_page(document: ProtocolDocument, quote: str) -> int | None:
    """The first page whose text contains the quote, ignoring spacing."""
    if len(quote) < MIN_PDF_QUOTE_LENGTH:
        return None
    wanted = _normalised(quote)
    for page in document.pages:
        if wanted in _normalised(page.text):
            return page.page_number
    return None


def _study_url(trial_id: str) -> str | None:
    if NCT_ID_PATTERN.fullmatch(trial_id) is None:
        return None
    return STUDY_PAGE_URL_TEMPLATE.format(nct_id=trial_id)


def _section(result: DimensionComparison) -> str:
    if result.dimension.dimension_id == DimensionId.ENROLLMENT:
        return SAMPLE_SIZE_SECTION
    return ELIGIBILITY_SECTION


def _view_name(category: Category) -> str:
    return category.value.lower().replace("_", " ")


def _draft_evidence(
    result: DimensionComparison,
    decision_id: str,
    document: ProtocolDocument,
    draft_trial_id: str,
) -> Evidence | None:
    if result.draft_value is None:
        return None
    quote = quoted_text(result.draft_value.source)
    page = find_quote_page(document, quote)
    evidence_id = f"{decision_id}-draft"
    if page is not None:
        return Evidence(
            evidence_id=evidence_id,
            source=EvidenceSource.PROTOCOL,
            document=document.title,
            page=page,
            quote=quote,
            is_verified=True,
            section_title=_section(result),
            context=result.draft_value.source,
        )
    return Evidence(
        evidence_id=evidence_id,
        source=EvidenceSource.AACT,
        document=draft_trial_id,
        quote=quote,
        # The readers only keep quotes found in the registry record.
        is_verified=True,
        section_title=_section(result),
        context=result.draft_value.source,
        url=_study_url(draft_trial_id),
    )


def _peer_evidence(peer: PeerEvidence, decision_id: str) -> Evidence | None:
    if peer.value is None:
        return None
    return Evidence(
        evidence_id=f"{decision_id}-{peer.trial_id}",
        source=EvidenceSource.AACT,
        document=peer.trial_id,
        quote=quoted_text(peer.value.source),
        is_verified=True,
        context=(
            f"{peer.value.source}; tier {peer.tier.value}, "
            f"weight {peer.weight:.2f}"
        ),
        url=_study_url(peer.trial_id),
    )


def _compare_text(summary: CategoryResult) -> str:
    parts = [
        (
            f"{_view_name(summary.category)} peers: "
            f"{summary.stating_count} of {summary.peer_count} state a "
            f"value (effective n {summary.n_eff:.1f})"
        )
    ]
    if summary.percentile_range is not None:
        parts.append(
            f"10th-90th percentile {summary.percentile_range.low:g} to "
            f"{summary.percentile_range.high:g}"
        )
    if summary.range_position is not None:
        parts.append(f"draft is {summary.range_position.value.lower()}")
    parts.append(f"verdict {summary.verdict.value}")
    return "; ".join(parts) + "."


def _evidence_ids_in(
    summary: CategoryResult,
    result: DimensionComparison,
    decision_id: str,
    peer_ids: set[str],
) -> list[str]:
    return [
        evidence_id
        for peer in result.evidence
        if (evidence_id := f"{decision_id}-{peer.trial_id}") in peer_ids
        and (
            summary.category == Category.WEIGHTED
            or summary.category in peer.categories
        )
    ]


def _trace(
    result: DimensionComparison,
    recommendation: Recommendation,
    draft: Evidence | None,
    peers: Sequence[Evidence],
) -> list[TraceEntry]:
    decision_id = recommendation.recommendation_id
    peer_ids = {evidence.evidence_id for evidence in peers}
    draft_ids = [] if draft is None else [draft.evidence_id]
    trace = [
        TraceEntry(
            agent=TRACE_AGENT,
            kind=TraceKind.RETRIEVE,
            text=(
                f"Compared with {len(result.evidence)} screened peer "
                f"trials; {len(peers)} state a "
                f"{result.dimension.label} value."
            ),
            evidence_ids=sorted(peer_ids),
        )
    ]
    if draft is not None and result.draft_value is not None:
        trace.append(
            TraceEntry(
                agent=TRACE_AGENT,
                kind=TraceKind.RETRIEVE,
                text=(
                    "Draft value "
                    f"{formatted_value(result, result.draft_value.value)} "
                    f"read from {result.draft_value.source}."
                ),
                evidence_ids=draft_ids,
            )
        )
    for summary in result.categories:
        trace.append(
            TraceEntry(
                agent=TRACE_AGENT,
                kind=TraceKind.COMPARE,
                text=_compare_text(summary),
                evidence_ids=draft_ids
                + _evidence_ids_in(summary, result, decision_id, peer_ids),
                details={
                    "category": summary.category.value,
                    "is_official": summary is result.categories[0],
                    "verdict": summary.verdict.value,
                    "rule": None if summary.rule is None else summary.rule,
                },
            )
        )
    trace.append(
        TraceEntry(
            agent=TRACE_AGENT,
            kind=TraceKind.CONCLUDE,
            text=recommendation.description,
            evidence_ids=draft_ids,
        )
    )
    return trace


def _options(
    result: DimensionComparison,
    card: SuggestionCard | None,
    decision_id: str,
) -> list[DecisionOption]:
    if card is None or not card.suggestions or result.draft_value is None:
        return []
    leaning = None if card.reasoning is None else card.reasoning.leaning
    before = formatted_value(result, result.draft_value.value)
    options = []
    for index, suggestion in enumerate(card.suggestions):
        view = _view_name(suggestion.category)
        after = formatted_value(result, suggestion.suggested_value)
        rationale = (
            f"{after} is in line with {len(suggestion.peer_ids)} {view} "
            f"peer trials ({suggestion.rule.value.lower()} rule)."
        )
        options.append(
            DecisionOption(
                option_id=f"{decision_id}-{view.replace(' ', '-')}",
                title=f"Bring in line with {view} peers",
                rationale=rationale,
                is_recommended=leaning == Leaning.BRING_IN_LINE and index == 0,
                proposed_change=ProposedChange(
                    path=f"{_section(result)}: {result.dimension.label}",
                    before=before,
                    after=after,
                    section_title=_section(result),
                    rationale=rationale,
                ),
            )
        )
    options.append(
        DecisionOption(
            option_id=f"{decision_id}-keep",
            title="Keep the current value",
            rationale=(
                card.reasoning.risk_of_changing
                if card.reasoning is not None
                else f"Leave {result.dimension.label} at {before}."
            ),
            is_recommended=leaning == Leaning.KEEP_AS_IS,
            risks=(
                [card.reasoning.why_it_matters]
                if card.reasoning is not None
                else []
            ),
        )
    )
    return options


def _impact(result: DimensionComparison, is_flagged: bool) -> list[Metric]:
    if result.draft_value is None or not result.categories:
        return []
    official = result.categories[0]
    benchmarks = (
        []
        if official.percentile_range is None
        else [
            MetricBenchmark(
                label="Peer 10th percentile",
                value=formatted_value(result, official.percentile_range.low),
                numeric_value=official.percentile_range.low,
            ),
            MetricBenchmark(
                label="Peer 90th percentile",
                value=formatted_value(result, official.percentile_range.high),
                numeric_value=official.percentile_range.high,
            ),
        ]
    )
    return [
        Metric(
            label="Draft value",
            value=formatted_value(result, result.draft_value.value),
            tone=MetricTone.WARN if is_flagged else MetricTone.GOOD,
            numeric_value=result.draft_value.value,
            unit=result.dimension.unit,
            benchmarks=benchmarks,
        ),
        Metric(
            label="Effective peers",
            value=f"{official.n_eff:.1f}",
            numeric_value=official.n_eff,
            description="Kish effective sample size of the weighted peers.",
        ),
    ]


def _peer_table(result: DimensionComparison, decision_id: str) -> DataTable:
    return DataTable(
        table_id=f"{decision_id}-peers",
        title=f"Peer trials: {result.dimension.label}",
        columns=[
            TableColumn(key="trial_id", label="Trial"),
            TableColumn(
                key="value", label="Value", unit=result.dimension.unit
            ),
            TableColumn(key="tier", label="Tier"),
            TableColumn(key="weight", label="Weight"),
            TableColumn(key="categories", label="Categories"),
            TableColumn(key="url", label="Registry page"),
        ],
        rows=[
            {
                "trial_id": peer.trial_id,
                "value": None if peer.value is None else peer.value.value,
                "tier": peer.tier.value,
                "weight": round(peer.weight, 3),
                "categories": ", ".join(
                    sorted(category.value for category in peer.categories)
                ),
                "url": _study_url(peer.trial_id),
            }
            for peer in result.evidence
        ],
    )


def _peer_chart(result: DimensionComparison, decision_id: str) -> Chart:
    peer_points = [
        ChartPoint(label=peer.trial_id, value=peer.value.value)
        for peer in result.evidence
        if peer.value is not None
    ]
    series = [ChartSeries(name="Peers", points=peer_points)]
    if result.draft_value is not None:
        official = result.categories[0] if result.categories else None
        peer_range = None if official is None else official.percentile_range
        series.append(
            ChartSeries(
                name="Draft",
                points=[
                    ChartPoint(
                        label="Draft",
                        value=result.draft_value.value,
                        lower=None if peer_range is None else peer_range.low,
                        upper=None if peer_range is None else peer_range.high,
                        annotation=(
                            None
                            if peer_range is None
                            else "bounds are the peers' 10th-90th percentile"
                        ),
                    )
                ],
            )
        )
    return Chart(
        chart_id=f"{decision_id}-chart",
        kind=ChartKind.COMPARISON,
        title=f"{result.dimension.label}: draft against peers",
        x_label="Trial",
        y_label=result.dimension.label,
        unit=result.dimension.unit,
        series=series,
    )


def _decision(
    result: DimensionComparison,
    card: SuggestionCard | None,
    recommendation: Recommendation,
    document: ProtocolDocument,
    draft_trial_id: str,
) -> Decision | None:
    """One dimension as a Decision; None when there is no evidence."""
    decision_id = recommendation.recommendation_id
    draft = _draft_evidence(result, decision_id, document, draft_trial_id)
    peers = [
        peer_evidence
        for peer in result.evidence
        if (peer_evidence := _peer_evidence(peer, decision_id)) is not None
    ]
    all_evidence = ([] if draft is None else [draft]) + peers
    if not all_evidence:
        return None
    finding = Finding(str(recommendation.details["finding"]))
    options = _options(result, card, decision_id)
    proposed_change = next(
        (
            option.proposed_change
            for option in options
            if option.proposed_change is not None
        ),
        None,
    )
    is_protocol_quote = (
        draft is not None and draft.source == EvidenceSource.PROTOCOL
    )
    return Decision(
        decision_id=decision_id,
        step_id=StepId.PEERS,
        severity=recommendation.severity,
        title=recommendation.title,
        claim=recommendation.description,
        evidence=all_evidence,
        trace=_trace(result, recommendation, draft, peers),
        proposed_change=proposed_change,
        category=_section(result).lower(),
        location=(
            ProtocolLocation(
                section_title=_section(result),
                start_page=draft.page,
                end_page=draft.page,
            )
            if is_protocol_quote and draft is not None
            else None
        ),
        impact=_impact(result, finding == Finding.FLAGGED),
        options=options,
        tags=[finding.value.lower(), result.dimension.dimension_id.lower()],
        tables=[_peer_table(result, decision_id)],
        charts=[_peer_chart(result, decision_id)],
        details=DETAIL_MAP_ADAPTER.validate_python(
            to_jsonable_python(recommendation.details)
        ),
    )


def _dimension_table(
    results: Sequence[DimensionComparison],
    recommendations: Sequence[Recommendation],
) -> DataTable:
    rows: list[DetailMap] = []
    for result, recommendation in zip(results, recommendations, strict=True):
        official = result.categories[0] if result.categories else None
        peer_range = None if official is None else official.percentile_range
        rows.append(
            {
                "dimension": result.dimension.label,
                "draft_value": (
                    None
                    if result.draft_value is None
                    else formatted_value(result, result.draft_value.value)
                ),
                "finding": str(recommendation.details["finding"]),
                "verdict": result.verdict.value,
                "effective_peers": (
                    None if official is None else round(official.n_eff, 2)
                ),
                "peer_p10": None if peer_range is None else peer_range.low,
                "peer_p90": None if peer_range is None else peer_range.high,
            }
        )
    return DataTable(
        table_id="peers-dimensions",
        title="Every compared dimension",
        columns=[
            TableColumn(key="dimension", label="Dimension"),
            TableColumn(key="draft_value", label="Draft"),
            TableColumn(key="finding", label="Finding"),
            TableColumn(key="verdict", label="Official verdict"),
            TableColumn(key="effective_peers", label="Effective peers"),
            TableColumn(key="peer_p10", label="Peer 10th percentile"),
            TableColumn(key="peer_p90", label="Peer 90th percentile"),
        ],
        rows=rows,
    )


def _warnings(
    decisions: Sequence[Decision],
    cards: Sequence[SuggestionCard],
    draft_trial_id: str,
) -> list[StepWarning]:
    warnings = []
    draft_evidence = [
        evidence
        for decision in decisions
        for evidence in decision.evidence
        if evidence.evidence_id.endswith("-draft")
    ]
    from_pdf = sum(
        evidence.source == EvidenceSource.PROTOCOL
        for evidence in draft_evidence
    )
    if from_pdf < len(draft_evidence):
        warnings.append(
            StepWarning(
                code="DRAFT_FROM_REGISTRY",
                message=(
                    "Draft values are read from registry record "
                    f"{draft_trial_id}, not parsed from the uploaded PDF; "
                    f"{from_pdf} of {len(draft_evidence)} were also found "
                    "verbatim in the PDF."
                ),
            )
        )
    for card in cards:
        label = card.comparison.dimension.label
        if card.reasoning_status == ReasoningStatus.FAILED:
            warnings.append(
                StepWarning(
                    code="REASONING_FAILED",
                    message=f"{label}: the LLM reasoning call failed.",
                )
            )
        if card.unknown_cited_trial_ids:
            warnings.append(
                StepWarning(
                    code="UNKNOWN_CITED_TRIALS",
                    message=(
                        f"{label}: reasoning cites trials outside the "
                        f"evidence: {', '.join(card.unknown_cited_trial_ids)}"
                    ),
                )
            )
    return warnings


def to_step_data(
    document: ProtocolDocument,
    draft_trial_id: str,
    protocol_date: date,
    results: Sequence[DimensionComparison],
    cards: Sequence[SuggestionCard],
) -> StepData:
    """The comparison as the /demo PEERS step, one Decision per dimension.

    A dimension with no evidence at all (neither the draft nor any peer
    states it) has no Decision; it is still listed in the step's table.
    """
    recommendations = to_recommendations(document.protocol_id, results, cards)
    cards_by_dimension = {
        card.comparison.dimension.dimension_id: card for card in cards
    }
    decisions = [
        decision
        for result, recommendation in zip(
            results, recommendations, strict=True
        )
        if (
            decision := _decision(
                result,
                cards_by_dimension.get(result.dimension.dimension_id),
                recommendation,
                document,
                draft_trial_id,
            )
        )
        is not None
    ]
    peer_count = len(results[0].evidence) if results else 0
    official_flags = sum(card.is_official_flag for card in cards)
    to_review = len(cards) - official_flags
    has_failed_reasoning = any(
        card.reasoning_status == ReasoningStatus.FAILED for card in cards
    )
    return StepData(
        id=StepId.PEERS,
        title=STEP_TITLE,
        summary=(
            f"'{document.title}' compared with {peer_count} peer trials on "
            f"{len(results)} dimensions: {official_flags} outlier(s) "
            f"flagged, {to_review} more to review."
        ),
        headline=Metric(label="peer trials", value=str(peer_count)),
        metrics=[
            Metric(
                label="Peer trials",
                value=str(peer_count),
                numeric_value=peer_count,
            ),
            Metric(
                label="Dimensions compared",
                value=str(len(results)),
                numeric_value=len(results),
            ),
            Metric(
                label="Outliers",
                value=str(official_flags),
                tone=MetricTone.RISK if official_flags else MetricTone.GOOD,
                numeric_value=official_flags,
            ),
            Metric(
                label="To review",
                value=str(to_review),
                tone=MetricTone.WARN if to_review else MetricTone.GOOD,
                numeric_value=to_review,
            ),
        ],
        decisions=decisions,
        status=(
            StepStatus.PARTIAL
            if has_failed_reasoning
            else StepStatus.COMPLETED
        ),
        agent=AGENT_NAME,
        warnings=_warnings(decisions, cards, draft_trial_id),
        data_sources=[
            DataSource(
                source=EvidenceSource.AACT,
                name="ClinicalTrials.gov peer snapshot",
                description=(
                    "Peer trials that started before the protocol date "
                    f"({protocol_date.isoformat()}), cached in data/peers."
                ),
                url=REGISTRY_URL,
                record_count=peer_count,
            )
        ],
        tables=[_dimension_table(results, recommendations)],
        details={
            "draft_trial_id": draft_trial_id,
            "draft_url": _study_url(draft_trial_id),
            "protocol_date": protocol_date.isoformat(),
        },
    )
