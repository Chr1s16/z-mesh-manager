from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

Provider = Literal["tailscale", "netbird"]

class ActivateRequest(BaseModel):
    provider: Provider
    credential: str | None = Field(default=None, max_length=4096)
    management_url: HttpUrl | None = None

class ActionRequest(BaseModel):
    provider: Provider
    action: Literal["install", "repair", "update", "restart", "up", "down", "rollback"]

class SettingsRequest(BaseModel):
    auto_repair: bool = True
    automatic_updates: bool = False
    update_check_hours: int = Field(default=24, ge=1, le=168)
