from pydantic import BaseModel, Field

from app.schemas.enums import Market


class WatchlistCreateRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    market: Market
    alias: str = Field(default="", max_length=50)
    enabled: bool = True
    download_1d: bool = True
    download_1m: bool = False


class WatchlistUpdateRequest(BaseModel):
    alias: str | None = Field(default=None, max_length=50)
    enabled: bool | None = None
    download_1d: bool | None = None
    download_1m: bool | None = None


class WatchlistItemResponse(BaseModel):
    id: str
    symbol: str
    market: str
    alias: str
    enabled: bool
    download_1d: bool
    download_1m: bool
    created_at: str
    updated_at: str
