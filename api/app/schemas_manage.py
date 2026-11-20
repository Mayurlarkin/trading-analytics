"""Request and response shapes for managing accounts and API keys."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import ApiKey

# Fields that must hold a value if they are sent at all (null would erase them).
_NOT_NULLABLE = ("label", "currency", "starting_balance", "is_demo", "server_timezone")


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=100, examples=["IFX Demo"])
    broker: str | None = Field(default=None, max_length=100)
    currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$", description="3-letter code")
    starting_balance: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    is_demo: bool = False
    server_timezone: str | None = Field(
        default=None,
        max_length=64,
        description="How to read MT5 report times: 'ny_close' or an IANA zone like Europe/Athens",
    )


class AccountUpdate(BaseModel):
    """Only the fields you send are changed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str | None = Field(default=None, min_length=1, max_length=100)
    broker: str | None = Field(default=None, max_length=100, description="null clears it")
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    starting_balance: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    is_demo: bool | None = None
    server_timezone: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _something_valid_to_change(self) -> "AccountUpdate":
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        for name in _NOT_NULLABLE:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    def changes(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str | None = Field(default=None, max_length=64, examples=["MT5 EA"])


class ApiKeyOut(BaseModel):
    """A key as listed: never the secret itself, only enough to recognise it."""

    id: int
    prefix: str
    label: str | None
    created_at: datetime
    revoked_at: datetime | None

    @classmethod
    def of(cls, key: ApiKey) -> "ApiKeyOut":
        return cls(
            id=key.id,
            prefix=key.key_prefix,
            label=key.label,
            created_at=key.created_at,
            revoked_at=key.revoked_at,
        )


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="The secret. Shown once; it cannot be retrieved later.")
