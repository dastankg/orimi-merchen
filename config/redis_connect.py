import redis.asyncio as redis_async

from config.config import load_config

config = load_config()

redis_client = redis_async.Redis(
    host=config.redis.redis_host,
    port=config.redis.redis_port,
    db=config.redis.redis_db,
    password=config.redis.redis_password,
)
