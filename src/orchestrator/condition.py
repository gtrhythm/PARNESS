import re
from typing import Any, Dict


class ConditionEvaluator:
    SAFE_BUILTINS = {
        "true": True,
        "false": False,
        "null": None,
        "True": True,
        "False": False,
        "None": None,
    }

    _DOT_ACCESS_RE = re.compile(r'\bconfig\.([a-zA-Z_][a-zA-Z0-9_]*)\b')

    def _rewrite_config_access(self, expr: str) -> str:
        return self._DOT_ACCESS_RE.sub(lambda m: f'config["{m.group(1)}"]', expr)

    def evaluate(self, expr: str, context: Dict[str, Any]) -> bool:
        if not expr:
            return True
        try:
            rewritten = self._rewrite_config_access(expr)
            safe_globals = {"__builtins__": {}}
            safe_locals = {**self.SAFE_BUILTINS, "config": context}
            result = eval(rewritten, safe_globals, safe_locals)
            return bool(result)
        except Exception:
            return False
