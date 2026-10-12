# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
semantic_cache.py
=================
Consolidated semantic cache facade.
Delegates to UnifiedSemanticCache (app.retrieval.cache) for sub-millisecond,
FAISS-backed semantic similarity without heavy model load latencies.
"""
from typing import Any, Dict, List, Optional, Tuple
from app.retrieval.cache import UnifiedSemanticCache, get_semantic_cache


class SemanticCache:
    """Wrapper around UnifiedSemanticCache providing engine compatibility."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", threshold: float = 0.88):
        self._cache = UnifiedSemanticCache(sim_threshold=threshold)
        self.threshold = threshold

    def check(
        self,
        query: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Tuple[Optional[dict], float]:
        return self._cache.check(query, user_id=user_id, tenant_id=tenant_id)

    def store(
        self,
        query: str,
        payload: dict,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        self._cache.store(query, payload, user_id=user_id, tenant_id=tenant_id)

    def invalidate_user(self, user_id: str, tenant_id: Optional[str] = None) -> int:
        return self._cache.invalidate_user(user_id, tenant_id)

    def clear(self):
        self._cache.clear()

    def warm_cache_patterns(self, precomputed_items: List[Tuple[str, dict]]):
        self._cache.warm_cache_patterns(precomputed_items)


def get_cache() -> UnifiedSemanticCache:
    """Returns the process-wide canonical semantic cache instance."""
    return get_semantic_cache()

