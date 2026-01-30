"""
Redis caching utilities for performance optimization
"""
import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps
import redis
from app.core.config import settings
from app.core.redis import get_redis_client
import logging

logger = logging.getLogger(__name__)

# Cache TTLs (in seconds)
CACHE_TTL = {
    "metadata": 3600,  # 1 hour - metadata rarely changes
    "patient_details": 300,  # 5 minutes - patient data changes more frequently
    "patient_search": 60,  # 1 minute - search results should be fresh
    "fee_schedules": 1800,  # 30 minutes
    "default": 300  # 5 minutes default
}


def get_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a cache key from prefix and arguments."""
    # Create a deterministic key from args and kwargs
    key_data = {
        "args": args,
        "kwargs": sorted(kwargs.items())
    }
    key_str = json.dumps(key_data, sort_keys=True, default=str)
    key_hash = hashlib.md5(key_str.encode()).hexdigest()
    return f"{prefix}:{key_hash}"


def cache_result(ttl: int = CACHE_TTL["default"], prefix: str = "cache"):
    """
    Decorator to cache function results in Redis.
    
    Usage:
        @cache_result(ttl=3600, prefix="patient_metadata")
        def get_patient_metadata():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                redis_client = get_redis_client()
                cache_key = get_cache_key(f"{prefix}:{func.__name__}", *args, **kwargs)
                
                # Try to get from cache
                cached = redis_client.get(cache_key)
                if cached:
                    logger.debug(f"Cache HIT: {cache_key}")
                    return json.loads(cached)
                
                # Cache miss - execute function
                logger.debug(f"Cache MISS: {cache_key}")
                result = await func(*args, **kwargs)
                
                # Store in cache
                if result is not None:
                    redis_client.setex(
                        cache_key,
                        ttl,
                        json.dumps(result, default=str)
                    )
                
                return result
            except redis.RedisError as e:
                logger.warning(f"Redis cache error for {func.__name__}: {e}")
                # Fallback to executing function without cache
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in cache decorator for {func.__name__}: {e}")
                return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                redis_client = get_redis_client()
                cache_key = get_cache_key(f"{prefix}:{func.__name__}", *args, **kwargs)
                
                # Try to get from cache
                cached = redis_client.get(cache_key)
                if cached:
                    logger.debug(f"Cache HIT: {cache_key}")
                    return json.loads(cached)
                
                # Cache miss - execute function
                logger.debug(f"Cache MISS: {cache_key}")
                result = func(*args, **kwargs)
                
                # Store in cache
                if result is not None:
                    # Convert Pydantic models to dict for JSON serialization
                    if hasattr(result, "dict"):
                        result_dict = result.dict()
                    elif hasattr(result, "model_dump"):
                        result_dict = result.model_dump()
                    else:
                        result_dict = result
                    
                    redis_client.setex(
                        cache_key,
                        ttl,
                        json.dumps(result_dict, default=str)
                    )
                
                return result
            except redis.RedisError as e:
                logger.warning(f"Redis cache error for {func.__name__}: {e}")
                # Fallback to executing function without cache
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in cache decorator for {func.__name__}: {e}")
                return func(*args, **kwargs)
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def invalidate_cache(pattern: str):
    """Invalidate cache entries matching a pattern."""
    try:
        redis_client = get_redis_client()
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            logger.info(f"Invalidated {len(keys)} cache entries matching {pattern}")
    except redis.RedisError as e:
        logger.warning(f"Error invalidating cache: {e}")


def get_cached(key: str) -> Optional[Any]:
    """Get a value from cache."""
    try:
        redis_client = get_redis_client()
        cached = redis_client.get(key)
        if cached:
            return json.loads(cached)
        return None
    except redis.RedisError as e:
        logger.warning(f"Error getting cache: {e}")
        return None


def set_cached(key: str, value: Any, ttl: int = CACHE_TTL["default"]):
    """Set a value in cache."""
    try:
        redis_client = get_redis_client()
        redis_client.setex(
            key,
            ttl,
            json.dumps(value, default=str)
        )
    except redis.RedisError as e:
        logger.warning(f"Error setting cache: {e}")
