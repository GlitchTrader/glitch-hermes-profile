"""Fail until live market snapshot has rehydrated session extremes.

Run after NinjaTrader recompile of GlitchAiMarketIngest + AnalyticsBridge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LATEST = (
    Path.home()
    / "Documents"
    / "NinjaTrader 8"
    / "GlitchData"
    / "snapshots"
    / "market"
    / "latest.json"
)


def main() -> int:
    snap = json.loads(LATEST.read_text(encoding="utf-8"))
    print("created_utc", snap.get("created_utc"))
    ok = True
    for inst in snap.get("instruments") or []:
        root = str(inst.get("instrument") or "")[:3]
        sess = inst.get("session") if isinstance(inst.get("session"), dict) else {}
        high = sess.get("high")
        low = sess.get("low")
        prev_h = sess.get("previous_high")
        prev_l = sess.get("previous_low")
        status = sess.get("extremes_status")
        px = inst.get("current_price")
        print(
            f"{root} px={px} high={high} low={low} "
            f"prev_h={prev_h} prev_l={prev_l} extremes_status={status}"
        )
        if status != "complete":
            print(f"  FAIL {root}: extremes_status expected complete")
            ok = False
        if prev_h is None or prev_l is None:
            print(f"  FAIL {root}: previous session extremes missing")
            ok = False
        if high is None or low is None or px is None:
            print(f"  FAIL {root}: current session incomplete")
            ok = False
            continue
        # Session high must not sit absurdly near price right after a mid-session reload
        # unless the auction truly never extended; flag MES-style collapse.
        if abs(float(high) - float(px)) < 5 and root == "MES":
            print(
                f"  WARN {root}: session high within 5pts of price "
                f"(was the bug symptom when high collapsed to ~7675)"
            )
    if not ok:
        print("RESULT: FAIL — recompile Indicator (ingest+bridge) and ensure ingest chart has day history")
        return 1
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
