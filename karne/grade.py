"""Deterministik puanlama: model çıktısını harfe/sayıya çevir, ret ve biçim hatasını ayır."""
from __future__ import annotations

import re

REFUSAL = re.compile(
    r"bilmiyorum|emin değilim|bilgim yok|bilemiyorum|cevap veremem|yanıt veremem|"
    r"I don't know|I do not know|I'm not sure|cannot answer|can't answer|unable to",
    re.IGNORECASE,
)
THINK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL)


def strip(text: str) -> str:
    text = THINK.sub("", text or "")
    return text.strip().strip("*").strip()


def parse_letter(text: str, choices: list[str], letters: str = "ABCD") -> str | None:
    """Çıktıdan tek bir seçenek harfi çıkar. Belirsizse None."""
    t = strip(text)
    if not t:
        return None
    valid = letters[: len(choices)]
    # 1) Başta tek harf: "B", "B)", "B.", "(B)", "**B**"
    m = re.match(rf"^[\(\[]?\s*([{valid}])\s*(?:[\)\]\.\:,\-]|$|\s)", t)
    if m:
        return m.group(1)
    # 2) "Cevap: B" / "Doğru cevap B şıkkı"
    m = re.search(rf"(?:cevap|yanıt|answer|seçenek|şık)\w*\s*[:\-]?\s*\**[\(\[]?([{valid}])\b", t, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 3) Seçenek metnini aynen yazmışsa (tek bir seçenekle eşleşmeli)
    low = t.lower().rstrip(".")
    hits = [letters[i] for i, c in enumerate(choices) if low == c.lower()]
    if len(hits) == 1:
        return hits[0]
    hits = [letters[i] for i, c in enumerate(choices)
            if re.search(rf"(?<!\w){re.escape(c.lower())}(?!\w)", low)]
    if len(hits) == 1 and len(low) <= 60:
        return hits[0]
    return None


def parse_number(text: str) -> str | None:
    t = strip(text)
    m = re.search(r"(?<!\d)(\d{1,3})(?!\d)", t)
    return str(int(m.group(1))) if m else None


def grade(variant: dict, kind: str, output: str) -> dict:
    """{'pred':..., 'status': 'correct'|'wrong'|'refusal'|'format'}"""
    if kind == "exact":
        pred = parse_number(output)
        gold = str(int(variant["answer"]))
    else:
        pred = parse_letter(output, variant["choices"])
        gold = variant["answer"]
    if pred is None:
        status = "refusal" if REFUSAL.search(strip(output)) else "format"
    else:
        status = "correct" if pred == gold else "wrong"
    return {"pred": pred, "status": status}
