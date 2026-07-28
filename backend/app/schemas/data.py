from pydantic import BaseModel, Field


class DataDownloadRequest(BaseModel):
    symbols: list[str] | None = Field(default=None, description="为空则使用股票池")
    intervals: list[str] = Field(default=["1d"], description="1d / 1m / 5m")
    start_date: str = Field(default="20200101", description="YYYYMMDD")
    end_date: str | None = Field(default=None, description="YYYYMMDD，默认今日")
    use_watchlist: bool = Field(default=True, description="symbols 为空时从股票池读取")


class DataDeleteRequest(BaseModel):
    market: str
    symbol: str
    interval: str | None = None
