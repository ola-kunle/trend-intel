"""Optional LLM enrichment.

Design rule: **the LLM never produces a measurement.** It may not create a
number, a trend label, a confidence value, a source attribution or a claim
about what the evidence shows. It is used for two things only:

  1. A short "why this might matter" narrative for the practitioner.
  2. Rephrasing a content angle so it reads naturally.

Both are returned as strings that sit alongside - never inside - the
statistical fields. If no key is configured, the system runs identically and
these fields are simply absent. Nothing in the pipeline blocks on this step.
"""

import json
import os

from . import config

SYSTEM = (
    "You are a careful research assistant supporting a wellness-content "
    "practitioner. You are given observed trend data and must write a short, "
    "grounded note. Rules you must follow:\n"
    "- Never state or imply a medical claim, a cure, or a guaranteed therapeutic outcome.\n"
    "- Never invent statistics, sources, dates or citations. Use only what is given.\n"
    "- Never describe something as 'proven to work' unless the evidence tier says 'established'.\n"
    "- Keep it under 60 words. Plain prose. No bullet points.\n"
    "- If the evidence is thin, say so."
)


def _provider():
    for name in config.LLM_PROVIDER_ORDER:
        spec = config.LLM_PROVIDERS[name]
        key = os.environ.get(spec["env"])
        if key and spec["base"] and spec["model"]:
            return name, spec, key
    return None, None, None


def available():
    name, _, _ = _provider()
    return name


def _call_groq(spec, key, prompt):
    body = json.dumps({
        "model": spec["model"],
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 220,
    }).encode("utf-8")
    from .http import fetch_json
    url = spec["base"] + "/chat/completions"
    data = fetch_json(url, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + key})
    return data["choices"][0]["message"]["content"].strip()


def _call_gemini(spec, key, prompt):
    from .http import fetch_json
    url = ("%s/%s:generateContent?key=%s" % (spec["base"], spec["model"], key))
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 220},
    }).encode("utf-8")
    data = fetch_json(url, data=body, headers={"Content-Type": "application/json"})
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_openai_compatible(spec, key, prompt):
    from .http import fetch_json
    body = json.dumps({
        "model": spec["model"],
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.2, "max_tokens": 220,
    }).encode("utf-8")
    data = fetch_json(spec["base"] + "/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + key})
    return data["choices"][0]["message"]["content"].strip()


def enrich(concept_row, question_texts):
    """Return a narrative note for one concept, or None."""
    name, spec, key = _provider()
    if not name:
        return None
    prompt = (
        "Concept: %s\n"
        "Category: %s\n"
        "Evidence tier: %s\n"
        "Observed sources: %s\n"
        "Distinct surfaces: %d\n"
        "Observations in window: %d\n"
        "Recent audience questions: %s\n\n"
        "Write one short paragraph for a wellness practitioner explaining what "
        "this topic is, why it might be worth attention now, and how confident "
        "they should be. Do not make clinical claims."
        % (
            concept_row["name"],
            concept_row.get("category") or "unknown",
            concept_row.get("evidence_tier") or "unclassified",
            ", ".join(concept_row.get("sources", [])[:6]),
            concept_row.get("cross_source_count", 0),
            concept_row.get("observations", 0),
            ("; ".join(q[:90] for q in question_texts[:4]) or "none captured"),
        )
    )
    try:
        if name == "groq":
            return _call_groq(spec, key, prompt)
        if name == "gemini":
            return _call_gemini(spec, key, prompt)
        return _call_openai_compatible(spec, key, prompt)
    except Exception:
        return None


def enrich_batch(rows, questions_by_concept):
    """Enrich a limited number of rows. Failures are silent but logged."""
    provider = available()
    out = {}
    if not provider:
        return out
    for row in rows[:config.LLM_MAX_ITEMS]:
        note = enrich(row, questions_by_concept.get(row["key"], []))
        if note:
            out[row["key"]] = note
    return out
