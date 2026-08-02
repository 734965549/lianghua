from app.db.models.instrument import Instrument
from app.schemas.enums import Market
from app.services.instrument_catalog_service import InstrumentCatalogService


class CatalogAdapter:
    name = "ifind"

    def __init__(self, records):
        self.records = records

    def list_instruments(self):
        return self.records


def test_sync_all_persists_stock_and_futures_catalog(db, monkeypatch):
    stock = CatalogAdapter(
        [
            {
                "symbol": "600000.SH",
                "name": "浦发银行",
                "exchange": "SSE",
            },
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "exchange": "SZSE",
            },
        ]
    )
    futures = CatalogAdapter(
        [
            {
                "symbol": "IF2608.CFE",
                "name": "沪深300股指期货",
                "exchange": "CFFEX",
            }
        ]
    )
    monkeypatch.setattr(
        "app.services.instrument_catalog_service.sdk_manager.get_adapter_for_market",
        lambda market: stock if market == Market.STOCK else futures,
    )
    db.query(Instrument).delete(synchronize_session=False)
    db.commit()

    result = InstrumentCatalogService().sync_all(db)

    assert result["status"] == "ok"
    assert result["counts"] == {"stock": 2, "futures": 1}
    rows = db.query(Instrument).order_by(Instrument.symbol.asc()).all()
    assert [row.symbol for row in rows] == [
        "000001.SZ",
        "600000.SH",
        "IF2608.CFE",
    ]
    assert all(row.raw_payload["catalog_source"] == "ifind" for row in rows)
