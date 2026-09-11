"""A local generative answerer, for measuring the price of fluency.

The extractive answerer scores 1.000 on both citation measures by construction:
it quotes retrieved sections, so it cannot cite what it did not retrieve or
attribute words that are not there. That is the bar. This module exists to
measure how far below it a model falls once it writes prose.

## Why a 0.5B model

Everything here runs locally on CPU with no paid API, which is a constraint the
project has held to since Phase 1 and which shapes the result. Qwen2.5-0.5B-
Instruct generates roughly two tokens a second on this machine, so a hundred
answers is about an hour - workable for a measurement, not for a product.

A larger model would cite better. The number this produces is therefore a lower
bound on what abstractive generation can do, not an estimate of it, and the
write-up says so. What transfers regardless of model size is the *method*:
citations parsed from free text and checked against the retrieved context, with
grounded and supported reported separately.

## Citation format

Passages are numbered and the model is asked to tag each sentence with the
numbers it used. Numbers rather than `DOC-ID::Section` strings on purpose: a
small model copies a short tag reliably and mangles a long one, and the mangling
would measure the model's transcription rather than its faithfulness. Mapping
the number back to an evidence id is this module's job, not the model's.

Anything the model emits that is not a valid passage number is dropped rather
than repaired. A citation the parser had to guess at is not evidence the model
cited correctly.
"""

from __future__ import annotations

import re

from regulens.generation.answer import Citation, GroundedAnswer
from regulens.retrieval.base import RetrievalResult

DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"

PROMPT = """You are answering a question about UAE insurance regulation using only the numbered passages below. Do not use any other knowledge.

{passages}

Question: {question}

Write a short answer of one to three sentences. End every sentence with the numbers of the passages it came from, in square brackets, like [1] or [2][3]. Use only the numbers above. If the passages do not answer the question, reply exactly: Not covered by these passages."""

# One citation tag, and a run of adjacent tags written as a single cluster.
# "[2][3]" is one act of citation, not two, so the two numbers share a claim.
TAG_RE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")
_TAG = r"\[\d+(?:\s*[,;]\s*\d+)*\]"
CLUSTER_RE = re.compile(rf"{_TAG}(?:\s*{_TAG})*")

REFUSAL = "not covered by these passages"


class AbstractiveGenerator:
    """Generates prose with citation tags, resolved back to evidence ids."""

    name = "abstractive"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        max_new_tokens: int = 110,
        passage_chars: int = 700,
        dtype: str = "float32",
    ) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._torch = torch
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        self.passage_chars = passage_chars
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        # float32 for the small model, where it costs 2 GB and removes a
        # variable. A 1.5B model in float32 needs 6 GB, which this machine does
        # not have free, so larger models run in bfloat16 - halving memory at
        # some cost in speed on a CPU without native bf16 matmul.
        self.dtype = dtype
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, dtype=getattr(torch, dtype)
        ).eval()

    def _prompt(self, question: str, context: list[RetrievalResult]) -> str:
        passages = "\n\n".join(
            f"[{i}] {r.chunk.text[:self.passage_chars].rstrip()}"
            for i, r in enumerate(context, start=1)
        )
        return PROMPT.format(passages=passages, question=question)

    def _run(self, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        inputs = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
        )
        with self._torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        start = inputs["input_ids"].shape[1]
        return self.tokenizer.decode(output[0][start:], skip_special_tokens=True).strip()

    def generate(self, question: str, context: list[RetrievalResult]) -> GroundedAnswer:
        return parse_answer(self._run(self._prompt(question, context)), context)


def split_claims(text: str) -> list[tuple[str, list[int]]]:
    """Pair each citation cluster with the words it is citing.

    A tag belongs to the text *before* it - the prompt asks the model to end
    each sentence with its numbers. When there is nothing before it, the model
    put the tag first and the claim is the text that follows.

    This is not sentence splitting, and an earlier version that was got it
    wrong in both directions: splitting on the full stop left "[1]" at the head
    of the next segment, so one claim's citation quoted the *following* claim's
    words, and the final citation quoted nothing at all. Both make a correct
    citation score as unsupported, which moves the measured number without any
    model behaving differently.
    """
    clusters = list(CLUSTER_RE.finditer(text))
    claims: list[tuple[str, list[int]]] = []
    for i, cluster in enumerate(clusters):
        start = clusters[i - 1].end() if i else 0
        claim = text[start : cluster.start()].strip()
        if not claim:
            nxt = clusters[i + 1].start() if i + 1 < len(clusters) else len(text)
            claim = text[cluster.end() : nxt].strip()

        numbers: list[int] = []
        for group in TAG_RE.findall(cluster.group(0)):
            for raw in re.split(r"[,;]", group):
                raw = raw.strip()
                if raw.isdigit() and int(raw) not in numbers:
                    numbers.append(int(raw))
        claims.append((claim, numbers))
    return claims


def parse_answer(text: str, context: list[RetrievalResult]) -> GroundedAnswer:
    """Turn tagged model output into an answer with resolved citations.

    Separate from the model so the resolution rules can be tested without
    generating anything - they are where a citation is accepted or lost, which
    is what the measurement in `results/abstractive.md` depends on.
    """
    if text.lower().startswith(REFUSAL):
        return GroundedAnswer(
            text=text, citations=[], abstained=True, context_used=context,
            reason="model declined: passages do not answer the question",
        )

    citations: list[Citation] = []
    seen: set[tuple[str, str]] = set()
    for claim, numbers in split_claims(text):
        # A tag with no prose anywhere near it is not a claim, and there is
        # nothing for validation to check against the section it names.
        if not claim:
            continue
        for number in numbers:
            index = number - 1
            # Out-of-range tags are dropped, not clamped. A number the model
            # invented is not a citation to anything.
            if not (0 <= index < len(context)):
                continue
            chunk = context[index].chunk
            key = (chunk.doc_id, chunk.section)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                Citation(
                    doc_id=chunk.doc_id,
                    section=chunk.section,
                    # The claim, not the source. validate_citations then asks
                    # whether the cited section actually contains the words the
                    # claim rests on.
                    quote=claim,
                    url=chunk.metadata.get("url", ""),
                )
            )

    return GroundedAnswer(text=text, citations=citations, context_used=context)
