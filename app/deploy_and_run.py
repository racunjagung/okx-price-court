#!/usr/bin/env python3
"""OKX Price Court — deploy + demo driver for GenLayer Studio Next (61997).

Why this exists: the current `genlayer-js` release only speaks the legacy
addTransaction ABI (V5/V6, nonpayable). Studio Next's consensus contract
requires the newer *tuple* addTransaction (payable, with a feesDistribution
built from the node's own sim_getFeeConfig) — the same variant the GenLayer
portal's Wizard of Coin flow uses. This script implements that variant
directly (patterns proven by ~/workspace/testnet-missions/genlayer/
genlayer_wizard.py) and drives the whole demo:

  deploy OkxPriceCourt -> file 2 cases -> resolve both via validator
  consensus (validators fetch OKX candles + LLM jury ruling) -> read the
  verdicts back with gen_call and write evidence/demo_result.json.

Usage: deploy_and_run.py <keyfile>
The key is read from the file and never printed.
"""
import json, sys, os, time, subprocess, urllib.request, urllib.error

import rlp
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_utils import keccak

RPC = "https://studio-dev.genlayer.com/api"
CHAIN_ID = 61997
ZERO = "0x0000000000000000000000000000000000000000"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONTRACT_PATH = os.path.join(ROOT, "contracts", "okx_price_court.py")
EVIDENCE = os.path.join(ROOT, "evidence")
CONSENSUS_FALLBACK = "0xb7278A61aa25c888815aFC32Ad3cC52fF24fE575"


# ---------------------------------------------------------------- calldata
def leb128(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def gl_enc(v):
    if isinstance(v, str):
        b = v.encode()
        return leb128((len(b) << 3) | 4) + b
    if isinstance(v, bool):
        return bytes([(2 << 3) | 0]) if v else bytes([(1 << 3) | 0])
    if isinstance(v, int):
        if v >= 0:
            return leb128((v << 3) | 1)
        return leb128(((-v - 1) << 3) | 2)
    if isinstance(v, (list, tuple)):
        out = bytearray(leb128((len(v) << 3) | 5))
        for item in v:
            out += gl_enc(item)
        return bytes(out)
    if isinstance(v, dict):
        items = sorted(v.items())
        out = bytearray(leb128((len(items) << 3) | 6))
        for k, val in items:
            kb = k.encode()
            out += leb128(len(kb)) + kb + gl_enc(val)
        return bytes(out)
    raise TypeError(f"unsupported {type(v)}")


def gl_dec_str(buf, pos=0):
    """Decode one calldata value; returns (value, next_pos). Only the types
    this demo reads back are supported (str / pint / bool / null)."""
    n = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        n |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            break
    tag = n & 7
    val = n >> 3
    if tag == 4:
        return buf[pos:pos + val].decode(), pos + val
    if tag == 1:
        return val, pos
    if tag == 0:
        return {0: None, 1: False, 2: True}.get(val), pos
    raise ValueError(f"unsupported tag {tag}")


# -------------------------------------------------------------------- rpc
def rpc(method, params, timeout=60, tries=5):
    """JSON-RPC via curl: this RPC truncates large responses (tx objects are
    ~80 KB) under urllib (IncompleteRead); curl --retry is the transport the
    workspace's proven GenLayer scripts use for exactly this reason."""
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params})
    last = None
    for k in range(tries):
        try:
            proc = subprocess.run(
                ["curl", "-s", "--retry", "3", "--retry-all-errors",
                 "--max-time", str(timeout), "-X", "POST", RPC,
                 "-H", "Content-Type: application/json",
                 "-H", f"User-Agent: {UA}", "-d", payload],
                capture_output=True, text=True, timeout=timeout + 30)
            out = json.loads(proc.stdout)
            if "error" in out:
                raise RuntimeError(f"RPC {method}: {out['error']}")
            return out["result"]
        except Exception as e:
            last = e
            print(f"  rpc {method} try{k} err: {str(e)[:110]}", flush=True)
            time.sleep(4)
    raise RuntimeError(f"rpc {method} failed after {tries}: {last}")


# ------------------------------------------------------- consensus sending
TUPLE_TYPE = ("(address,address,uint256,uint256,uint256,uint256,uint256,"
              "(uint256,uint256,uint256,uint256,uint256,uint256,uint256[],"
              "uint256,uint256,uint256),bytes,"
              "(uint8,bool,uint256,address,bytes32,uint256,bytes)[])")


EXEC_BUDGET_MULTIPLIER = 1


def fee_plan(fee_config, validators=5, rotations=3):
    if not fee_config or not fee_config.get("enabled"):
        return None
    base = fee_config["defaultFees"]["distribution"]
    leader = int(base["leaderTimeunitsAllocation"])
    validator = int(base["validatorTimeunitsAllocation"])
    # Node default per-round execution budget, as used by the portal's own
    # wizard flow. (Two earlier deploys failed only because the contract's
    # Depends hash named a non-existent py-genlayer runner — the budget was
    # never the problem.)
    exec_budget = int(base["executionBudgetPerRound"]) * EXEC_BUDGET_MULTIPLIER
    max_price = int(base["maxPriceGenPerTimeUnit"])
    overlay = int(fee_config["policy"]["timeUnitOverlayBps"])
    u = (rotations + 1) * (leader + validators * validator)
    if max_price > 0:
        u *= max_price
    d = 0 if overlay == 0 else u * overlay // (10000 - overlay)
    fee_value = u + d + exec_budget * (rotations + 1)
    distribution = (leader, validator, int(base["appealRounds"]), exec_budget,
                    int(base["executionConsumed"]),
                    int(base["totalMessageFees"]), [rotations], max_price,
                    int(base["storageFeeMaxGasPrice"]),
                    int(base["receiptFeeMaxGasPrice"]))
    return distribution, fee_value


def abi_add_transaction_tuple(sender, recipient, nval, nrot, valid_until,
                              distribution, tx_data):
    params = (sender, recipient, nval, nrot, valid_until, 0, 0,
              distribution, tx_data, [])
    enc = abi_encode([TUPLE_TYPE], [params])
    sel = keccak(text=f"addTransaction({TUPLE_TYPE})")[:4]
    return "0x" + (sel + enc).hex()


class Court:
    def __init__(self, acct):
        self.acct = acct
        self.addr = acct.address
        try:
            cons = rpc("sim_getConsensusContract", ["ConsensusMain"])
            self.consensus = cons["address"]
        except Exception:
            self.consensus = CONSENSUS_FALLBACK
        fee_config = rpc("sim_getFeeConfig", [])
        plan = fee_plan(fee_config)
        if not plan:
            raise RuntimeError("fee config unavailable — tuple variant required")
        self.distribution, self.fee_value = plan
        print(f"consensus={self.consensus} feeValue={self.fee_value}", flush=True)

    def send(self, recipient, tx_data, label):
        valid_until = int(time.time()) + 3600
        data = abi_add_transaction_tuple(self.addr, recipient, 5, 3,
                                         valid_until, self.distribution,
                                         tx_data)
        nonce = int(rpc("eth_getTransactionCount", [self.addr, "pending"]), 16)
        try:
            gas = int(rpc("eth_estimateGas", [{
                "from": self.addr, "to": self.consensus,
                "value": hex(self.fee_value), "data": data}]), 16)
            gas = int(gas * 1.3) + 10000
        except Exception as e:
            print(f"  estimateGas failed ({str(e)[:70]}); fallback gas", flush=True)
            gas = 3_000_000
        tx = {"chainId": CHAIN_ID, "nonce": nonce, "gasPrice": 0,
              "gas": gas, "to": self.consensus, "value": self.fee_value,
              "data": data}
        signed = self.acct.sign_transaction(tx)
        raw = signed.raw_transaction.hex()
        if not raw.startswith("0x"):
            raw = "0x" + raw
        tx_hash = rpc("eth_sendRawTransaction", [raw])
        print(f"{label}: tx {tx_hash} (nonce {nonce})", flush=True)
        return tx_hash

    def wait_finalized(self, tx_hash, label, timeout_s=1500):
        last = None
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            time.sleep(15)
            tx = rpc("eth_getTransactionByHash", [tx_hash])
            if tx is None:
                continue
            status = tx.get("status")
            if status != last:
                print(f"  [{label}] status={status} "
                      f"exec={tx.get('txExecutionResultName')}", flush=True)
                last = status
            if status == "FINALIZED":
                return tx
            if status in ("UNDETERMINED", "CANCELED"):
                raise RuntimeError(
                    f"{label} ended {status}: "
                    f"{json.dumps(tx)[:1200]}")
        raise RuntimeError(f"{label} not finalized within {timeout_s}s")

    def call(self, method, args):
        calldata = gl_enc({"method": method, "args": args})
        # Second element is the leader_only flag as ONE byte b"\x00" — this is
        # genlayer-js transactions.serialize([calldata, false]) exactly.
        # Using b"" here (the wizard flow's form) makes the GenVM runner's
        # calldata.decode fail on the gen_call path ("unparsed end
        # b'\\x04args'"), verified 21 Nov against this chain.
        return rlp.encode([calldata, b"\x00"])

    def read(self, contract, method, args):
        data = "0x" + self.call(method, args).hex()
        res = rpc("gen_call", [{
            "type": "read", "to": contract, "from": self.addr,
            "data": data, "transaction_hash_variant": "latest-nonfinal"}])
        if isinstance(res, dict):
            if res.get("status", {}).get("code", 0) != 0:
                raise RuntimeError(f"gen_call failed: {res.get('status')}")
            hexdata = res["data"]
        else:
            hexdata = res
        buf = bytes.fromhex(hexdata)
        value, _ = gl_dec_str(buf)
        return value


CASES = [
    {
        "case_id": "case-001-btc-2026-11-19",
        "instrument": "BTC-USDT",
        "date": "2026-11-19",
        "threshold": "59000",
        "claim": ("Agent A sold Agent B a BTC price-protection note: it pays "
                  "out if BTC-USDT closed at or above 59,000 USDT on OKX on "
                  "2026-11-19. Agent A claims the note paid out; Agent B "
                  "disputes it."),
    },
    {
        "case_id": "case-002-btc-2026-11-18",
        "instrument": "BTC-USDT",
        "date": "2026-11-18",
        "threshold": "65000",
        "claim": ("Two trading agents escrowed a deal that settles only if "
                  "BTC-USDT closed at or above 65,000 USDT on OKX on "
                  "2026-11-18. The buyer claims the condition was met; the "
                  "seller disputes it."),
    },
]


def main():
    keyfile = sys.argv[1]
    acct = Account.from_key(open(keyfile).read().strip())
    court = Court(acct)
    bal = int(rpc("eth_getBalance", [court.addr, "latest"]), 16)
    print(f"sender {court.addr} balance {bal / 10**18} GEN", flush=True)

    deployment_path = os.path.join(HERE, "deployment.json")
    if os.path.exists(deployment_path):
        dep = json.load(open(deployment_path))
        contract = dep["contractAddress"]
        print(f"reusing contract {contract}", flush=True)
    else:
        code = open(CONTRACT_PATH, "rb").read()
        tx_data = rlp.encode([code, gl_enc({}), b""])
        dep_hash = court.send(ZERO, tx_data, "deploy")
        tx = court.wait_finalized(dep_hash, "deploy")
        with open(os.path.join(EVIDENCE, "deploy_tx.json"), "w") as f:
            json.dump(tx, f, indent=1, default=str)
        if tx.get("txExecutionResultName") == "FINISHED_WITH_ERROR":
            import base64
            lr = (tx.get("consensus_data") or {}).get("leader_receipt") or []
            detail = ""
            if lr and lr[0].get("result"):
                try:
                    detail = base64.b64decode(lr[0]["result"]).decode(
                        "utf-8", "replace")
                except Exception:
                    detail = lr[0]["result"]
            raise RuntimeError(f"deploy execution failed: {detail!r} "
                               f"(tx {dep_hash})")
        contract = None
        for key in ("contract_address", "to_address", "recipient"):
            v = tx.get(key)
            if isinstance(v, str) and v.lower() != ZERO and v.startswith("0x"):
                contract = v
                break
        if not contract:
            blob = json.dumps(tx)
            import re
            m = re.search(r'"contract_address"\s*:\s*"(0x[0-9a-fA-F]{40})"', blob)
            if m:
                contract = m.group(1)
        if not contract:
            raise RuntimeError("contract address not found in deploy tx; "
                               "see evidence/deploy_tx.json")
        dep = {
            "contractAddress": contract,
            "deployTx": dep_hash,
            "chainId": CHAIN_ID,
            "rpc": RPC,
            "explorer": f"https://explorer-studio-dev.genlayer.com/address/{contract}",
            "deployedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(deployment_path, "w") as f:
            json.dump(dep, f, indent=2)
        print(f"deployed: {contract}", flush=True)

    results = []
    for c in CASES:
        existing = court.read(contract, "get_case", [c["case_id"]])
        parsed = json.loads(existing)
        if parsed.get("status") == "RESOLVED":
            print(f"{c['case_id']}: already resolved, skipping", flush=True)
            results.append({**c, "final": parsed})
            continue
        if parsed.get("status") == "OPEN":
            print(f"{c['case_id']}: already filed, resolving", flush=True)
            file_tx = None
        else:
            file_tx = court.send(contract, court.call("file_case", [
                c["case_id"], c["instrument"], c["date"], c["threshold"],
                c["claim"]]), f"file {c['case_id']}")
            ftx = court.wait_finalized(file_tx, "file_case")
            if ftx.get("txExecutionResultName") == "FINISHED_WITH_ERROR":
                raise RuntimeError(f"file_case failed for {c['case_id']}")
        resolve_tx = court.send(contract, court.call("resolve_case",
                                                   [c["case_id"]]),
                                f"resolve {c['case_id']}")
        rtx = court.wait_finalized(resolve_tx, "resolve_case")
        if rtx.get("txExecutionResultName") == "FINISHED_WITH_ERROR":
            raise RuntimeError(f"resolve_case failed for {c['case_id']}")
        final = json.loads(court.read(contract, "get_case", [c["case_id"]]))
        if final.get("status") != "RESOLVED":
            raise RuntimeError(f"{c['case_id']} not RESOLVED after resolve: "
                               f"{final}")
        print(f"{c['case_id']}: verdict={final.get('verdict')} "
              f"close={final.get('close')} ruling={final.get('ruling')!r}",
              flush=True)
        results.append({**c, "fileTx": file_tx, "resolveTx": resolve_tx,
                        "final": final})

    out = {
        "demo": "OKX Price Court — Internet Court Partner Demo Lab",
        "partner": "OKX (Internet Court founding member)",
        "contract": dep,
        "cases": results,
        "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(EVIDENCE, "demo_result.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("SUMMARY " + json.dumps(out)[:600], flush=True)


if __name__ == "__main__":
    main()
