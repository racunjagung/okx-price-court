# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
OKX Price Court — an Internet Court demo on GenLayer.

Use case: two agents strike a deal whose outcome depends on a market fact
("BTC-USDT closed at or above 59,000 USDT on OKX on 2026-11-19"). When the
parties disagree, this Intelligent Contract acts as the adjudication layer of
the Internet Court stack: every validator independently fetches the disputed
candle from OKX's official public API (OKX is a founding member of the
Internet Court consortium) and an LLM jury turns the evidence into a ruling.
Consensus — not a single oracle — decides the verdict, and the verdict is
stored on-chain.

Partner: OKX (founding member, Internet Court consortium, internetcourt.org)
Data:    OKX public REST API v5, market/history-candles (no key required).
         The bar is 1Dutc (UTC-midnight-aligned daily candles) — OKX's plain
         1D bar is aligned to 16:00 UTC and would not match a UTC date.
"""

from genlayer import *
import json


def _days_from_civil(y: int, m: int, d: int) -> int:
    """Days since 1970-01-01 for a Gregorian date (Howard Hinnant's algorithm)."""
    y_adj = y - (1 if m <= 2 else 0)
    era = (y_adj if y_adj >= 0 else y_adj - 399) // 400
    yoe = y_adj - era * 400
    mp = (m + 9) % 12
    doy = (153 * mp + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _day_ts_ms(date_str: str) -> int:
    """'YYYY-MM-DD' -> milliseconds since epoch at 00:00:00 UTC that day."""
    parts = date_str.split("-")
    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    return _days_from_civil(y, m, d) * 86400000


class OkxPriceCourt(gl.Contract):
    court_name: str
    cases: TreeMap[str, str]

    def __init__(self) -> None:
        self.court_name = "OKX Price Court (Internet Court Demo Lab)"

    # ------------------------------------------------------------------ views
    @gl.public.view
    def get_case(self, case_id: str) -> str:
        if case_id not in self.cases:
            return '{"error": "case not found"}'
        return self.cases[case_id]

    @gl.public.view
    def get_court_name(self) -> str:
        return self.court_name

    # ----------------------------------------------------------------- writes
    @gl.public.write
    def file_case(
        self,
        case_id: str,
        instrument: str,
        date: str,
        threshold: str,
        claim: str,
    ) -> None:
        """Open a dispute: 'the daily close of `instrument` on OKX on `date`
        was at or above `threshold` USDT'. `claim` is the natural-language
        statement of the deal term being disputed."""
        if case_id in self.cases:
            raise Exception("case already exists")
        case = {
            "case_id": case_id,
            "instrument": instrument,
            "date": date,
            "threshold": threshold,
            "claim": claim,
            "filed_by": str(gl.message.sender_address),
            "status": "OPEN",
            "close": "",
            "verdict": None,
            "ruling": "",
            "evidence_url": "",
        }
        self.cases[case_id] = json.dumps(case)

    @gl.public.write
    def resolve_case(self, case_id: str) -> None:
        """Adjudicate an open case. Each validator independently renders the
        OKX history-candles API for the disputed day, extracts the confirmed
        daily close, and an LLM jury phrases the ruling. The Equivalence
        Principle requires every validator to agree on the exact close price
        and the verdict; only the ruling's wording may vary in style."""
        if case_id not in self.cases:
            raise Exception("case not found")
        case = json.loads(self.cases[case_id])
        if case["status"] != "OPEN":
            raise Exception("case is not open")

        day_ts = _day_ts_ms(case["date"])
        after_ts = day_ts + 2 * 86400000
        url = (
            "https://www.okx.com/api/v5/market/history-candles"
            f"?instId={case['instrument']}&bar=1Dutc&after={after_ts}&limit=5"
        )
        case["evidence_url"] = url
        threshold = case["threshold"]
        claim_text = case["claim"]
        instrument = case["instrument"]
        date_text = case["date"]

        def adjudicate() -> str:
            raw = gl.nondet.web.render(url, mode="text")
            payload = json.loads(raw)
            rows = payload.get("data", [])
            chosen = None
            for row in rows:
                # row: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
                if int(row[0]) == day_ts and row[8] == "1":
                    chosen = row
                    break
            if chosen is None:
                raise Exception("no confirmed OKX candle for the disputed date")
            open_px, high_px, low_px, close_px = chosen[1], chosen[2], chosen[3], chosen[4]
            verdict = float(close_px) >= float(threshold)
            ruling = gl.nondet.exec_prompt(
                "You are a judge of the Internet Court, a dispute-resolution "
                "protocol for agent-to-agent deals built on GenLayer. A deal "
                f"between two agents hinged on this term: \"{claim_text}\". "
                f"Official evidence from the OKX exchange API for {instrument} "
                f"on {date_text} (UTC daily candle): open {open_px}, high "
                f"{high_px}, low {low_px}, close {close_px} USDT. The disputed "
                f"threshold is {threshold} USDT, so the claim is "
                f"{'TRUE' if verdict else 'FALSE'}. Write a ruling in exactly "
                "one short sentence (max 30 words) that states the verdict and "
                "cites the closing price as evidence. No preamble."
            )
            return json.dumps(
                {"close": close_px, "verdict": verdict, "ruling": ruling.strip()}
            )

        result = gl.eq_principle.prompt_comparative(
            adjudicate,
            "The 'close' field must be exactly the same value and the "
            "'verdict' field must be the same boolean in both outputs. The "
            "'ruling' sentences must state the same outcome and cite the same "
            "closing price; only wording and style may differ.",
        )
        outcome = json.loads(result)
        case["close"] = outcome["close"]
        case["verdict"] = outcome["verdict"]
        case["ruling"] = outcome["ruling"]
        case["status"] = "RESOLVED"
        self.cases[case_id] = json.dumps(case)
