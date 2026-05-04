from typing import Callable, Optional

from stealth_config.config_manager import get_config


class SOTAOptimizer:
    def __init__(self, cfg=None):
        self.cfg = cfg or get_config()
        self._sem_cache = None
        self._comp_instance = None
        self._limiter_instance = None
        self._batch_client = None

    def _semantic_cache(self):
        if self._sem_cache is None:
            import sys
            sys.path.insert(0, "/Users/jeremy/dev/stealth-cache")
            from stealth_cache.cache import get_cache
            self._sem_cache = get_cache()
        return self._sem_cache

    def _compressor(self):
        if self._comp_instance is None:
            import sys
            sys.path.insert(0, "/Users/jeremy/dev/stealth-compressor")
            from stealth_compressor.compressor import get_compressor
            self._comp_instance = get_compressor()
        return self._comp_instance

    def _limiter(self):
        if self._limiter_instance is None:
            import sys
            sys.path.insert(0, "/Users/jeremy/dev/stealth-optimizer")
            from stealth_optimizer.output_limiter import get_limiter
            self._limiter_instance = get_limiter()
        return self._limiter_instance

    def _batch_client(self):
        if self._batch_client is None:
            import sys
            sys.path.insert(0, "/Users/jeremy/dev/stealth-batch")
            from stealth_batch.batch_client import get_batch_client
            self._batch_client = get_batch_client()
        return self._batch_client

    def estimate_complexity(self, prompt: str, task_hint: str = "") -> str:
        routing = self.cfg.get("routing")
        thresh = routing.get("complexity_thresholds", {}) if routing else {}
        micro_max = thresh.get("micro_max_chars", 80)
        mid_max = thresh.get("mid_max_chars", 300)
        if len(prompt) <= micro_max and any(k in task_hint for k in ["classify_element", "verify_state", "pick_answer"]):
            return "micro"
        if len(prompt) <= mid_max:
            return "mid"
        return "heavy"

    def best_model_for_complexity(self, complexity: str) -> str:
        routing = self.cfg.get("routing")
        models = routing.get("models", {}) if routing else {}
        if complexity == "micro":
            return models.get("cheap", {}).get("id", "accounts/fireworks/models/llama-v3p1-8b-instruct")
        if complexity == "heavy":
            return models.get("expensive", {}).get("id", "accounts/fireworks/models/minimax-m2p7")
        return models.get("standard", {}).get("id", "accounts/fireworks/models/minimax-m2p7")

    def infer(
        self,
        prompt: str,
        api_call_fn: Callable,
        model_id: str,
        task_hint: str = "",
        complexity: str = None,
        context: Optional[dict] = None
    ) -> dict:
        compressor = self._compressor()
        compressed_prompt = compressor.compress(prompt)

        sem_cache = self._semantic_cache()
        cache_hit = sem_cache.query(compressed_prompt)
        if cache_hit:
            limiter = self._limiter()
            complexity = complexity or self.estimate_complexity(prompt, task_hint)
            trimmed = limiter.apply_to_llm_response(cache_hit["response"], complexity)
            return {"source": "cache", "response": trimmed, "similarity": cache_hit["similarity"], "hit_count": cache_hit["hit_count"]}

        complexity = complexity or self.estimate_complexity(compressed_prompt, task_hint)
        model_for_call = self.best_model_for_complexity(complexity)

        response = api_call_fn(model_id=model_for_call, prompt=compressed_prompt)

        sem_cache.store(compressed_prompt, response, model_for_call, 0.75, task_hint)

        limiter = self._limiter()
        trimmed = limiter.apply_to_llm_response(response, complexity)
        return {"source": "live", "response": trimmed, "model": model_for_call, "complexity": complexity, "compressed": compressed_prompt != prompt}

    def infer_batch(self, prompts: list, api_call_fn: Callable, model_id: str) -> list:
        client = self._batch_client()
        requests = [{"messages": [{"role": "user", "content": p}]} for p in prompts]
        result = client.submit_and_wait(requests, model_id)
        return result.get("results", [])

    def stats(self) -> dict:
        sem_cache = self._semantic_cache()
        return {
            "cache": sem_cache.stats() if sem_cache else {},
            "routing_enabled": self.cfg.is_enabled("routing"),
            "compressor_enabled": self.cfg.is_enabled("compressor"),
            "batch_enabled": self.cfg.is_enabled("batch"),
            "optimizer_enabled": self.cfg.is_enabled("output_limiter"),
        }


_optimizer = None


def get_optimizer() -> SOTAOptimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = SOTAOptimizer()
    return _optimizer