# psa-pokemon-bidder

`psa-pokemon-bidder` is a production-minded Python MVP for scanning PSA's official eBay listings, filtering to a strict allow-list of target Pokemon, using prompt-driven agents to choose viable auction links and estimate market value/max bids, and then producing safe manual bidding recommendations by default.

The project is intentionally narrow:

- PSA official eBay account only
- Pokemon cards only
- auction listings only
- PSA graded cards only
- strict Pokemon enum allow-list
- listings must explicitly indicate `"In the PSA Vault"` on the listing page or in structured page metadata
- auctions must be within the last 10 minutes before ending
- the script polls every 15 minutes in continuous mode
- manual bidding is the default MVP behavior
- the app does not place bids through eBay website automation
- live eBay Browse API fetching is implemented behind explicit credentials
- official eBay Buy Offer API proxy bidding is implemented but gated behind explicit config, user OAuth, dry-run=false, human-confirmation=false, and eBay approval

## Architecture

This is a true multi-agent MVP from day one, not a monolithic pipeline.

Agent roles:

- `AuctionSearchAgent`: uses a LangChain prompt to choose which validated eBay listing links should move forward
- `AnalysisAgent`: uses a LangChain prompt to estimate market value, assess price trend direction, and produce a max bid for each selected listing
- `SupervisorAgent`: coordinates the LangChain runnable chain and agent handoffs

Deterministic tools:

- `ScannerTool`: fetches raw listings from the configured eBay client adapter
- `ListingPreparationTool`: parses listings and applies hard scope filters before any LLM call
- `BidExecutionTool`: applies deterministic guardrails and prepares a safe bid action result

Orchestration:

- The supervisor performs deterministic scanning, parsing, and scope filtering through LangChain runnable tool stages, then hands the surviving listings to two prompt-driven agents: auction search and market analysis.
- The end-to-end cycle is wired as a LangChain runnable chain inside [app/agents/supervisor_agent.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/agents/supervisor_agent.py).
- Deterministic Python handles ingestion, parsing helpers, scope filters, the 10-minute cutoff, persistence, guardrails, and safe bid-action preparation.
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
- [app/tools/bid_execution_tool.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/tools/bid_execution_tool.py): deterministic bidding guardrail and safe bid-action service
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
- `BidDecision`, `BidActionResult`, and `BidExecutionResult`
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
8. create a manual bid action result, or a gated official eBay Offer API proxy-bid result when explicitly enabled, with the title, item ID, current price, end time, estimated market value, max bid, margin, reasoning, and eBay URL
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

Set `USE_OPENAI_SEARCH_AGENT=true` or `USE_OPENAI_ANALYSIS=true` with `OPENAI_API_KEY` to enable the OpenAI-backed prompt agents. Otherwise the project falls back to local heuristic engines so the dry-run MVP still works offline.

The default run uses mock eBay data, SQLite persistence, and heuristic fallbacks for the prompt agents when no OpenAI key is configured. The sample eBay data includes market-context snapshots and relative end times so the 10-minute auction window and bidding logic can be exercised locally.

Listing ingestion is not LLM scraping today. In dry-run mode, `MockEbayClient` loads [data/sample_ebay_listings.json](/Users/yaroslawbagriy/Dev/psa-auction-agent/data/sample_ebay_listings.json). In live mode, [app/clients/ebay.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay.py) uses the eBay Browse API to search PSA's official `/str/psa` seller account for auction listings and then enriches item details. The eBay seller username for that store is `psa`, so the live Browse API filter is `sellers:{psa},buyingOptions:{AUCTION}`. Optional listing-page enrichment only looks for the literal `"In the PSA Vault"` phrase because that signal may appear on the listing page rather than the title.

Live eBay settings:

- `USE_LIVE_EBAY=true`
- `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` mint an application token for Browse API calls, or `EBAY_ACCESS_TOKEN` can provide a pre-minted application token.
- `EBAY_BIDDING_MODE=manual` is the default and recommended MVP setting while API access is pending.
- `EBAY_BIDDING_MODE=official_api` uses eBay's official Buy Offer API `place_proxy_bid` endpoint only when all required flags and user OAuth credentials are present. If credentials, approval, or safety flags are missing, the app falls back to manual bidding.
- `EBAY_BIDDING_MODE=browser_automation` is explicitly unsupported and returns an unsupported result.
- `EBAY_ENVIRONMENT=sandbox` switches supported official eBay API endpoints to sandbox.
- `EBAY_USER_REFRESH_TOKEN` lets the app mint a fresh user access token with eBay's official OAuth refresh-token flow when needed.

## Bidding Safety

Manual mode never places a bid automatically. It scans, analyzes, calculates a recommended max bid, and returns a manual action result that clearly requires the user to review the listing and place the bid on eBay.

Supported bidding modes:

- `manual`: default behavior. Returns `status="requires_user_action"` with the listing URL and bid recommendation.
- `official_api`: approved official API path. It only submits through `POST /buy/offer/v1_beta/bidding/{item_id}/place_proxy_bid` when `EBAY_BIDDING_ENABLED=true`, `EBAY_BUY_OFFER_API_ENABLED=true`, `EBAY_REQUIRE_HUMAN_CONFIRMATION=false`, `dry_run=False`, `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, and `EBAY_USER_REFRESH_TOKEN` are present. `EBAY_USER_ACCESS_TOKEN` is optional because the client can mint a fresh user access token from the refresh token. If `dry_run=True`, it returns `status="dry_run_official_api"` without submitting. If config is incomplete, it falls back to manual mode.
- `browser_automation`: explicit placeholder only. It returns `status="unsupported"` and does not import or use Selenium, Playwright, Puppeteer, browser cookies, copied browser requests, DOM clicking, or form submission.

To enable official API bidding after eBay grants access, set all of the following deliberately:

```bash
EBAY_BIDDING_MODE=official_api
EBAY_BIDDING_ENABLED=true
EBAY_BUY_OFFER_API_ENABLED=true
EBAY_REQUIRE_HUMAN_CONFIRMATION=false
EBAY_USER_ACCESS_TOKEN=<optional current user OAuth token with buy.offer.auction scope>
EBAY_USER_REFRESH_TOKEN=<user refresh token>
```

Then call `run_mvp(..., dry_run=False)`. The app uses the RESTful Browse API item ID such as `v1|...|0`; legacy `/itm/123...` IDs are not used for `place_proxy_bid`.

Final bid guardrails still run before any action result is created. They cap recommendations at `max_bid_cap`, block low-confidence analysis, block low-margin opportunities, reject ended auctions, reject seller mismatches, and reject suspicious analysis flags.

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
- manual, official API fallback, official API dry-run/submission, and browser-automation-disabled bidding modes
- final bid guardrails for max cap, low confidence, low margin, and seller mismatch

## Live Integration Notes

The code is structured so live integrations can be added without rewriting the architecture:

- [app/clients/ebay.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay.py): `OfficialEbayApiClient` uses OAuth client credentials and Browse API search/getItem calls
- live market context enrichment is still a TODO; the second prompt agent currently reasons over listing data plus supplied market context instead of a dedicated external pricing source
- [app/clients/ebay_offer.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay_offer.py): `OfficialEbayOfferApiClient` calls only eBay's official Buy Offer API `place_proxy_bid` endpoint
- [app/tools/bid_execution_tool.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/tools/bid_execution_tool.py): `OfficialEbayBiddingService` gates official API bid submission behind config, credentials, dry-run, human-confirmation, and guardrails
- eBay automated bidding requires official API access. The app does not use website automation, cookie replay, Selenium, Playwright, Puppeteer, or copied browser curl requests to place bids.

## Notes

- Shipping cost is intentionally excluded from the MVP model because the target workflow assumes cards remain in the PSA Vault.
- The Pokemon enum allow-list is a strict filter and is applied before the prompt-driven auction-search and market-analysis stages.
- Duplicate unsafe bidding is guarded by SQLite-backed bid-attempt checks in the deterministic bid guardrail layer.
- The market-analysis prompt is expected to recommend bids only when the outlook is steady or upward; deterministic guardrails reject downward outlooks.
