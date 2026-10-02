import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignEnquiryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str = Field(min_length=1, max_length=160)
    contact_name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(default="", max_length=32)
    brief: str = Field(min_length=1, max_length=2000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
            raise ValueError("Enter a valid email address")
        return value.lower()

    @field_validator("company", "contact_name", "email", "phone", "brief")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Unsupported control character")
        return value


class CampaignEnquiryRead(BaseModel):
    status: str = "submitted"
