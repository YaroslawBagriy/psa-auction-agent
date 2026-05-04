# psa-pokemon-bidder

`psa-pokemon-bidder` is a production-minded Python MVP for scanning PSA's official eBay listings, filtering to a strict allow-list of target Pokemon, using prompt-driven agents to choose viable auction links and estimate market value/max bids, and then producing safe manual bidding recommendations by default.

The project is intentionally narrow:

- PSA official eBay account only
- Pokemon cards only
- auction listings only
- PSA graded cards only
- strict Pokemon enum allow-list
- listings must explicitly indicate `"In the PSA Vault"` on the listing page or in structured page metadata
- the script polls every 15 minutes in continuous mode
- manual bidding is the default MVP behavior
- the app does not place bids through eBay website automation
- live eBay Browse API fetching is implemented behind explicit credentials
- official eBay Buy Offer API proxy bidding is implemented but gated behind explicit config, user OAuth, dry-run=false, human-confirmation=false, and eBay approval

## Architecture

This is a true multi-agent MVP from day one, not a monolithic pipeline.

Agent roles:

- `AuctionSearchAgent`: uses a LangChain prompt to choose which validated eBay listing links should move forward
- `MarketQueryPlannerAgent`: uses a LangChain prompt to produce exact-title and normalized eBay comp search queries
- `MarketResearchAgent`: uses an LLM web-search prompt to research eBay solds, eBay active listings, PriceCharting, and other public comp sources
- `AnalysisAgent`: uses a LangChain prompt to estimate market value, assess price trend direction, and produce a max bid for each selected listing
- `SupervisorAgent`: coordinates the LangChain runnable chain and agent handoffs

Deterministic tools:

- `ScannerTool`: fetches raw listings from the configured eBay client adapter
- `ListingPreparationTool`: parses listings and applies hard scope filters before any LLM call
- `MarketResearchTool`: attaches structured market evidence from the LLM web-research agent, or from the optional official eBay API adapter when explicitly configured
- `BidExecutionTool`: applies deterministic guardrails and prepares a safe bid action result

Orchestration:

- The supervisor scans the eBay search result page/set, then streams each enriched auction through the full agent workflow one listing at a time. Each listing gets an accepted/denied verdict and reason before the next listing is processed.
- The end-to-end cycle is wired as a LangChain runnable chain inside [app/agents/supervisor_agent.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/agents/supervisor_agent.py).
- Deterministic Python handles ingestion, parsing helpers, scope filters, persistence, guardrails, and safe bid-action preparation.
- The prompt agents use LangChain runnable composition in the `prompt | llm.with_structured_output(...)` style. Auction selection and market/max-bid analysis always go through the LLM; there is no runtime heuristic fallback.

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
- [app/agents/market_research_agent.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/agents/market_research_agent.py): LLM web-search market research agent
- [app/tools/market_research_tool.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/tools/market_research_tool.py): market evidence enrichment tool
- [app/tools/bid_execution_tool.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/tools/bid_execution_tool.py): deterministic bidding guardrail and safe bid-action service
- [app/prompts/auction_search_prompt.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/prompts/auction_search_prompt.py): auction-search prompt that selects listing links
- [app/prompts/analysis_prompt.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/prompts/analysis_prompt.py): comp-driven market-analysis/max-bid prompt

## Core Models

The main typed models live under [app/models](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/models):

- `Pokemon`: enum-based allow-list input
- `CardLanguage`: normalized card language, such as English or Japanese, detected from PSA-style titles and item specifics
- `TargetRules`: business rules like allowed grades and max current price
- `SearchConfig`: runtime search/bid configuration
- `RawListing` and `Listing`: ingestion and normalized listing models
- `AuctionSearchDecision` and `AuctionSearchResult`
- `MarketResearchResult`: active listings, sold comps, sell-through rate, recent sold prices, and evidence summary
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
        allowed_grades={"8", "9", "10"},
        max_current_price=1500.0,
    ),
    dry_run=True,
)
```

## Workflow

The implemented MVP flow is:

1. fetch PSA auction summaries from the eBay client
2. enrich and process each auction one at a time through the rest of the workflow
3. pre-validate seller, auction type, and raw Pokemon scope for that auction
4. parse normalized listing details for that auction, including card language when it appears in PSA-style title text such as `JAPANESE`, `JPN`, or `EN-...`
5. validate PSA grading, Pokemon allow-list, explicit listing-page vault evidence, and target rules
6. send that single validated listing to the `AuctionSearchAgent` prompt
7. if selected, use the `MarketQueryPlannerAgent` to create exact-title and normalized comp queries
8. use the `MarketResearchAgent` to search public sources such as eBay and PriceCharting for active listings, sold comps, sell-through, recent sold prices, and market value, treating language as a hard comp-matching field
9. send that enriched listing to the `AnalysisAgent` prompt to estimate market value, trend outlook, and max bid
10. apply deterministic bid guardrails
11. log an accepted/denied verdict with the current stage and reason before moving to the next listing
12. create a manual bid action result, or a gated official eBay Offer API proxy-bid result when explicitly enabled, with the title, item ID, current price, end time, estimated market value, max bid, margin, reasoning, and eBay URL
13. persist every major step to SQLite

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

To print a compact recommendation/review report instead of the full workflow JSON:

```bash
python scripts/run_mvp.py --once --recommendations-only
```

For quicker live checks, reduce the number of PSA listings fetched:

```bash
python scripts/run_mvp.py --once --recommendations-only --scan-limit 25
```

The runner targets every Pokemon currently supported by the enum by default. To narrow the allow-list for a run:

```bash
python scripts/run_mvp.py --once --recommendations-only --pokemon pikachu charizard gengar
```

The default script now allows PSA grades 8, 9, and 10. To broaden or narrow grades for a run:

```bash
python scripts/run_mvp.py --once --recommendations-only --grades 6 7 8 9 10
```

For a live class demo where you want more listings to make it deeper into the agent workflow, use demo mode:

```bash
python scripts/run_mvp.py --once --recommendations-only --scan-limit 100 --demo-mode
```

Demo mode is intentionally labeled. It targets all supported Pokemon, allows PSA grades 6-10, raises the current-price review cap to `$2500`, lowers the confidence threshold to `0.55`, permits uncertain trend labels, and sets the minimum expected margin to `$0`. Bidding still remains dry-run/manual, and the output includes `showcase_auctions` so the demo can show analyzed listings even when final bid guardrails deny them.

Useful live-demo tuning options:

```bash
python scripts/run_mvp.py --once --recommendations-only --scan-limit 150 --demo-mode --showcase-limit 12
python scripts/run_mvp.py --once --recommendations-only --all-pokemon --grades 7 8 9 10 --min-margin 5
python scripts/run_mvp.py --once --recommendations-only --pokemon pikachu charizard rayquaza lugia gengar --grades 8 9 10
```

5. Run continuous polling every 15 minutes:

```bash
python scripts/run_mvp.py
```

Set `OPENAI_API_KEY` and `OPENAI_MODEL` before running. The auction-search and market-analysis agents are always prompt-driven LLM agents; if `OPENAI_API_KEY` is missing, the app fails fast instead of producing heuristic recommendations.

The default run uses mock eBay data unless `USE_LIVE_EBAY=true`, SQLite persistence, and LLM prompt agents. The sample eBay data includes market-context snapshots and relative end times so bidding logic can be exercised locally.

Listing ingestion is not LLM scraping today. In dry-run mode, `MockEbayClient` loads [data/sample_ebay_listings.json](/Users/yaroslawbagriy/Dev/psa-auction-agent/data/sample_ebay_listings.json). In live mode, [app/clients/ebay.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay.py) uses the eBay Browse API to search PSA's official `/str/psa` seller account for auction listings and then enriches item details. The eBay seller username for that store is `psa`, so the live Browse API filter is `sellers:{psa},buyingOptions:{AUCTION}`. Optional listing-page enrichment only looks for the literal `"In the PSA Vault"` phrase because that signal may appear on the listing page rather than the title.

Live eBay settings:

- `USE_LIVE_EBAY=true`
- `EBAY_SCAN_LIMIT=100` controls how many PSA listings the scanner fetches per cycle; lower it for quick manual checks.
- `EBAY_LISTING_PAGE_TIMEOUT_SECONDS=5` controls the per-listing page enrichment timeout used for `"In the PSA Vault"` detection.
- `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` mint an application token for Browse API calls, or `EBAY_ACCESS_TOKEN` can provide a pre-minted application token.
- `EBAY_MARKET_RESEARCH_ENABLED=true` enables the MarketResearchTool stage.
- `MARKET_RESEARCH_MODE=llm_web` is the default market research mode. It uses OpenAI web search and public sources rather than eBay Marketplace Insights for sold comps.
- `OPENAI_MARKET_RESEARCH_MODEL` can override the model used by the web market research agent.
- `OPENAI_MARKET_RESEARCH_DOMAIN_FILTERS_ENABLED=false` leaves OpenAI web-search domain filters disabled by default. Some models, including `gpt-4.1-mini`, reject the `filters.allowed_domains` parameter.
- `OPENAI_MARKET_RESEARCH_ALLOWED_DOMAINS=ebay.com,pricecharting.com,130point.com,psacard.com,tcgplayer.com` is only sent to OpenAI when `OPENAI_MARKET_RESEARCH_DOMAIN_FILTERS_ENABLED=true`; otherwise the prompt still prefers eBay sold comps and public card-price sources.
- `MARKET_RESEARCH_MODE=official_ebay_api` switches back to the official eBay market-research adapter.
- `EBAY_MARKETPLACE_INSIGHTS_ENABLED=true` enables sold-comp lookup through eBay's limited-release Buy Marketplace Insights API only when `MARKET_RESEARCH_MODE=official_ebay_api`.
- `EBAY_MARKETPLACE_INSIGHTS_SCOPE=https://api.ebay.com/oauth/api_scope/buy.marketplace.insights` is the app-token scope used for official sold-comp research.
- `EBAY_DEV_ID` can be stored for account reference, but REST Browse and Buy Offer calls use the Client ID and Client Secret.
- `EBAY_RU_NAME` is required only when generating a user token through eBay's authorization-code flow.
- `EBAY_OAUTH_SCOPES` controls helper-script token generation. Use `https://api.ebay.com/oauth/api_scope` for public Browse API tokens. Add `https://api.ebay.com/oauth/api_scope/buy.offer.auction` only after eBay grants that scope to the application.
- `EBAY_BIDDING_MODE=manual` is the default and recommended MVP setting while API access is pending.
- `EBAY_BIDDING_MODE=official_api` uses eBay's official Buy Offer API `place_proxy_bid` endpoint only when all required flags and user OAuth credentials are present. If credentials, approval, or safety flags are missing, the app falls back to manual bidding.
- `EBAY_BIDDING_MODE=browser_automation` is explicitly unsupported and returns an unsupported result.
- `EBAY_ENVIRONMENT=sandbox` switches supported official eBay API endpoints to sandbox.
- `EBAY_USER_REFRESH_TOKEN` lets the app mint a fresh user access token with eBay's official OAuth refresh-token flow when needed.

OAuth helper commands:

```bash
python scripts/ebay_oauth.py app-token --write-env
python scripts/ebay_oauth.py auth-url
python scripts/ebay_oauth.py exchange-code --code "<code-from-ebay-redirect>" --write-env
python scripts/ebay_oauth.py refresh-user-token --write-env
```

The helper redacts token values in terminal output. When `--write-env` is passed, it writes tokens to the ignored local `.env` file.

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
EBAY_OAUTH_SCOPES="https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/buy.offer.auction"
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
- LLM web market research over public sources such as eBay and PriceCharting
- optional official eBay active/sold market comp parsing and MarketResearchTool enrichment
- LLM comp-query planning that sends exact title first and normalized variants second
- optional bidding-window validation when explicitly configured
- validation and allow-list behavior
- end-to-end dry-run workflow behavior against sample data
- manual, official API fallback, official API dry-run/submission, and browser-automation-disabled bidding modes
- final bid guardrails for max cap, low confidence, low margin, and seller mismatch

## Live Integration Notes

The code is structured so live integrations can be added without rewriting the architecture:

- [app/clients/ebay.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay.py): `OfficialEbayApiClient` uses OAuth client credentials and Browse API search/getItem calls
- [app/agents/market_research_agent.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/agents/market_research_agent.py): `OpenAIWebMarketResearchEngine` uses OpenAI Responses API web search to gather public market evidence
- [app/clients/ebay_market.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay_market.py): `OfficialEbayMarketResearchClient` remains available as an optional adapter for Browse API active comps and the limited-release Marketplace Insights item-sales endpoint
- [app/clients/ebay_offer.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay_offer.py): `OfficialEbayOfferApiClient` calls only eBay's official Buy Offer API `place_proxy_bid` endpoint
- [app/tools/bid_execution_tool.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/tools/bid_execution_tool.py): `OfficialEbayBiddingService` gates official API bid submission behind config, credentials, dry-run, human-confirmation, and guardrails
- eBay automated bidding requires official API access. The app does not use website automation, cookie replay, Selenium, Playwright, Puppeteer, or copied browser curl requests to place bids.

## Notes

- Shipping cost is intentionally excluded from the MVP model because the target workflow assumes cards remain in the PSA Vault.
- The Pokemon enum allow-list is a strict filter and is applied before the prompt-driven auction-search and market-analysis stages.
- Duplicate unsafe bidding is guarded by SQLite-backed bid-attempt checks in the deterministic bid guardrail layer.
- The market-analysis prompt is expected to recommend bids only when exact comp evidence, sell-through, and trend are healthy; deterministic guardrails reject downward outlooks.
