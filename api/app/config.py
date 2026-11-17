from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Only for local development. Any other environment must set JWT_SECRET (see below).
DEV_JWT_SECRET = "dev-only-secret-do-not-use-anywhere-else-0123456789"


class Settings(BaseSettings):
    """Application settings, loaded from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "mysql+pymysql://trading:trading@localhost:3306/trading"
    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:5173"
    # Signs login tokens. Generate one with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: str = DEV_JWT_SECRET
    # How long a login lasts. There is no refresh token yet, so people sign in again after this.
    jwt_expire_minutes: int = 480

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _empty_means_not_set(cls, value: object) -> object:
        # docker compose passes JWT_SECRET="" when it is not defined in .env
        return DEV_JWT_SECRET if value == "" else value

    @model_validator(mode="after")
    def _require_a_real_secret_outside_development(self) -> "Settings":
        if self.environment != "development" and (
            self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32
        ):
            raise ValueError(
                "JWT_SECRET must be set to a random value of at least 32 characters "
                "when ENVIRONMENT is not 'development'"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
