# psa-pokemon-bidder

`psa-pokemon-bidder` is a production-minded Python MVP for scanning PSA's official eBay listings, filtering to a strict allow-list of target Pokemon, using prompt-driven agents to choose viable auction links and estimate market value/max bids, and then placing bids through a chained workflow.

The project is intentionally narrow:

- PSA official eBay account only
- Pokemon cards only
- auction listings only
- PSA graded cards only
- strict Pokemon enum allow-list
- listings must explicitly indicate `"In the PSA Vault"` on the listing page or in structured page metadata
- auctions must be within the last 10 minutes before ending
- the script polls every 15 minutes in continuous mode
- dry-run bidding supported now
- live eBay Browse API fetching and Trading API bid execution hooks are implemented behind explicit credentials

## Architecture

This is a true multi-agent MVP from day one, not a monolithic pipeline.

Agent roles:

- `AuctionSearchAgent`: uses a LangChain prompt to choose which validated eBay listing links should move forward
- `AnalysisAgent`: uses a LangChain prompt to estimate market value, assess price trend direction, and produce a max bid for each selected listing
- `SupervisorAgent`: coordinates the LangChain runnable chain and agent handoffs

Deterministic tools:

- `ScannerTool`: fetches raw listings from the configured eBay client adapter
- `ListingPreparationTool`: parses listings and applies hard scope filters before any LLM call
- `BidExecutionTool`: applies deterministic guardrails and executes dry-run or real bid hooks

Orchestration:

- The supervisor performs deterministic scanning, parsing, and scope filtering through LangChain runnable tool stages, then hands the surviving listings to two prompt-driven agents: auction search and market analysis.
- The end-to-end cycle is wired as a LangChain runnable chain inside [app/agents/supervisor_agent.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/agents/supervisor_agent.py).
- Deterministic Python handles ingestion, parsing helpers, scope filters, the 10-minute cutoff, persistence, guardrails, and bid execution mechanics.
- The prompt agents use LangChain runnable composition in the `prompt | llm.with_structured_output(...)` style, with OpenAI-backed structured-output paths and local heuristic fallbacks so the MVP still runs without credentials.

## Project Layout

```text
app/
  agents/
  clients/
  models/
  prompts/
  services/
  storage/
  tools/
  utils/
  workflows/
data/
scripts/
tests/
```

Key files:

- [app/main.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/main.py): top-level `run_mvp(...)` entrypoint
- [scripts/run_mvp.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/scripts/run_mvp.py): runnable local script
- [data/sample_ebay_listings.json](/Users/yaroslawbagriy/Dev/psa-auction-agent/data/sample_ebay_listings.json): mock PSA/eBay listing payloads
- [app/storage/sqlite.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/storage/sqlite.py): SQLite persistence for listings, analysis, bids, and errors
- [app/tools/scanner_tool.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/tools/scanner_tool.py): deterministic listing ingestion tool used by the LangChain chain
- [app/tools/listing_preparation_tool.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/tools/listing_preparation_tool.py): deterministic parsing and validation tool
- [app/tools/bid_execution_tool.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/tools/bid_execution_tool.py): deterministic bidding guardrail and execution tool
- [app/prompts/auction_search_prompt.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/prompts/auction_search_prompt.py): auction-search prompt that selects listing links
- [app/prompts/analysis_prompt.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/prompts/analysis_prompt.py): market-analysis/max-bid prompt

## Core Models

The main typed models live under [app/models](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/models):

- `Pokemon`: enum-based allow-list input
- `TargetRules`: business rules like allowed grades and max current price
- `SearchConfig`: runtime search/bid configuration
- `RawListing` and `Listing`: ingestion and normalized listing models
- `AuctionSearchDecision` and `AuctionSearchResult`
- `MarketAnalysisInput`, `MarketAnalysisBatchResult`, and `AnalysisResult`
- `BidDecision` and `BidExecutionResult`
- `WorkflowSummary`

Example target Pokemon input:

```python
from app.models.pokemon import Pokemon

targets = [Pokemon.PIKACHU, Pokemon.CHARIZARD, Pokemon.GENGAR]
```

Example programmatic usage:

```python
from app.main import run_mvp
from app.models.config import TargetRules
from app.models.pokemon import Pokemon

summary = run_mvp(
    target_pokemon=[Pokemon.PIKACHU, Pokemon.CHARIZARD, Pokemon.GENGAR],
    target_rules=TargetRules(
        allowed_grades={"9", "10"},
        max_current_price=1500.0,
        max_minutes_remaining=10,
    ),
    dry_run=True,
)
```

## Workflow

The implemented MVP flow is:

1. fetch listings from the eBay client
2. pre-validate seller, auction type, raw Pokemon scope, and the `<= 10 minute` bidding window
3. parse normalized listing details
4. validate PSA grading, Pokemon allow-list, explicit listing-page vault evidence, and target rules
5. send validated listings to the `AuctionSearchAgent` prompt and collect the eBay links it selects
6. send each selected listing batch to the `AnalysisAgent` prompt to estimate market value, trend outlook, and max bid
7. apply deterministic bid guardrails
8. execute a dry-run bid
9. persist every major step to SQLite

## Running Locally

1. Create a virtual environment and activate it.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy [.env.example](/Users/yaroslawbagriy/Dev/psa-auction-agent/.env.example) to `.env` if you want to customize paths or enable optional integrations.
4. Run one dry-run cycle:

```bash
python scripts/run_mvp.py --once
```

5. Run continuous polling every 15 minutes:

```bash
python scripts/run_mvp.py
```

If `OPENAI_API_KEY` is set, the OpenAI-backed prompt agents are enabled automatically. Otherwise the project falls back to local heuristic engines so the dry-run MVP still works offline.

The default run uses mock eBay data, SQLite persistence, and heuristic fallbacks for the prompt agents when no OpenAI key is configured. The sample eBay data includes market-context snapshots and relative end times so the 10-minute auction window and bidding logic can be exercised locally.

Listing ingestion is not LLM scraping today. In dry-run mode, `MockEbayClient` loads [data/sample_ebay_listings.json](/Users/yaroslawbagriy/Dev/psa-auction-agent/data/sample_ebay_listings.json). In live mode, [app/clients/ebay.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay.py) uses the eBay Browse API to search PSA's official `/str/psa` seller account for auction listings and then enriches item details. The eBay seller username for that store is `psa`, so the live Browse API filter is `sellers:{psa},buyingOptions:{AUCTION}`. Optional listing-page enrichment only looks for the literal `"In the PSA Vault"` phrase because that signal may appear on the listing page rather than the title.

Live eBay settings:

- `USE_LIVE_EBAY=true`
- `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` mint an application token for Browse API calls, or `EBAY_ACCESS_TOKEN` can provide a pre-minted application token.
- `EBAY_USER_ACCESS_TOKEN` is required for live bid placement through the eBay Trading API `PlaceOffer` call.
- `EBAY_ENVIRONMENT=sandbox` switches both Browse and Trading API endpoints to sandbox.

## Tests

Run the tests with:

```bash
pytest
```

Current coverage includes:

- title parsing and Pokemon detection
- PSA Vault detection
- 10-minute bidding-window validation
- validation and allow-list behavior
- end-to-end dry-run workflow behavior against sample data

## Live Integration Notes

The code is structured so live integrations can be added without rewriting the architecture:

- [app/clients/ebay.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay.py): `OfficialEbayApiClient` uses OAuth client credentials and Browse API search/getItem calls
- live market context enrichment is still a TODO; the second prompt agent currently reasons over listing data plus supplied market context instead of a dedicated external pricing source
- [app/tools/bid_execution_tool.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/tools/bid_execution_tool.py): `RealEbayBidExecutor` posts Trading API `PlaceOffer` XML when `dry_run=False` and `EBAY_USER_ACCESS_TOKEN` is configured
- eBay notes that new access to the legacy `PlaceOffer` feature is restricted, so production live bidding may require approval or a different eBay buying integration depending on your developer account

## Notes

- Shipping cost is intentionally excluded from the MVP model because the target workflow assumes cards remain in the PSA Vault.
- The Pokemon enum allow-list is a strict filter and is applied before the prompt-driven auction-search and market-analysis stages.
- Duplicate unsafe bidding is guarded by SQLite-backed bid-attempt checks in the deterministic bid guardrail layer.
- The market-analysis prompt is expected to recommend bids only when the outlook is steady or upward; deterministic guardrails reject downward outlooks.
