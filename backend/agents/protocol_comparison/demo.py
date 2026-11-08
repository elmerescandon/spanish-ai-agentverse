"""Demo case: canagliflozin in pediatric type 2 diabetes (NCT03170518).

The sponsor loosened HbA1c and ALT limits in Amendment 4 (2020) after slow
recruitment. The demo reviews the protocol as first issued, against peers
that had started by then, to see whether the agent flags the same limits.

Run `make demo-peers` to refresh the committed peer snapshot.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from backend.agents.protocol_comparison.agent import compare_registry_draft
from backend.agents.protocol_comparison.comparison import DimensionComparison
from backend.agents.protocol_comparison.peer_store import (
    PeerStore,
    PeerStoreError,
    load_or_fetch_peers,
)
from backend.agents.protocol_comparison.recommendations import (
    to_recommendations,
)
from backend.agents.protocol_comparison.review import SuggestionCard
from backend.api.schemas import Recommendation
from backend.clients.clinicaltrials_gov import (
    ClinicalTrialsGovClient,
    PeerSearchQuery,
    Phase,
    Population,
)
from backend.clients.gemini import JsonGenerator

DEMO_DRAFT_NCT_ID = "NCT03170518"
# Original protocol issue date, from the protocol amendment table (Prot_002
# page 6). Only trials that had started by then could have been compared.
DEMO_PROTOCOL_DATE = date(2016, 12, 19)
PEER_LOOKBACK_START = date(2006, 12, 19)  # ten years before the protocol

DEMO_PEER_QUERY = PeerSearchQuery(
    condition="Diabetes Mellitus, Type 2",
    phases=(Phase.PHASE3,),
    population=Population.PEDIATRIC,
    started_on_or_after=PEER_LOOKBACK_START,
    started_before=DEMO_PROTOCOL_DATE,
    exclude_nct_ids=frozenset({DEMO_DRAFT_NCT_ID}),
)


async def refresh_demo_peers() -> None:
    """Re-run the demo peer search and the draft fetch, then cache both."""
    store = PeerStore()
    async with ClinicalTrialsGovClient() as client:
        await load_or_fetch_peers(DEMO_PEER_QUERY, client, store, refresh=True)
        draft = await client.fetch_study(DEMO_DRAFT_NCT_ID)
    store.save_study(draft)


@dataclass(frozen=True)
class DemoComparison:
    """The demo draft compared with its cached peers."""

    draft_trial_id: str
    protocol_date: date
    results: tuple[DimensionComparison, ...]
    cards: tuple[SuggestionCard, ...]


async def compare_demo_draft(
    store: PeerStore | None = None, llm: JsonGenerator | None = None
) -> DemoComparison:
    """Compare the demo draft with its cached peers.

    Uses only the committed cache (data/peers) unless an LLM is given,
    so it is fast and repeatable.

    Raises:
        PeerStoreError: the demo peers or draft are not cached; run
            `make demo-peers`.
    """
    # [TO REFACTOR:(theo)]: every protocol is compared as the demo draft
    # until the parsed protocol's values feed the comparison.
    store = store or PeerStore()
    peer_studies = store.load_studies(DEMO_PEER_QUERY)
    if peer_studies is None:
        raise PeerStoreError(
            "expected cached demo peers in data/peers, found none; "
            "run `make demo-peers`"
        )
    draft_study = store.load_study(DEMO_DRAFT_NCT_ID)
    results, cards = await compare_registry_draft(
        draft_study, DEMO_PROTOCOL_DATE, peer_studies, store, llm
    )
    return DemoComparison(
        draft_trial_id=DEMO_DRAFT_NCT_ID,
        protocol_date=DEMO_PROTOCOL_DATE,
        results=results,
        cards=cards,
    )


async def demo_recommendations(
    protocol_id: str,
    store: PeerStore | None = None,
    llm: JsonGenerator | None = None,
) -> list[Recommendation]:
    """Compare the demo draft with its cached peers, as recommendations.

    Raises:
        PeerStoreError: the demo peers or draft are not cached; run
            `make demo-peers`.
    """
    comparison = await compare_demo_draft(store, llm)
    return to_recommendations(
        protocol_id, comparison.results, comparison.cards
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(refresh_demo_peers())
