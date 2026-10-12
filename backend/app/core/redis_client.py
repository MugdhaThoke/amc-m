# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
# ===========================================================================

"""Redis cache client with mandatory user/tenant scoping."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.core.cache_utils import generate_cache_key, invalidate_user_cache

logger = logging.getLogger("core.redis_client")


class UserScopedRedisCache:
    """Redis cache client with mandatory user/tenant scoping."""

    def __init__(self, redis_client: Any, default_ttl: int = 3600):
        self.redis = redis_client
        self.default_ttl = default_ttl

    def get(
        self,
        namespace: str,
        key_components: Dict[str, Any],
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[Any]:
        """Get cached value with user scope."""
        cache_key = generate_cache_key(namespace, key_components, user_id, tenant_id)
        try:
            value = self.redis.get(cache_key)
            if value:
                if isinstance(value, bytes):
                    value = value.decode("utf-8")
                return json.loads(value)
        except Exception as exc:
            logger.warning("Error reading from Redis cache: %s", exc)
        return None

    def set(
        self,
        namespace: str,
        key_components: Dict[str, Any],
        value: Any,
        user_id: str,
        tenant_id: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set cached value with user scope."""
        cache_key = generate_cache_key(namespace, key_components, user_id, tenant_id)
        serialized = json.dumps(value, default=str)
        try:
            if hasattr(self.redis, "setex"):
                return bool(self.redis.setex(cache_key, ttl or self.default_ttl, serialized))
            elif hasattr(self.redis, "set"):
                return bool(self.redis.set(cache_key, serialized, ex=(ttl or self.default_ttl)))
        except Exception as exc:
            logger.warning("Error writing to Redis cache: %s", exc)
        return False

    def invalidate_user(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> int:
        """Invalidate all cache entries for a user."""
        if namespace:
            return invalidate_user_cache(self.redis, namespace, user_id, tenant_id)

        # Invalidate across all standard namespaces
        total_deleted = 0
        namespaces = ["intent", "cypher", "entity_resolve", "vector_search", "semantic_cache"]
        for ns in namespaces:
            total_deleted += invalidate_user_cache(self.redis, ns, user_id, tenant_id)

        return total_deleted
