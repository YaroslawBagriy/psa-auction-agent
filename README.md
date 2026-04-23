# psa-auction-agent

An automated Python + LangChain project for scanning PSA's official eBay account, identifying target Pokémon card auctions, analyzing potential opportunities, and placing bids automatically.

## Overview

This project is a focused MVP for an automated trading workflow in the Pokémon card market.

The system is designed to:

- monitor **PSA’s official eBay account**
- find **Pokémon card auction listings**
- keep only **PSA graded cards**
- filter to a user-provided list of target Pokémon
- analyze candidate listings
- automatically place bids on qualifying auctions

For the MVP, this project only handles the **buying side**. It does **not** automate relisting or selling purchased cards.

## MVP Scope

The MVP is intentionally narrow.

It only supports:

- PSA official eBay account
- Pokémon cards only
- auction listings only
- PSA graded cards only
- cards matching user-defined target rules
- automatic bidding only
- no automatic selling

Example target Pokémon input:

```python
from app.models.pokemon import Pokemon

targets = [Pokemon.PIKACHU, Pokemon.CHARIZARD, Pokemon.GENGAR]
