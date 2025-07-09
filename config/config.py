import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class TgBot:
    token: str


@dataclass
class RedisConfig:
    redis_host: str
    redis_port: int
    redis_db: int
    redis_password: str


@dataclass
class Config:
    tg_bot: TgBot
    redis: RedisConfig


def load_config() -> Config:
    return Config(
        tg_bot=TgBot(token=os.getenv("SECRET_KEY")),
        redis=RedisConfig(
            redis_host=os.getenv("REDIS_HOST"),
            redis_port=int(os.getenv("REDIS_PORT")),
            redis_db=int(os.getenv("REDIS_DB")),
            redis_password=os.getenv("REDIS_PASSWORD"),
        ),
    )
