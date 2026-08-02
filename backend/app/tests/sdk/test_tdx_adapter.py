from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.enums import Market
from app.sdk.market_data.tdx_adapter import TdxAdapter


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.closed = False
        self.calls = []

    def post(self, endpoint, json):
        self.calls.append((endpoint, json))
        symbol = json["params"]["stock_list"][0]
        count = json["params"]["count"]
        size = 2 if count != 1 else 1
        values = {
            "ErrorId": "0",
            "Open": ["10.00", "10.20"][-size:],
            "High": ["10.30", "10.60"][-size:],
            "Low": ["9.90", "10.10"][-size:],
            "Close": ["10.00", "10.50"][-size:],
            "Volume": ["1000", "1500"][-size:],
            "Date": ["20260730", "20260731"][-size:],
            "Time": ["145900", "150000"][-size:],
        }
        return FakeResponse(
            {
                "id": json["id"],
                "result": {
                    "ErrorId": "0",
                    "Value": {symbol: values},
                },
            }
        )

    def close(self):
        self.closed = True


def test_tdx_connect_quote_and_kline(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(
        "app.sdk.market_data.tdx_adapter.httpx.Client",
        lambda timeout: client,
    )
    adapter = TdxAdapter(
        market=Market.STOCK,
        config={
            "tdx_endpoint": "http://127.0.0.1:17709/",
            "tdx_poll_seconds": 3,
        },
    )

    status = adapter.connect()
    quote = adapter.get_quote("600000.SH")
    bars = adapter.get_kline(
        "600000.SH",
        "1d",
        datetime(2026, 7, 30, tzinfo=timezone.utc),
        datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    adapter.disconnect()

    assert status["connected"] is True
    assert quote.last_price == Decimal("10.50")
    assert quote.change_rate == Decimal("0.05")
    assert quote.volume == Decimal("1500")
    assert len(bars) == 2
    assert bars[-1].close == Decimal("10.50")
    assert client.closed is True
    assert all(call[0] == "http://127.0.0.1:17709/" for call in client.calls)
