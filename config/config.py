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


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise ValueError(f"Environment variable {name} is required")
    return value


def _get_required_int_env(name: str) -> int:
    value = _get_required_env(name)
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def load_config() -> Config:
    return Config(
        tg_bot=TgBot(token=_get_required_env("SECRET_KEY")),
        redis=RedisConfig(
            redis_host=_get_required_env("REDIS_HOST"),
            redis_port=_get_required_int_env("REDIS_PORT"),
            redis_db=_get_required_int_env("REDIS_DB"),
            redis_password=_get_required_env("REDIS_PASSWORD"),
        ),
    )
