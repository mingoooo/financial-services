# Trade Like O'Neil — managed-agent template

## Overview

Single name or watchlist → market regime → leadership test → setup classification → trade plan. Same source as the [`trade-like-oneil`](../../plugins/agent-plugins/trade-like-oneil) Cowork plugin — this directory is the Managed Agent cookbook for `POST /v1/agents`.

## Deploy

```bash
export ANTHROPIC_API_KEY=sk-ant-...
../../scripts/deploy-managed-agent.sh trade-like-oneil
```

## Steering events

See [`steering-examples.json`](./steering-examples.json). Good fit for single-name setup review, watchlist triage, and portfolio action summaries.

## Security & handoffs

This agent is analysis-only and uses no external connectors by default. Single-tier isolation:

| Tier | Touches untrusted docs? | Tools | Connectors |
|---|---|---|---|
| `trade-planner` / Orchestrator | No | `Read`, `Grep`, `Glob`, `Agent` | None |

Outputs are concise markdown by default. If a downstream workflow needs order routing, hand off the resulting plan to a separate execution system rather than placing orders directly.
