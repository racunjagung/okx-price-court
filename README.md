# OKX Price Court — Internet Court: Partner Demo Lab

**A working Internet Court demo:** when two AI agents disagree about a market
fact, a jury of GenLayer validators fetches the evidence from the partner's
own API and rules on the claim — by consensus, on-chain.

- **Court / adjudication layer:** [GenLayer](https://genlayer.com) Intelligent
  Contracts (Optimistic Democracy: 5 validators, independent execution,
  equivalence-principle consensus)
- **Partner:** **OKX** — founding member of the
  [Internet Court](https://internetcourt.org) consortium (see
  [Step 1 — partner evidence](#partner-choice--evidence))
- **Partner data:** OKX public REST API v5 (`market/history-candles`), no API
  key required
- **Network:** GenLayer Studio Next testnet, chainId **61997**
  (RPC `https://studio-dev.genlayer.com/api`)

## The use case

Agent-to-agent deals routinely hinge on an external fact:

> *"BTC-USDT closed at or above 59,000 USDT on OKX on 2026-11-19."*

One side says the condition was met, the other disputes it. A normal smart
contract cannot settle that — the fact lives off-chain, on the partner's
systems. `OkxPriceCourt` can:

1. **`file_case(case_id, instrument, date, threshold, claim)`** — anyone opens
   a dispute describing the deal term in natural language.
2. **`resolve_case(case_id)`** — every validator independently renders the
   OKX history-candles API for the disputed day, extracts the *confirmed*
   daily close, and an LLM jury phrases a one-sentence ruling. The contract's
   Equivalence Principle requires all validators to agree on the **exact close
   price and the verdict**; only the ruling's wording may vary.
3. The verdict, the closing price, the ruling and the evidence URL are stored
   on-chain, readable by anyone via **`get_case(case_id)`**.

GenLayer is not decorative here: the fetch, the judgment and the consensus
*are* the product. Remove GenLayer and there is no court — only two agents
shouting.

## Demo run (real, on testnet)

Executed end-to-end on Studio Next — see [`evidence/demo_result.json`](evidence/demo_result.json)
and [`evidence/deploy_tx.json`](evidence/deploy_tx.json):

| Case | Disputed term | OKX close | Verdict |
|---|---|---|---|
| `case-001-btc-2026-11-19` | BTC-USDT close ≥ 59,000 on 2026-11-19 | 61,984.8 | claim upheld |
| `case-002-btc-2026-11-18` | BTC-USDT close ≥ 65,000 on 2026-11-18 | 63,070.6 | claim rejected |

Contract address, deploy tx and per-case tx hashes are recorded in
`evidence/demo_result.json`. A 45-second walkthrough is in
[`video/`](video/).

## Reproduce it

### Option A — Python driver (Studio Next, recommended)

The current `genlayer-js` release only speaks the legacy `addTransaction`
ABI; Studio Next's consensus contract requires the newer *tuple*
`addTransaction` (payable, fees distribution built from the node's
`sim_getFeeConfig`). `app/deploy_and_run.py` implements that variant directly
(the same construction the GenLayer portal's Wizard flow uses):

```bash
cd app
python3 -m venv .venv && . .venv/bin/activate
pip install rlp eth-abi eth-account eth-utils
python3 deploy_and_run.py /path/to/funded-studio-testnet-key.txt
```

The key file holds one `0x…` private key of a wallet funded with test GEN on
Studio Next (the portal's Wizard of Coin flow funds W1-class wallets there;
`sim_getFeeConfig` must be enabled on the target chain). The script deploys
the contract (or reuses `app/deployment.json`), files both demo cases,
resolves them through validator consensus, and writes
`evidence/demo_result.json`. It is idempotent: already-resolved cases are
skipped.

### Option B — verify the recorded run (Node, read-only)

`app/court.mjs` uses the official `genlayer-js` client to read the verdicts
straight from the deployed contract — no trust in this repo's evidence files
required (reads go through `gen_call`, which works on Studio Next; only
writes need the tuple form):

```bash
cd app
npm install
node court.mjs verify          # court name + both demo cases
node court.mjs get case-001-btc-2026-11-19
```

### Option C — read a verdict right now

Open `index.html` in a browser: it renders the recorded cases and verdicts
from `evidence/demo_result.json`, with links to the contract on the
Studio Next explorer.

## Partner choice & evidence

The mission asks for an **Internet Court partner**. The consortium's founding
members are published by the Internet Court itself:

- Press release, internetcourt.org (2 Jul 2026): *"A consortium of 27
  companies … today announced the launch of Internet Court"* — naming
  GenLayer Foundation/Labs, Matter Labs' ZKsync, **OKX** ("global
  cryptocurrency exchange OKX"), 0G Labs, ConsenSys MetaMask, among others.
  <https://www.internetcourt.org/blog/press-release>
- The official skill repository (`internet-court/internet-court-skill`) lists
  the founding members verbatim: *"GenLayer, MetaMask, **OKX**, NEAR,
  Starknet, x402, 0G Labs, ZKsync, Nansen, Kleros, Privy, AntSeed, Collective
  Memory, UMA, Arkhai, AltLayer, Anoma, AppLayer, BNB Chain, LI.FI,
  Chainbase, io.net, Heurist, Chutes, ChainGPT, OpenServ, Humanode, Humanity
  Protocol."*

OKX was chosen because it is a named founding member **and** exposes a
free, keyless, public market-data API — so the court can cite the partner's
own records as evidence. (CoinGecko, although it appears in an unrelated
GenLayer portal task, is **not** an Internet Court consortium member and was
therefore not used as the partner.)

## Layout

```
contracts/okx_price_court.py   the Intelligent Contract
app/deploy_and_run.py          Studio Next driver (tuple addTransaction)
app/court.mjs                  genlayer-js read-only verifier CLI
app/deployment.json            deployed contract address + explorer link
evidence/demo_result.json      the recorded demo run (tx hashes, verdicts)
evidence/deploy_tx.json        raw finalized deploy transaction
assets/                        official logos (Internet Court, GenLayer, OKX)
video/                         45s demo video + build script
index.html                     static verdict viewer
SKILL.md                       agent skill: reproduce this demo step-by-step
```

## Notes & limits

- Testnet only. No mainnet funds, no real assets; verdicts concern testnet
  demo cases about public market data.
- Daily candles are taken from OKX's UTC daily bar and must be *confirmed*
  (`confirm = "1"`) — the contract refuses unconfirmed candles.
- The submission to the GenLayer portal (mission 101) is performed by a human
  from this repository + the demo video; this repo contains everything the
  portal form asks for.
