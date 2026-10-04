import json
import hashlib
import logging
from typing import Optional, Any, List
from datetime import timedelta

import redis.asyncio as redis
from pystac import Item

from api.config import settings

logger = logging.getLogger(__name__)


class STACCache:
    """Redis-based cache for STAC search results and band data."""
    
    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._enabled = settings.REDIS_URL and settings.REDIS_URL.strip()
    
    async def _get_client(self) -> redis.Redis:
        if self._client is None and self._enabled:
            self._client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None
    
    def _make_key(self, prefix: str, *args) -> str:
        """Create a deterministic cache key from arguments."""
        key_string = ":".join(str(arg) for arg in args)
        hash_suffix = hashlib.md5(key_string.encode()).hexdigest()[:12]
        return f"skydump:{prefix}:{hash_suffix}"
    
    async def get_stac_search(self, bbox: List[float], start_date: str, end_date: str, 
                              max_cloud_cover: int, limit: int) -> Optional[List[dict]]:
        """Get cached STAC search results."""
        if not self._enabled:
            return None
        
        try:
            client = await self._get_client()
            key = self._make_key("stac_search", bbox, start_date, end_date, max_cloud_cover, limit)
            cached = await client.get(key)
            if cached:
                logger.debug(f"Cache hit for STAC search: {key}")
                return json.loads(cached)
            logger.debug(f"Cache miss for STAC search: {key}")
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
        return None
    
    async def set_stac_search(self, bbox: List[float], start_date: str, end_date: str,
                              max_cloud_cover: int, limit: int, items: List[dict], 
                              ttl: int = 3600) -> bool:
        """Cache STAC search results."""
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            key = self._make_key("stac_search", bbox, start_date, end_date, max_cloud_cover, limit)
            await client.setex(key, ttl, json.dumps(items))
            logger.debug(f"Cached STAC search: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
        return False
    
    async def get_band_data(self, item_id: str, band: str) -> Optional[dict]:
        """Get cached band data."""
        if not self._enabled:
            return None
        
        try:
            client = await self._get_client()
            key = self._make_key("band", item_id, band)
            cached = await client.get(key)
            if cached:
                logger.debug(f"Cache hit for band data: {key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache get band failed: {e}")
        return None
    
    async def set_band_data(self, item_id: str, band: str, data: dict, ttl: int = 86400) -> bool:
        """Cache band data."""
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            key = self._make_key("band", item_id, band)
            await client.setex(key, ttl, json.dumps(data))
            logger.debug(f"Cached band data: {key}")
            return True
        except Exception as e:
            logger.warning(f"Cache set band failed: {e}")
        return False
    
    async def invalidate_stac_search(self, bbox: List[float]) -> bool:
        """Invalidate all STAC search caches for a bbox pattern."""
        if not self._enabled:
            return False
        
        try:
            client = await self._get_client()
            pattern = f"skydump:stac_search:*{bbox[0]}*{bbox[1]}*{bbox[2]}*{bbox[3]}*"
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await client.delete(*keys)
                logger.info(f"Invalidated {len(keys)} STAC search caches for bbox")
            return True
        except Exception as e:
            logger.warning(f"Cache invalidate failed: {e}")
        return False


# Global cache instance
stac_cache = STACCache()


async def get_cached_stac_search(
    bbox: List[float], 
    start_date: str, 
    end_date: str, 
    max_cloud_cover: int, 
    limit: int,
    fetch_func
) -> List[dict]:
    """Get STAC search results with cache fallback."""
    # Try cache first
    cached = await stac_cache.get_stac_search(bbox, start_date, end_date, max_cloud_cover, limit)
    if cached is not None:
        return cached
    
    # Fetch from source
    items = await fetch_func(bbox, start_date, end_date, max_cloud_cover, limit)
    
    # Cache results
    await stac_cache.set_stac_search(bbox, start_date, end_date, max_cloud_cover, limit, items)
    
    return items