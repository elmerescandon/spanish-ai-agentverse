"""Demo case: canagliflozin in pediatric type 2 diabetes (NCT03170518).

The sponsor loosened HbA1c and ALT limits in Amendment 4 (2020) after slow
recruitment. The demo reviews the protocol as first issued, against peers
that had started by then, to see whether the agent flags the same limits.

Run `make demo-peers` to refresh the committed peer snapshot.
"""

import asyncio
import logging
from datetime import date

from backend.agents.protocol_comparison.peer_store import (
    PeerStore,
    load_or_fetch_peers,
)
from backend.clients.clinicaltrials_gov import (
    ClinicalTrialsGovClient,
    PeerSearchQuery,
    Phase,
    Population,
)

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(refresh_demo_peers())
