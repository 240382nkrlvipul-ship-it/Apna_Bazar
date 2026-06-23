import os
import time
import json
import pickle

# Check if redis is installed
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

class CacheManager:
    def __init__(self):
        self.use_redis = False
        self.redis_client = None
        self.local_cache = {} # Structure: {key: {'value': serialized_value, 'expires': timestamp}}
        
        if REDIS_AVAILABLE:
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
            try:
                # Set a low connection timeout to fail fast if Redis is down
                self.redis_client = redis.Redis.from_url(redis_url, socket_connect_timeout=2)
                # Test connection
                self.redis_client.ping()
                self.use_redis = True
                print(f"CacheManager: Successfully connected to Redis at {redis_url}")
            except Exception as e:
                print(f"CacheManager: Redis connection failed ({e}). Falling back to local in-memory cache.")
                self.use_redis = False
        else:
            print("CacheManager: 'redis' package is not installed. Falling back to local in-memory cache.")

    def get(self, key):
        """Get key value from cache"""
        if self.use_redis:
            try:
                data = self.redis_client.get(key)
                if data:
                    return pickle.loads(data)
                return None
            except Exception as e:
                print(f"CacheManager: Redis GET error ({e}), falling back to memory.")
                # Temporary local lookup if Redis fails mid-operation
                return self._get_local(key)
        else:
            return self._get_local(key)

    def set(self, key, value, timeout=300):
        """Set key with value and expiry time in seconds"""
        if self.use_redis:
            try:
                serialized = pickle.dumps(value)
                self.redis_client.setex(key, timeout, serialized)
                return True
            except Exception as e:
                print(f"CacheManager: Redis SET error ({e}), falling back to memory.")
                self._set_local(key, value, timeout)
        else:
            self._set_local(key, value, timeout)

    def delete(self, key):
        """Delete key from cache"""
        if self.use_redis:
            try:
                self.redis_client.delete(key)
                return True
            except Exception as e:
                print(f"CacheManager: Redis DEL error ({e})")
                self._delete_local(key)
        else:
            self._delete_local(key)

    def clear_pattern(self, pattern):
        """Delete keys matching pattern (e.g. 'products:*')"""
        if self.use_redis:
            try:
                # Convert glob pattern to scan
                cursor = 0
                while True:
                    cursor, keys = self.redis_client.scan(cursor=cursor, match=pattern, count=100)
                    if keys:
                        self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
                return True
            except Exception as e:
                print(f"CacheManager: Redis SCAN/DELETE pattern error ({e})")
                self._clear_pattern_local(pattern)
        else:
            self._clear_pattern_local(pattern)

    # Local Cache Helpers
    def _get_local(self, key):
        self._cleanup_expired()
        entry = self.local_cache.get(key)
        if entry:
            if entry['expires'] > time.time():
                # Return deep copy of picked object to simulate network boundary
                return pickle.loads(pickle.dumps(entry['value']))
            else:
                self.local_cache.pop(key, None)
        return None

    def _set_local(self, key, value, timeout):
        # Store copied value
        expires = time.time() + timeout
        self.local_cache[key] = {
            'value': pickle.loads(pickle.dumps(value)),
            'expires': expires
        }

    def _delete_local(self, key):
        self.local_cache.pop(key, None)

    def _clear_pattern_local(self, pattern):
        # Convert simple glob to starts-with/contains check
        prefix = pattern.replace('*', '')
        keys_to_del = [k for k in self.local_cache.keys() if k.startswith(prefix)]
        for k in keys_to_del:
            self.local_cache.pop(k, None)

    def _cleanup_expired(self):
        now = time.time()
        expired_keys = [k for k, v in self.local_cache.items() if v['expires'] <= now]
        for k in expired_keys:
            self.local_cache.pop(k, None)

# Global cache instance
cache = CacheManager()
