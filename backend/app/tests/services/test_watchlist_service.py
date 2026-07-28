"""股票池服务测试。"""

from app.services.watchlist_service import watchlist_service


def test_watchlist_defaults_and_crud(db):
    watchlist_service.ensure_defaults(db)
    db.commit()
    items = watchlist_service.list_items(db)
    assert len(items) >= 2
    symbols = {i["symbol"] for i in items}
    assert "600000.SH" in symbols

    added = watchlist_service.add_item(
        db, symbol="000001.SZ", market="stock", alias="平安银行"
    )
    assert added["symbol"] == "000001.SZ"

    updated = watchlist_service.update_item(
        db, "stock", "000001.SZ", alias="平安"
    )
    assert updated["alias"] == "平安"

    watchlist_service.remove_item(db, "stock", "000001.SZ")
    db.commit()
    remaining = {i["symbol"] for i in watchlist_service.list_items(db)}
    assert "000001.SZ" not in remaining
