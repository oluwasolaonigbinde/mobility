from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class BankRead(BaseModel):
    code: str
    name: str


class AccountNameCheckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_access_token: SecretStr = Field(repr=False)
    bank_code: SecretStr = Field(repr=False)
    account_number: SecretStr = Field(repr=False)


class AccountNameCheckRead(BaseModel):
    outcome: Literal["resolved", "unavailable"]
    account_name: str | None = None
    bank_check_receipt: str
