import os
import json
import logging
import hashlib

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

class ResponseCache:
    def __init__(self):
        self.redis_client = None
        self.in_memory_cache = {}
        
        if REDIS_AVAILABLE:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_db = int(os.getenv("REDIS_DB", 0))
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    socket_timeout=2.0,
                    decode_responses=True
                )
                # Ping to check if server is active
                self.redis_client.ping()
                logger.info("Connected to Redis successfully. Using Redis for caching.")
            except Exception as e:
                logger.info(f"Redis is not running ({e}). Falling back to local in-memory caching.")
                self.redis_client = None
        else:
            logger.info("redis-py not installed. Using local in-memory caching.")

    def _generate_key(self, query: str, history: str = "", image_context: str = "") -> str:
        # Create a unique SHA256 hash of the query inputs to avoid collision
        raw_string = f"q:{query.strip()}|h:{history.strip()}|i:{image_context.strip()}"
        return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

    def get(self, query: str, history: str = "", image_context: str = "") -> dict | None:
        key = self._generate_key(query, history, image_context)
        
        if self.redis_client:
            try:
                cached_val = self.redis_client.get(key)
                if cached_val:
                    logger.info("Cache HIT (Redis)!")
                    return json.loads(cached_val)
            except Exception as e:
                logger.error(f"Redis get failed: {e}")
        
        # Fallback to in-memory cache
        val = self.in_memory_cache.get(key)
        if val:
            logger.info("Cache HIT (In-Memory)!")
        return val

    def set(self, query: str, history: str = "", image_context: str = "", response_data: dict = None, ttl_seconds: int = 3600):
        if not response_data:
            return
        key = self._generate_key(query, history, image_context)
        
        if self.redis_client:
            try:
                self.redis_client.setex(key, ttl_seconds, json.dumps(response_data))
                return
            except Exception as e:
                logger.error(f"Redis set failed: {e}")
        
        # Fallback to in-memory cache
        self.in_memory_cache[key] = response_data
