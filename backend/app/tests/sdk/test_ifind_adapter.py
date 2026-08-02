from types import SimpleNamespace

import pandas as pd
import pytest

from app.schemas.enums import Market
from app.sdk.base import SDKAuthFailed
from app.sdk.market_data.ifind_adapter import IFindAdapter


class FakeIFindApi:
    def __init__(self, *, login_result: int = 0):
        self.login_result = login_result
        self.logout_calls = 0

    def THS_iFinDLogin(self, username, password):
        return self.login_result

    def THS_iFinDLogout(self):
        self.logout_calls += 1
        return 0

    def THS_RQ(self, symbols, indicators):
        codes = symbols.split(",")
        return SimpleNamespace(
            errorcode=0,
            errmsg="",
            thscode=codes,
            time=["2026-07-31 10:30:00"] * len(codes),
            data=pd.DataFrame(
                [
                    {
                        "thscode": code,
                        "time": "2026-07-31 10:30:00",
                        "latest": 12.34,
                        "changeRatio": 1.25,
                        "volume": 500,
                        "bid1": 12.33,
                        "ask1": 12.35,
                    }
                    for code in codes
                ]
            ),
        )

    def THS_DR(self, report, params, fields):
        if report == "p03291":
            data = pd.DataFrame(
                [
                    {
                        "p03291_f001": "600000.SH",
                        "p03291_f002": "浦发银行",
                        "p03291_f003": "上海证券交易所",
                    },
                    {
                        "p03291_f001": "000001.SZ",
                        "p03291_f002": "平安银行",
                        "p03291_f003": "深圳证券交易所",
                    },
                ]
            )
        else:
            exchange = params.split("=", 1)[-1]
            codes = {
                "CFFEX": ("IF2608", "沪深300股指期货"),
                "SHFE": ("cu2609", "沪铜"),
                "INE": ("sc2609", "原油"),
                "DCE": ("m2609", "豆粕"),
                "CZCE": ("TA609", "PTA"),
                "GFEX": ("si2609", "工业硅"),
            }
            code, name = codes[exchange]
            data = pd.DataFrame(
                [{"p00001_f001": code, "p00001_f002": name}]
            )
        return SimpleNamespace(errorcode=0, errmsg="", data=data)


@pytest.fixture(autouse=True)
def reset_ifind_session():
    IFindAdapter._session_refs = 0
    IFindAdapter._session_username = ""
    IFindAdapter._api_module = None
    yield
    IFindAdapter._session_refs = 0
    IFindAdapter._session_username = ""
    IFindAdapter._api_module = None


def test_ifind_connect_and_quote(monkeypatch):
    fake = FakeIFindApi()
    monkeypatch.setattr(IFindAdapter, "_api_module", fake)
    adapter = IFindAdapter(
        market=Market.STOCK,
        config={
            "ifind_username": "demo",
            "ifind_password": "secret",
            "ifind_poll_seconds": 3,
        },
    )

    status = adapter.connect()
    quote = adapter.get_quote("600000.SH")
    adapter.disconnect()

    assert status["connected"] is True
    assert quote.symbol == "600000.SH"
    assert str(quote.last_price) == "12.34"
    assert str(quote.change_rate) == "0.0125"
    assert str(quote.volume) == "500"
    assert str(quote.bid_price) == "12.33"
    assert str(quote.ask_price) == "12.35"
    assert quote.quote_time.isoformat().startswith("2026-07-31T10:30:00")
    assert fake.logout_calls == 1


def test_ifind_auth_failure(monkeypatch):
    fake = FakeIFindApi(login_result=-2)
    monkeypatch.setattr(IFindAdapter, "_api_module", fake)
    adapter = IFindAdapter(
        market=Market.STOCK,
        config={
            "ifind_username": "wrong",
            "ifind_password": "wrong",
        },
    )

    with pytest.raises(SDKAuthFailed, match="用户名或密码错误"):
        adapter.connect()


def test_ifind_lists_all_a_share_instruments(monkeypatch):
    fake = FakeIFindApi()
    monkeypatch.setattr(IFindAdapter, "_api_module", fake)
    adapter = IFindAdapter(
        market=Market.STOCK,
        config={"ifind_username": "demo", "ifind_password": "secret"},
    )
    adapter.connect()

    instruments = adapter.list_instruments()

    assert [item["symbol"] for item in instruments] == ["600000.SH", "000001.SZ"]
    assert instruments[0]["name"] == "浦发银行"
    assert instruments[0]["exchange"] == "SSE"


def test_ifind_lists_futures_from_six_exchanges(monkeypatch):
    fake = FakeIFindApi()
    monkeypatch.setattr(IFindAdapter, "_api_module", fake)
    adapter = IFindAdapter(
        market=Market.FUTURES,
        config={"ifind_username": "demo", "ifind_password": "secret"},
    )
    adapter.connect()

    instruments = adapter.list_instruments()
    symbols = {item["symbol"] for item in instruments}

    assert symbols == {
        "IF2608.CFE",
        "CU2609.SHF",
        "SC2609.INE",
        "M2609.DCE",
        "TA609.ZCE",
        "SI2609.GFE",
    }
