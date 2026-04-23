# psa-pokemon-bidder

`psa-pokemon-bidder` is a production-minded Python MVP for scanning PSA's official eBay listings, filtering to a strict allow-list of target Pokemon, researching PriceCharting comps, analyzing bid opportunities, and placing bids through a multi-agent workflow.

The project is intentionally narrow:

- PSA official eBay account only
- Pokemon cards only
- auction listings only
- PSA graded cards only
- strict Pokemon enum allow-list
- listings must explicitly state `"In the PSA Vault"`
- dry-run bidding supported now
- live eBay API bidding and live PriceCharting scraping are cleanly stubbed for later wiring

## Architecture

This is a true multi-agent MVP from day one, not a monolithic pipeline.

Agent roles:

- `ScannerAgent`: fetches raw listings from an eBay client adapter
- `ValidationAgent`: handles raw pre-validation and parsed scope/rule validation
- `ParsingAgent`: normalizes titles and extracts structured listing details
- `PriceResearchAgent`: finds PriceCharting matches and grade prices
- `AnalysisAgent`: produces structured bid analysis using LangChain-compatible agent logic
- `BiddingAgent`: applies deterministic bid guardrails and executes dry-run bids
- `SupervisorAgent`: coordinates the end-to-end run and agent handoffs

Orchestration:

- The per-listing workflow is modeled as a LangGraph state machine in [app/workflows/mvp_workflow.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/workflows/mvp_workflow.py).
- Deterministic Python handles ingestion, parsing, validation, guardrails, persistence, and bid execution mechanics.
- LangChain-style structured analysis lives in [app/agents/analysis_agent.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/agents/analysis_agent.py), with an OpenAI-backed structured-output path and a local heuristic fallback so the MVP runs without credentials.

## Project Layout

```text
app/
  agents/
  clients/
  models/
  prompts/
  services/
  storage/
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
- [data/sample_pricecharting.json](/Users/yaroslawbagriy/Dev/psa-auction-agent/data/sample_pricecharting.json): mock PriceCharting card/comps data
- [app/storage/sqlite.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/storage/sqlite.py): SQLite persistence for listings, analysis, bids, and errors

## Core Models

The main typed models live under [app/models](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/models):

- `Pokemon`: enum-based allow-list input
- `TargetRules`: business rules like allowed grades and max current price
- `SearchConfig`: runtime search/bid configuration
- `RawListing` and `Listing`: ingestion and normalized listing models
- `PriceResearchResult`
- `AnalyzerInput` and `AnalysisResult`
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
    ),
    dry_run=True,
)
```

## Workflow

The implemented MVP flow is:

1. fetch listings from the eBay client
2. pre-validate seller, auction type, and raw Pokemon scope
3. parse normalized listing details
4. validate PSA grading, Pokemon allow-list, vault phrase, and target rules
5. research PriceCharting comps
6. analyze opportunity and max bid
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
4. Run the dry-run MVP:

```bash
python scripts/run_mvp.py
```

The default run uses mock eBay data, mock PriceCharting data, SQLite persistence, and a deterministic heuristic analyzer. That means it is runnable locally without live credentials.

## Tests

Run the tests with:

```bash
pytest
```

Current coverage includes:

- title parsing and Pokemon detection
- PSA Vault detection
- validation and allow-list behavior
- end-to-end dry-run workflow behavior against sample data

## What Is Stubbed

The code is structured so live integrations can be added without rewriting the architecture:

- [app/clients/ebay.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/ebay.py): `OfficialEbayApiClient` is a TODO stub for authenticated PSA/eBay API integration
- [app/clients/pricecharting.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/clients/pricecharting.py): `ScrapingPriceChartingClient` is a TODO stub for resilient live scraping
- [app/agents/bidding_agent.py](/Users/yaroslawbagriy/Dev/psa-auction-agent/app/agents/bidding_agent.py): `RealEbayBidExecutor` is a TODO stub for live bidding

## Notes

- Shipping cost is intentionally excluded from the MVP model because the target workflow assumes cards remain in the PSA Vault.
- The Pokemon enum allow-list is a strict filter and is applied before deeper analysis.
- Duplicate unsafe bidding is guarded by SQLite-backed bid-attempt checks in the deterministic bid guardrail layer.
