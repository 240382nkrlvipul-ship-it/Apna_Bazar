from flask import request, jsonify
from functools import wraps
from backend.utils.cache import cache

def rate_limit(limit=60, period=60):
    """
    Flask rate limiting decorator.
    limit: maximum requests allowed
    period: window size in seconds
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Resolve client IP
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ',' in ip:
                ip = ip.split(',')[0].strip()
                
            # Create unique caching key per IP + endpoint path
            key = f"rate_limit:{ip}:{request.endpoint}"
            
            try:
                current_requests = cache.get(key)
                if current_requests is None:
                    # Initialize count
                    cache.set(key, 1, timeout=period)
                elif current_requests >= limit:
                    # Limit exceeded
                    return jsonify({
                        'message': 'Too many requests. Please slow down and try again later.',
                        'limit': limit,
                        'period': period
                    }), 429
                else:
                    # Increment count, preserving remaining TTL
                    # To simplify, we just increment. We can read remaining TTL if needed, 
                    # but simple set is fine for our light-weight limiter
                    cache.set(key, current_requests + 1, timeout=period)
            except Exception as e:
                # If cache is broken, print error but do not block client request (fail open)
                print(f"Rate Limiter error: {e}")
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator
