from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr
    exa_api_key: SecretStr = SecretStr("")
    exa_content_top_n: int = 5
    exa_exclude_domains: list[str] = [
        "w3schools.com",
        "geeksforgeeks.org",
        "tutorialspoint.com",
        "medium.com",
    ]
    exa_min_published_year_offset: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
