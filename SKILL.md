# Skill — Run the OKX Price Court demo (Internet Court on GenLayer)

Use this skill to reproduce the OKX Price Court demo end-to-end: deploy an
Intelligent Contract on GenLayer Studio Next, file two market-fact disputes,
let a jury of validators fetch the evidence from OKX (an Internet Court
founding member) and rule by consensus, and read the verdicts back.

## Prerequisites

- Python 3.11+ with `rlp`, `eth-abi`, `eth-account`, `eth-utils`
  (`pip install rlp eth-abi eth-account eth-utils`)
- A text file containing one `0x…` private key for a wallet funded with test
  GEN on **GenLayer Studio Next** (chainId 61997,
  RPC `https://studio-dev.genlayer.com/api`). Never print or share the key.
- Internet access to `studio-dev.genlayer.com` and `www.okx.com`.

## Steps

1. **Deploy (or reuse).** Run:
   `python3 app/deploy_and_run.py <keyfile>`
   The script builds the tuple-form `addTransaction` that Studio Next's
   consensus requires (fees distribution derived live from
   `sim_getFeeConfig`), deploys `contracts/okx_price_court.py`, and records
   the address in `app/deployment.json`. If that file exists, deployment is
   skipped.
2. **File a case.** A case is
   `(case_id, instrument, date, threshold, claim)` — e.g.
   `("case-001-btc-2026-11-19", "BTC-USDT", "2026-11-19", "59000", "<deal term>")`.
   The claim is always of the form: *the UTC daily close of `instrument` on
   OKX on `date` was at or above `threshold` USDT.*
3. **Resolve.** `resolve_case(case_id)` triggers consensus: each validator
   renders `https://www.okx.com/api/v5/market/history-candles?instId=…&bar=1D`
   for the disputed day, extracts the confirmed close, and an LLM jury writes
   a one-sentence ruling. Equivalence principle: identical close + verdict,
   free wording for the ruling. Finalization takes a few minutes.
4. **Read the verdict.** `get_case(case_id)` (a `gen_call`) returns JSON with
   `status`, `close`, `verdict`, `ruling`, and the OKX `evidence_url`.
5. **Verify independently.** Open the OKX evidence URL yourself and compare
   the candle's close with the on-chain verdict; open the contract on
   `https://explorer-studio-dev.genlayer.com/address/<address>`.

## Expected results (recorded run)

- `case-001-btc-2026-11-19`: close **61,984.8** ≥ 59,000 → verdict **true**
  (claim upheld).
- `case-002-btc-2026-11-18`: close **63,070.6** < 65,000 → verdict **false**
  (claim rejected).

Full tx hashes and rulings: `evidence/demo_result.json`.

## Failure modes

- `sim_getFeeConfig` errors → the target chain is not Studio Next; the tuple
  variant does not apply (use `app/court.mjs` on studionet 61999 instead).
- Tx ends `UNDETERMINED` → validators disagreed; read the tx on the explorer,
  check the OKX candle is confirmed (`confirm = "1"`), then re-run — the
  driver skips already-resolved cases.
- `no confirmed OKX candle` → the disputed date is today/future or the
  instrument is wrong; pick a past UTC day.
