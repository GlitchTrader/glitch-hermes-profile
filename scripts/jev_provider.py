"""Pinned TypeSafe transport; typed judgments remain isolated research evidence."""
from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from pathlib import Path

from jev_observation import encoded, strict_json

MODEL = "jev-1.13.0"
PROVIDER = "typesafe-direct"
QUESTION_VERSION = "live-long-v1"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
INPUT_USD_PER_MILLION = .042  # Verified 2026-09-19; output tokens free for this pinned model.
RESERVED_USD_PER_CALL = .03  # Conservative accounting reserve, including failed/unknown calls.
QUESTIONS = {
    f"endpoint_{h}m": {
        "type": "choice",
        "instructions": f"Forecast the primary instrument's net price displacement at exactly {h} minutes AFTER the supplied observation. Use the explicit {h}m neutral band in reference; displacement and band share anchor 15m-ATR units. Judge the FUTURE endpoint using current evidence, not the sign of the past move. Missing order flow is not directional evidence. This is a market forecast, not an order.",
        "criteria": {"UP": "Future displacement exceeds the positive neutral band.",
                     "DOWN": "Future displacement is below the negative neutral band.",
                     "FLAT": "Future displacement lies inside or on the neutral band."},
    } for h in (5, 15, 30, 60)
}
QUESTIONS.update({
    "first_barrier_60m": {
        "type": "choice",
        "instructions": "During the NEXT 60 minutes, which of the symmetric upper/lower excursion barriers specified in reference is likely to be touched first? Start at the current primary price. Distinguish the first excursion from the eventual endpoint; a reversal may cross both.",
        "criteria": {"UPPER_FIRST": "The upper barrier is touched before the lower barrier.",
                     "LOWER_FIRST": "The lower barrier is touched before the upper barrier.",
                     "NEITHER": "Neither barrier is touched in the next 60 minutes."}},
    "path_state": {
        "type": "choice",
        "instructions": "Which state best describes the primary market path NOW, using recent displacement, efficiency, session location and multi-timeframe evidence? Respect each frame's partial or unknown completeness. This is a current-state description, not a future direction or action.",
        "criteria": {"UPWARD": "Coherent upward progress across the relevant context.",
                     "DOWNWARD": "Coherent downward progress across the relevant context.",
                     "PULLBACK": "A counter-move within a still coherent broader direction.",
                     "ROTATION": "Repeated opposing movement with little sustained net progress.",
                     "TRANSITION": "Directional evidence is changing or materially conflicts across horizons.",
                     "UNCLEAR": "No reliable coherent state can be established."}},
    "maturity": {
        "type": "choice",
        "instructions": "How developed is the current primary directional move, based on the supplied price path, location and multiple timeframes? Do not treat a high oscillator reading alone as reversal evidence.",
        "criteria": {"EARLY": "Directional movement is beginning.",
                     "DEVELOPING": "Directional progress is building and remains coherent.",
                     "MATURE": "Substantial displacement has already occurred but coherent progress persists.",
                     "EXHAUSTED": "Further same-direction price progress is failing or being rejected.",
                     "UNCLEAR": "There is no coherent directional move or evidence is insufficient."}},
})


def credentials(env_file=None):
    """Read only named research keys, without dotenv expansion or shell evaluation."""
    values = {key: os.environ.get(key, "") for key in ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY")}
    if env_file:
        path = Path(env_file)
        if not path.is_absolute() or path.stat().st_size > 16384:
            raise ValueError("credential_file_invalid")
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in values:
                values[key.strip()] = value.strip().strip('"\'')
    if not values["TYPESAFE_API_KEY"]:
        raise ValueError("missing_typesafe_key")
    return values


def scrub(raw, secrets):
    text = raw.decode("utf-8", errors="replace")
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
            text = text.replace(json.dumps(secret)[1:-1], "[REDACTED]")
    return text


def validate_response(value, questions=None):
    questions = QUESTIONS if questions is None else questions
    if not isinstance(value, dict) or value.get("model") != MODEL:
        raise ValueError("model_identity")
    answers = value.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("answer_set")
    normalized, notes = {}, []
    for key, question in questions.items():
        answer = answers[key]
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise ValueError("answer_type")
        cells = answer.get("probabilities")
        if not isinstance(cells, dict) or set(cells) != set(question["criteria"]):
            raise ValueError("probability_keys")
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in cells.values()):
            raise ValueError("probability_range")
        total = sum(cells.values())
        if total <= 0 or abs(total - 1) > .005 * len(cells) + 1e-9:
            raise ValueError("probability_sum")
        if abs(total - 1) > 1e-9:
            if any(abs(v * 100 - round(v * 100)) > 1e-8 for v in cells.values()):
                raise ValueError("unexplained_probability_sum")
            notes.append(key + ":rounded_probability_sum")
        if answer.get("choice") not in cells or max(cells.values()) - cells[answer["choice"]] > 1e-12:
            raise ValueError("named_choice_discrepancy")
        if cells[answer["choice"]] < max(cells.values()):
            notes.append(key + ":floating_point_argmax_tie")
        confidence = answer.get("confidence")
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("confidence_range")
        normalized[key] = {label: probability / total for label, probability in cells.items()}
    return normalized, notes


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(state, keys, questions=None):
    questions = QUESTIONS if questions is None else questions
    body = encoded({"model": MODEL, "state": state, "questions": questions})
    if len(body) > MAX_REQUEST_BYTES:
        return {"status": "request_size_limit"}
    req = urllib.request.Request(ENDPOINT, data=body, headers={
        "Authorization": "Bearer " + keys["TYPESAFE_API_KEY"], "Content-Type": "application/json"})
    try:
        # Never forward credentials on redirects. Process deadline also bounds DNS and reads.
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=2) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return {"status": "http_error", "http_status": exc.code}
    except (OSError, ValueError):
        return {"status": "transport_error"}  # Do not log exception URLs, headers or key values.
    if len(raw) > MAX_RESPONSE_BYTES:
        return {"status": "response_size_limit"}
    result = {"raw_response": scrub(raw, keys.values())}
    try:
        value = strict_json(result["raw_response"].encode(), MAX_RESPONSE_BYTES)
        result["returned_model"] = value.get("model") if isinstance(value, dict) else None
        normalized, notes = validate_response(value, questions)
        result.update(status="ok", probabilities_for_scoring=normalized, notes=notes, usage=value.get("usage"))
        tokens = (value.get("usage") or {}).get("input_tokens")
        if type(tokens) is int and tokens >= 0:
            result["estimated_cost_usd"] = tokens * INPUT_USD_PER_MILLION / 1_000_000
    except (ValueError, TypeError, AttributeError) as exc:
        result["status"] = "malformed_response"
        result["error_category"] = str(exc) if type(exc) is ValueError and len(str(exc)) < 48 else "json_shape"
    return result


def request_process(connection, state, keys, questions=None):
    """Only worker target; its parent can terminate it at the absolute deadline."""
    try:
        connection.send(request(state, keys, questions))
    except Exception:
        connection.send({"status": "provider_worker_error"})
    finally:
        connection.close()
