"""Token counting + budget-aware batching for LLM intra-paper passes.

We use tiktoken (cl100k_base) as a tokenizer proxy. The actual deployed
provider (MiniMax, GLM, …) does not publish a public tokenizer, so cl100k is
not exact — but it is far closer to reality than chars/N for both English
and Chinese, and the design's safety budget (one third of the model context
window) absorbs the residual mismatch.

See docs/knowledge_graph_design/ingestion_and_edge_discovery_design.md
on the LLM batching mechanism.
"""

from __future__ import annotations

from typing import Callable, List, Sequence


_DEFAULT_MAX_CONTEXT = 200_000
_DEFAULT_BUDGET_RATIO = 1 / 3
_DEFAULT_PROMPT_OVERHEAD = 2_000


def _get_encoder():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")


_ENCODER = None


def count_tokens(text: str) -> int:
    """Return tiktoken cl100k_base token count for ``text``. Empty → 0."""
    if not text:
        return 0
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = _get_encoder()
    return len(_ENCODER.encode(text, disallowed_special=()))


def llm_call_budget(
    max_context_tokens: int = _DEFAULT_MAX_CONTEXT,
    ratio: float = _DEFAULT_BUDGET_RATIO,
) -> int:
    """Per-LLM-call token budget. Defaults to one third of the model context.

    Caller should subtract its own prompt-template overhead before packing.
    """
    return max(1, int(max_context_tokens * ratio))


def pack_items_to_budget(
    items: Sequence[object],
    item_tokens: Callable[[object], int],
    *,
    budget_tokens: int,
    prompt_overhead: int = _DEFAULT_PROMPT_OVERHEAD,
    overlap: int = 0,
) -> List[List[object]]:
    """Greedy sliding-window packer.

    Splits ``items`` into batches each fitting under
    ``budget_tokens - prompt_overhead`` total token mass. The last
    ``overlap`` items of each batch are carried into the start of the next
    batch (so adjacent batches share boundary context). ``overlap=0`` =
    disjoint partitioning.

    Each item that on its own exceeds the per-batch capacity goes into its
    own singleton batch — we don't drop it, but the caller should treat
    that as a signal to chunk that single item further.
    """
    if budget_tokens <= prompt_overhead:
        raise ValueError(
            f"budget_tokens={budget_tokens} must exceed prompt_overhead={prompt_overhead}"
        )
    capacity = budget_tokens - prompt_overhead
    if overlap < 0:
        raise ValueError(f"overlap must be >= 0 (got {overlap})")

    batches: List[List[object]] = []
    current: List[object] = []
    current_tokens = 0

    for item in items:
        item_t = max(0, int(item_tokens(item)))
        if current and current_tokens + item_t > capacity:
            batches.append(current)
            if overlap > 0 and len(current) >= overlap:
                tail = current[-overlap:]
                current = list(tail)
                current_tokens = sum(max(0, int(item_tokens(t))) for t in current)
            else:
                current = []
                current_tokens = 0
        current.append(item)
        current_tokens += item_t

    if current:
        batches.append(current)
    return batches
