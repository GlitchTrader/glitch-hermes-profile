"""Censoring-free scorer for authored geometries (read-only).

Why: score_nothing_waits.py / score_superseded_enters.py use the 5 one-minute
bars stored in decision-episodes.forward_observations. With a 5-minute window
roughly half of all geometries end "neither_reached", and the resolved subset is
biased toward the nearer barrier (the stop when reward/risk > 1). That makes
target-first rates incomparable across reward/risk and says nothing about edge.

What this does instead:
  * rebuilds a 1-minute OHLC series per root from saved decision-packets
    (cached under research/_cache/bars1m.json; delete to rebuild);
  * replays each authored geometry (NOTHING and ENTER decisions with a
    SELECTION_EV bracket) from the first full bar AFTER decision_utc (no
    look-ahead, no pre-entry touches), with fill-relative levels
    (entry = open of that bar; stop/target keep their authored offsets);
  * evaluates horizons H in {5,15,30,60} minutes; an unresolved bracket is
    marked to market at the horizon close (net of friction), never dropped;
  * same-bar double touch is reported as bounds (stop-first = pessimistic,
    target-first = optimistic);
  * builds a placebo for each geometry: the same direction, risk and reward
    replayed at random start times of the same root within +-90 minutes of the
    same time of day. edge = actual net R - placebo net R, so market drift,
    volatility and censoring cancel;
  * confidence intervals use a bootstrap over opportunity_group_id clusters.

It does not model slippage beyond the one-bar entry lag, and it ignores
management exits (HOLD/EXIT/MOVE_*): it scores the bracket, not the trade.
"""
from __future__ import annotations

import importlib.util
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

PROFILE = Path(r"C:\Users\arifr\Projects\glitch-hermes-profile")
GD = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"
SUP = GD / "hermes" / "exchange" / "hermes" / "supervisor"
PACKETS = GD / "hermes" / "exchange" / "glitch" / "decision-packets"
CACHE = PROFILE / "research" / "_cache" / "bars1m.json"
OUT_JSON = PROFILE / "research" / "report-rr-unbiased.json"
OUT_MD = PROFILE / "research" / "report-rr-unbiased.md"

HORIZONS = (5, 15, 30, 60)
PLACEBO_PER_DECISION = 150
BOOT = 1000
SEED = 7
TOD_WINDOW_MIN = 90
FALLBACK_FRICTION = {"MES": 0.25, "MNQ": 0.5, "M2K": 0.2}
POINT_VALUE = {"MES": 5.0, "MNQ": 2.0, "M2K": 5.0}
RR_BUCKETS = ((0.0, 1.0), (1.0, 1.5), (1.5, 2.5), (2.5, 99.0))

sys.path.insert(0, str(PROFILE / "scripts"))
_spec = importlib.util.spec_from_file_location("evalcog", PROFILE / "scripts" / "evaluate-frozen-cognition.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "")[:26]).replace(tzinfo=timezone.utc)


def minute_index(dt: datetime) -> int:
    return int(dt.timestamp() // 60)


def load_bars() -> dict[str, dict[int, tuple[float, float, float, float]]]:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        raw: dict[str, dict[str, list[float]]] = defaultdict(dict)
        for path in sorted(PACKETS.glob("*.json")):
            try:
                packet = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for frame in packet.get("frames", []):
                for ins in frame.get("market_snapshot", {}).get("instruments", []):
                    root = str(ins.get("instrument"))[:3]
                    for tb in ins.get("timeframe_bars", []):
                        if tb.get("minutes") != 1:
                            continue
                        lc = ((tb.get("descriptive_state") or {}).get("native_observations") or {}).get("last_completed_bar")
                        if lc and lc.get("completeness") == "complete":
                            raw[root][lc["utc_time"]] = [lc["open"], lc["high"], lc["low"], lc["close"]]
        CACHE.write_text(json.dumps(raw), encoding="utf-8")
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    return {
        root: {minute_index(parse_utc(k)): tuple(v) for k, v in series.items()}
        for root, series in raw.items()
    }


class Series:
    """Dense minute arrays with a presence mask for one root."""

    def __init__(self, bars: dict[int, tuple[float, float, float, float]]):
        self.t0 = min(bars)
        n = max(bars) - self.t0 + 1
        self.o = np.full(n, np.nan)
        self.h = np.full(n, np.nan)
        self.l = np.full(n, np.nan)
        self.c = np.full(n, np.nan)
        for minute, (o, h, l, c) in bars.items():
            i = minute - self.t0
            self.o[i], self.h[i], self.l[i], self.c[i] = o, h, l, c
        self.present = ~np.isnan(self.c)
        self.n = n
        self._valid: dict[int, np.ndarray] = {}

    def valid_starts(self, horizon: int) -> np.ndarray:
        if horizon not in self._valid:
            csum = np.concatenate([[0], np.cumsum(self.present.astype(int))])
            starts = np.arange(0, self.n - horizon + 1)
            ok = (csum[starts + horizon] - csum[starts]) == horizon
            self._valid[horizon] = starts[ok]
        return self._valid[horizon]

    def replay(self, starts: np.ndarray, horizon: int, direction: int, d_stop: float, d_target: float, friction: float):
        """Return (code_pess, r_pess, r_opt) arrays. code: 1 target, -1 stop, 0 neither, 2 ambiguous(pess=stop)."""
        idx = starts[:, None] + np.arange(horizon)[None, :]
        entry = self.o[starts]
        high, low = self.h[idx], self.l[idx]
        if direction > 0:
            stop_px = entry + d_stop
            tgt_px = entry + d_target
            t_hit = high >= tgt_px[:, None]
            s_hit = low <= stop_px[:, None]
        else:
            stop_px = entry + d_stop
            tgt_px = entry + d_target
            t_hit = low <= tgt_px[:, None]
            s_hit = high >= stop_px[:, None]
        either = t_hit | s_hit
        first = np.where(either.any(axis=1), either.argmax(axis=1), -1)
        rows = np.arange(len(starts))
        fi = np.where(first >= 0, first, 0)
        t_first = t_hit[rows, fi] & (first >= 0)
        s_first = s_hit[rows, fi] & (first >= 0)
        risk = abs(d_stop)
        reward = abs(d_target)
        close_end = self.c[starts + horizon - 1]
        mtm = direction * (close_end - entry)
        gross_pess = np.where(first < 0, mtm, np.where(s_first, -risk, reward))
        gross_opt = np.where(first < 0, mtm, np.where(t_first, reward, -risk))
        code = np.where(first < 0, 0, np.where(t_first & s_first, 2, np.where(t_first, 1, -1)))
        return code, (gross_pess - friction) / risk, (gross_opt - friction) / risk


def parse_fields(text: str) -> dict[str, str]:
    match = re.search(r"(?mi)^SELECTION_EV\s*=\s*(.+?)\s*$", text)
    out: dict[str, str] = {}
    if match:
        for part in match.group(1).split(";"):
            key, sep, value = part.partition("=")
            if sep:
                out[key.strip().lower()] = value.strip()
    return out


def declared_p(row: dict, fields: dict[str, str]) -> float | None:
    rng = ev.probability_range(ev.selection_audit(row))
    if rng:
        return statistics.fmean(rng)
    vals = [ev.number(x) for x in (fields.get("estimated_target_first_range") or "").replace("%", "").split("-")]
    vals = [v for v in vals if v is not None]
    return statistics.fmean(vals) if vals else None


def collect(series: dict[str, Series]):
    decisions = []
    for line in (SUP / "decision-episodes.jsonl").open(encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        action = str(row.get("action") or "")
        kind = "NOTHING" if action == "NOTHING" else "ENTER" if action.startswith("ENTER") else None
        if not kind:
            continue
        audit = row.get("decision_audit") if isinstance(row.get("decision_audit"), dict) else {}
        fields = parse_fields(str(audit.get("decisive_evidence") or ""))
        geo = ev.geometry_from_decisive_evidence(row)
        direction = {"LONG": 1, "SHORT": -1}.get(str(geo.get("direction") or "").upper())
        entry, stop, target = (ev.number(geo.get(k)) for k in ("entry", "stop", "target"))
        if not direction or None in (entry, stop, target):
            continue
        risk, reward = abs(entry - stop), abs(target - entry)
        # geometry must be coherent with direction
        if risk <= 0 or reward <= 0 or (direction > 0 and not (stop < entry < target)) or (direction < 0 and not (target < entry < stop)):
            continue
        root = ev.instrument_root(row.get("instrument"))
        if root not in series:
            continue
        decided = parse_utc(row["decision_utc"])
        start = minute_index(decided.replace(second=0, microsecond=0)) + 1
        friction = ev.number(fields.get("friction_points")) or FALLBACK_FRICTION.get(root, 0.25)
        decisions.append({
            "kind": kind, "root": root, "dir": direction, "risk": risk, "reward": reward, "rr": reward / risk,
            "friction": friction, "start": start, "tod": decided.hour * 60 + decided.minute,
            "group": str(row.get("opportunity_group_id") or row.get("episode_id")),
            "p": declared_p(row, fields), "version": str(row.get("prompt_version") or "")[:40],
            "pv": POINT_VALUE.get(root, 5.0),
        })
    return decisions


def run_horizon(decisions, series, horizon, rng):
    results = []
    for d in decisions:
        s = series[d["root"]]
        i = d["start"] - s.t0
        if i < 0 or i + horizon > s.n or not s.present[i:i + horizon].all():
            continue
        d_stop = -d["risk"] if d["dir"] > 0 else d["risk"]
        d_target = d["reward"] if d["dir"] > 0 else -d["reward"]
        code, rp, ro = s.replay(np.array([i]), horizon, d["dir"], d_stop, d_target, d["friction"])
        pool = s.valid_starts(horizon)
        tod = ((pool + s.t0) % 1440)  # minute-of-day (UTC)
        diff = np.abs(tod - d["tod"])
        diff = np.minimum(diff, 1440 - diff)
        cand = pool[diff <= TOD_WINDOW_MIN]
        cand = cand[np.abs(cand - i) > horizon]  # exclude overlap with the actual window
        if len(cand) < 30:
            continue
        pick = rng.choice(cand, size=min(PLACEBO_PER_DECISION, len(cand)), replace=False)
        pcode, prp, pro = s.replay(pick, horizon, d["dir"], d_stop, d_target, d["friction"])
        results.append({
            **d, "code": int(code[0]), "r_pess": float(rp[0]), "r_opt": float(ro[0]),
            "pl_t": float((pcode == 1).mean()), "pl_s": float(((pcode == -1) | (pcode == 2)).mean()),
            "pl_n": float((pcode == 0).mean()),
            "pl_r_pess": float(prp.mean()), "pl_r_opt": float(pro.mean()),
            "usd_pess": float(rp[0]) * d["risk"] * d["pv"], "pl_usd_pess": float(prp.mean()) * d["risk"] * d["pv"],
        })
    return results


def summarise(items, rng):
    if not items:
        return {"n": 0}
    groups = defaultdict(list)
    for r in items:
        groups[r["group"]].append(r)
    keys = list(groups)

    def stat(sample):
        n = len(sample)
        act_p = np.mean([r["r_pess"] for r in sample])
        act_o = np.mean([r["r_opt"] for r in sample])
        pl_p = np.mean([r["pl_r_pess"] for r in sample])
        pl_o = np.mean([r["pl_r_opt"] for r in sample])
        return n, act_p, act_o, pl_p, pl_o

    n, act_p, act_o, pl_p, pl_o = stat(items)
    edges, usd_edges = [], []
    for _ in range(BOOT):
        pick = rng.integers(0, len(keys), size=len(keys))
        sample = [r for k in pick for r in groups[keys[k]]]
        _, a, _, p, _ = stat(sample)
        edges.append(a - p)
        usd_edges.append(np.mean([r["usd_pess"] - r["pl_usd_pess"] for r in sample]))
    lo, hi = np.percentile(edges, [5, 95])
    ulo, uhi = np.percentile(usd_edges, [5, 95])
    usd_edge = float(np.mean([r["usd_pess"] - r["pl_usd_pess"] for r in items]))
    mean_risk_usd = float(np.mean([r["risk"] * r["pv"] for r in items]))
    codes = [r["code"] for r in items]
    ps = [r["p"] for r in items if r["p"] is not None]
    return {
        "n": n, "clusters": len(keys),
        "p_target": round(codes.count(1) / n, 3), "p_stop": round((codes.count(-1) + codes.count(2)) / n, 3),
        "p_neither": round(codes.count(0) / n, 3), "p_ambiguous": round(codes.count(2) / n, 3),
        "placebo_p_target": round(float(np.mean([r["pl_t"] for r in items])), 3),
        "placebo_p_stop": round(float(np.mean([r["pl_s"] for r in items])), 3),
        "placebo_p_neither": round(float(np.mean([r["pl_n"] for r in items])), 3),
        "mean_declared_p": round(float(np.mean(ps)), 3) if ps else None,
        "net_R_pess": round(float(act_p), 3), "net_R_opt": round(float(act_o), 3),
        "placebo_net_R_pess": round(float(pl_p), 3), "placebo_net_R_opt": round(float(pl_o), 3),
        "edge_R_pess": round(float(act_p - pl_p), 3), "edge_R_pess_ci90": [round(float(lo), 3), round(float(hi), 3)],
        "edge_R_opt": round(float(act_o - pl_o), 3),
        "edge_usd_pess": round(usd_edge, 2), "edge_usd_pess_ci90": [round(float(ulo), 2), round(float(uhi), 2)],
        "mean_risk_usd": round(mean_risk_usd, 2),
        "cond_hit_actual": round(codes.count(1) / max(1, codes.count(1) + codes.count(-1) + codes.count(2)), 3),
    }


def bucket_of(rr):
    for lo, hi in RR_BUCKETS:
        if lo <= rr < hi:
            return f"RR[{lo:g},{hi:g})"
    return "RR?"


def main() -> int:
    rng = np.random.default_rng(SEED)
    bars = load_bars()
    series = {root: Series(b) for root, b in bars.items() if b}
    decisions = collect(series)
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(), "decisions_with_geometry": len(decisions),
              "coverage": {root: len(b) for root, b in bars.items()}, "horizons": {}}
    for horizon in HORIZONS:
        res = run_horizon(decisions, series, horizon, rng)
        block = {"scored": len(res)}
        for kind in ("NOTHING", "ENTER"):
            sub = [r for r in res if r["kind"] == kind]
            block[kind] = {"all": summarise(sub, rng)}
            for lo, hi in RR_BUCKETS:
                part = [r for r in sub if lo <= r["rr"] < hi]
                if len(part) >= 8:
                    block[kind][bucket_of(lo)] = summarise(part, rng)
        report["horizons"][str(horizon)] = block
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = ["# Unbiased bracket scorer (no censoring)", "", f"Gerado: {report['generated_utc']}", "",
             f"- Decisoes com geometria coerente: {len(decisions)}",
             "- Entrada: abertura da 1a barra completa apos decision_utc; niveis fill-relativos; 'neither' = marcacao a mercado no fim do horizonte (liquido de friccao).",
             "- edge = R liquido real - R liquido placebo (mesma geometria em horarios aleatorios do mesmo root/hora do dia).",
             "- pess = barra com toque duplo conta como stop; opt = como target.", ""]
    for horizon, block in report["horizons"].items():
        lines += [f"## Horizonte {horizon} min (scored {block['scored']})", "",
                  "| grupo | n | clusters | P(T) | P(S) | P(neither) | placebo P(T)/P(S)/P(n) | R liq pess (opt) | placebo R pess | edge R pess [IC90] | edge US$/trade [IC90] | risco US$ | p declarado |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for kind in ("NOTHING", "ENTER"):
            for name, s in block[kind].items():
                if not s.get("n"):
                    continue
                lines.append(
                    f"| {kind} {name} | {s['n']} | {s['clusters']} | {s['p_target']} | {s['p_stop']} | {s['p_neither']} | "
                    f"{s['placebo_p_target']}/{s['placebo_p_stop']}/{s['placebo_p_neither']} | {s['net_R_pess']} ({s['net_R_opt']}) | "
                    f"{s['placebo_net_R_pess']} | {s['edge_R_pess']:+} {s['edge_R_pess_ci90']} | "
                    f"{s['edge_usd_pess']:+} {s['edge_usd_pess_ci90']} | {s['mean_risk_usd']} | {s['mean_declared_p']} |")
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
