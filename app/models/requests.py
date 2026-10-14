from __future__ import annotations

from pydantic import BaseModel, field_validator, model_validator
from typing import Literal


class CrawlRequest(BaseModel):
    url: str
    auto: bool = True          # auto-traverse until queue empty (recommended)
    max_depth: int | None = None   # ignored when auto=True
    max_pages: int | None = None   # ignored when auto=True (safety ceiling still applies)
    vendor: str | None = None  # ukg, workday, adp, dayforce, toast, or null for auto-detect

    model_config = {
        "json_schema_extra": {
            "example": {
                "url": "https://developer.ukg.com/wfm/reference/welcome-to-the-ukg-pro-workforce-management-api",
                "auto": True,
                "vendor": None,
            }
        }
    }

    @field_validator("url", "vendor", mode="before")
    @classmethod
    def strip_whitespace(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("vendor", mode="after")
    @classmethod
    def normalize_vendor(cls, v: str | None) -> str | None:
        _valid = {"ukg", "workday", "adp", "dayforce", "toast"}
        if v is None or v.lower() not in _valid:
            return None
        return v.lower()

    @field_validator("max_depth", "max_pages", mode="before")
    @classmethod
    def default_if_none(cls, v, info):
        defaults = {"max_depth": 3, "max_pages": 100}
        if v is None or v == "":
            return defaults.get(info.field_name, v)
        return v
