import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_AVG_CHARS_PER_TOKEN = 3.5
DEFAULT_SAFETY_MARGIN = 0.15
DEFAULT_TEMPLATE_OVERHEAD = 500

TOKENS_PER_IDEA = 800
TOKENS_PER_INSIGHT_LINE = 40
TOKENS_PER_SEED_LINE = 60
MAX_IDEAS_PER_BATCH = 10

_REASONING_MODELS = {"MiniMax-M2.7", "o1", "o1-mini", "o3-mini"}
_REASONING_TOKEN_MULTIPLIER = 3.0

_MODEL_DEFAULTS = {
    "MiniMax-M2.7": 200000,
    "MiniMax-Text-01": 1000000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "claude-3-5-sonnet-20241022": 200000,
    "default": 128000,
}


@dataclass
class PromptBudget:
    max_context: int
    avg_chars_per_token: float = DEFAULT_AVG_CHARS_PER_TOKEN

    def __init__(self, max_context: int, model: str = "", avg_chars_per_token: float = DEFAULT_AVG_CHARS_PER_TOKEN):
        self.max_context = max_context
        self.model = model
        self.avg_chars_per_token = avg_chars_per_token
        self._is_reasoning = model in _REASONING_MODELS

    @classmethod
    def from_config(cls, config: dict) -> "PromptBudget":
        explicit = config.get("max_context_tokens")
        model = config.get("llm_model", config.get("model", ""))
        if explicit:
            return cls(max_context=int(explicit), model=model)
        max_ctx = _MODEL_DEFAULTS.get(model, _MODEL_DEFAULTS["default"])
        return cls(max_context=max_ctx, model=model)

    def estimate_tokens(self, text: str) -> int:
        return int(len(text) / self.avg_chars_per_token)

    def available_output_tokens(self, input_text: str) -> int:
        safety = int(self.max_context * DEFAULT_SAFETY_MARGIN)
        input_tokens = self.estimate_tokens(input_text) + DEFAULT_TEMPLATE_OVERHEAD
        available = self.max_context - input_tokens - safety
        return max(available, 256)

    def _tokens_per_idea(self) -> int:
        base = TOKENS_PER_IDEA
        if self._is_reasoning:
            base = int(base * _REASONING_TOKEN_MULTIPLIER)
        return base

    def max_ideas_per_request(self, input_text: str) -> int:
        available = self.available_output_tokens(input_text)
        raw = max(1, available // self._tokens_per_idea())
        return min(raw, MAX_IDEAS_PER_BATCH)

    def truncate_to_budget(
        self,
        items: List,
        formatter,
        max_input_tokens: int,
    ) -> str:
        budget_chars = int(max_input_tokens * self.avg_chars_per_token)
        result = ""
        for item in items:
            line = formatter(item)
            if len(result) + len(line) + 1 > budget_chars:
                break
            if result:
                result += "\n"
            result += line
        return result

    def plan_batches(
        self,
        seeds: List,
        insights: List,
        target_count: int,
        batch_size: int = 15,
    ) -> List[dict]:
        insight_tokens = min(len(insights), 40) * TOKENS_PER_INSIGHT_LINE
        per_batch_seed_tokens = min(batch_size, len(seeds)) * TOKENS_PER_SEED_LINE
        input_tokens = insight_tokens + per_batch_seed_tokens + DEFAULT_TEMPLATE_OVERHEAD
        safety = int(self.max_context * DEFAULT_SAFETY_MARGIN)

        available_output = self.max_context - input_tokens - safety
        ideas_per_batch = max(1, min(available_output // self._tokens_per_idea(), MAX_IDEAS_PER_BATCH))

        batches = []
        for i in range(0, max(len(seeds), 1), batch_size):
            batch_seeds = seeds[i:i + batch_size]
            batches.append({
                "seeds": batch_seeds,
                "seed_start": i,
                "ideas_per_batch": ideas_per_batch,
            })

        num_batches = len(batches)
        total_capacity = ideas_per_batch * num_batches
        if total_capacity < target_count:
            extra_batches_needed = -(-( target_count - total_capacity) // ideas_per_batch)
            for b_idx in range(extra_batches_needed):
                start = num_batches * batch_size + b_idx * batch_size
                remaining_seeds = seeds[start:start + batch_size] if start < len(seeds) else seeds[:batch_size]
                batches.append({
                    "seeds": remaining_seeds if remaining_seeds else seeds[:batch_size],
                    "seed_start": start,
                    "ideas_per_batch": ideas_per_batch,
                })

        logger.info(
            "PromptBudget: context=%d, model=%s, reasoning=%s, "
            "tokens_per_idea=%d, ideas_per_batch=%d, batches=%d, target=%d",
            self.max_context, self.model, self._is_reasoning,
            self._tokens_per_idea(), ideas_per_batch, len(batches), target_count,
        )
        return batches
