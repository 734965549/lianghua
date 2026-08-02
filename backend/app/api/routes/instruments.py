"""可投标的列表：内置常用 A 股与期货合约，供前端搜索/选择。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id
from app.api.response import ok
from app.core.domestic_futures import domestic_futures_records
from app.db.models.instrument import Instrument
from app.db.session import get_db
from app.schemas.enums import Market
from app.services.instrument_catalog_service import instrument_catalog_service
from app.services.market_service import market_service

router = APIRouter(tags=["instruments"])


_STATIC_STOCKS: list[dict] = [
    {"symbol": "000001.SZ", "market": "stock", "name": "平安银行", "exchange": "SZSE"},
    {"symbol": "000002.SZ", "market": "stock", "name": "万科A", "exchange": "SZSE"},
    {"symbol": "000063.SZ", "market": "stock", "name": "中兴通讯", "exchange": "SZSE"},
    {"symbol": "000100.SZ", "market": "stock", "name": "TCL科技", "exchange": "SZSE"},
    {"symbol": "000333.SZ", "market": "stock", "name": "美的集团", "exchange": "SZSE"},
    {"symbol": "000538.SZ", "market": "stock", "name": "云南白药", "exchange": "SZSE"},
    {"symbol": "000568.SZ", "market": "stock", "name": "泸州老窖", "exchange": "SZSE"},
    {"symbol": "000625.SZ", "market": "stock", "name": "长安汽车", "exchange": "SZSE"},
    {"symbol": "000651.SZ", "market": "stock", "name": "格力电器", "exchange": "SZSE"},
    {"symbol": "000725.SZ", "market": "stock", "name": "京东方A", "exchange": "SZSE"},
    {"symbol": "000858.SZ", "market": "stock", "name": "五粮液", "exchange": "SZSE"},
    {"symbol": "000977.SZ", "market": "stock", "name": "浪潮信息", "exchange": "SZSE"},
    {"symbol": "002027.SZ", "market": "stock", "name": "分众传媒", "exchange": "SZSE"},
    {"symbol": "002049.SZ", "market": "stock", "name": "紫光国微", "exchange": "SZSE"},
    {"symbol": "002142.SZ", "market": "stock", "name": "宁波银行", "exchange": "SZSE"},
    {"symbol": "002230.SZ", "market": "stock", "name": "科大讯飞", "exchange": "SZSE"},
    {"symbol": "002304.SZ", "market": "stock", "name": "洋河股份", "exchange": "SZSE"},
    {"symbol": "002352.SZ", "market": "stock", "name": "顺丰控股", "exchange": "SZSE"},
    {"symbol": "002415.SZ", "market": "stock", "name": "海康威视", "exchange": "SZSE"},
    {"symbol": "002460.SZ", "market": "stock", "name": "赣锋锂业", "exchange": "SZSE"},
    {"symbol": "002475.SZ", "market": "stock", "name": "立讯精密", "exchange": "SZSE"},
    {"symbol": "002594.SZ", "market": "stock", "name": "比亚迪", "exchange": "SZSE"},
    {"symbol": "002714.SZ", "market": "stock", "name": "牧原股份", "exchange": "SZSE"},
    {"symbol": "300014.SZ", "market": "stock", "name": "亿纬锂能", "exchange": "SZSE"},
    {"symbol": "300015.SZ", "market": "stock", "name": "爱尔眼科", "exchange": "SZSE"},
    {"symbol": "300033.SZ", "market": "stock", "name": "同花顺", "exchange": "SZSE"},
    {"symbol": "300059.SZ", "market": "stock", "name": "东方财富", "exchange": "SZSE"},
    {"symbol": "300122.SZ", "market": "stock", "name": "智飞生物", "exchange": "SZSE"},
    {"symbol": "300124.SZ", "market": "stock", "name": "汇川技术", "exchange": "SZSE"},
    {"symbol": "300274.SZ", "market": "stock", "name": "阳光电源", "exchange": "SZSE"},
    {"symbol": "300750.SZ", "market": "stock", "name": "宁德时代", "exchange": "SZSE"},
    {"symbol": "600000.SH", "market": "stock", "name": "浦发银行", "exchange": "SSE"},
    {"symbol": "600009.SH", "market": "stock", "name": "上海机场", "exchange": "SSE"},
    {"symbol": "600028.SH", "market": "stock", "name": "中国石化", "exchange": "SSE"},
    {"symbol": "600030.SH", "market": "stock", "name": "中信证券", "exchange": "SSE"},
    {"symbol": "600031.SH", "market": "stock", "name": "三一重工", "exchange": "SSE"},
    {"symbol": "600036.SH", "market": "stock", "name": "招商银行", "exchange": "SSE"},
    {"symbol": "600048.SH", "market": "stock", "name": "保利发展", "exchange": "SSE"},
    {"symbol": "600050.SH", "market": "stock", "name": "中国联通", "exchange": "SSE"},
    {"symbol": "600104.SH", "market": "stock", "name": "上汽集团", "exchange": "SSE"},
    {"symbol": "600111.SH", "market": "stock", "name": "北方稀土", "exchange": "SSE"},
    {"symbol": "600150.SH", "market": "stock", "name": "中国船舶", "exchange": "SSE"},
    {"symbol": "600196.SH", "market": "stock", "name": "复星医药", "exchange": "SSE"},
    {"symbol": "600276.SH", "market": "stock", "name": "恒瑞医药", "exchange": "SSE"},
    {"symbol": "600309.SH", "market": "stock", "name": "万华化学", "exchange": "SSE"},
    {"symbol": "600406.SH", "market": "stock", "name": "国电南瑞", "exchange": "SSE"},
    {"symbol": "600436.SH", "market": "stock", "name": "片仔癀", "exchange": "SSE"},
    {"symbol": "600519.SH", "market": "stock", "name": "贵州茅台", "exchange": "SSE"},
    {"symbol": "600570.SH", "market": "stock", "name": "恒生电子", "exchange": "SSE"},
    {"symbol": "600585.SH", "market": "stock", "name": "海螺水泥", "exchange": "SSE"},
    {"symbol": "600690.SH", "market": "stock", "name": "海尔智家", "exchange": "SSE"},
    {"symbol": "600703.SH", "market": "stock", "name": "三安光电", "exchange": "SSE"},
    {"symbol": "600809.SH", "market": "stock", "name": "山西汾酒", "exchange": "SSE"},
    {"symbol": "600887.SH", "market": "stock", "name": "伊利股份", "exchange": "SSE"},
    {"symbol": "600900.SH", "market": "stock", "name": "长江电力", "exchange": "SSE"},
    {"symbol": "601012.SH", "market": "stock", "name": "隆基绿能", "exchange": "SSE"},
    {"symbol": "601088.SH", "market": "stock", "name": "中国神华", "exchange": "SSE"},
    {"symbol": "601138.SH", "market": "stock", "name": "工业富联", "exchange": "SSE"},
    {"symbol": "601166.SH", "market": "stock", "name": "兴业银行", "exchange": "SSE"},
    {"symbol": "601288.SH", "market": "stock", "name": "农业银行", "exchange": "SSE"},
    {"symbol": "601318.SH", "market": "stock", "name": "中国平安", "exchange": "SSE"},
    {"symbol": "601328.SH", "market": "stock", "name": "交通银行", "exchange": "SSE"},
    {"symbol": "601398.SH", "market": "stock", "name": "工商银行", "exchange": "SSE"},
    {"symbol": "601601.SH", "market": "stock", "name": "中国太保", "exchange": "SSE"},
    {"symbol": "601628.SH", "market": "stock", "name": "中国人寿", "exchange": "SSE"},
    {"symbol": "601688.SH", "market": "stock", "name": "华泰证券", "exchange": "SSE"},
    {"symbol": "601766.SH", "market": "stock", "name": "中国中车", "exchange": "SSE"},
    {"symbol": "601857.SH", "market": "stock", "name": "中国石油", "exchange": "SSE"},
    {"symbol": "601888.SH", "market": "stock", "name": "中国中免", "exchange": "SSE"},
    {"symbol": "601899.SH", "market": "stock", "name": "紫金矿业", "exchange": "SSE"},
    {"symbol": "601919.SH", "market": "stock", "name": "中远海控", "exchange": "SSE"},
    {"symbol": "603288.SH", "market": "stock", "name": "海天味业", "exchange": "SSE"},
    {"symbol": "603501.SH", "market": "stock", "name": "韦尔股份", "exchange": "SSE"},
    {"symbol": "603986.SH", "market": "stock", "name": "兆易创新", "exchange": "SSE"},
    {"symbol": "603993.SH", "market": "stock", "name": "洛阳钼业", "exchange": "SSE"},
    {"symbol": "688008.SH", "market": "stock", "name": "澜起科技", "exchange": "SSE"},
    {"symbol": "688111.SH", "market": "stock", "name": "金山办公", "exchange": "SSE"},
    {"symbol": "688169.SH", "market": "stock", "name": "石头科技", "exchange": "SSE"},
    {"symbol": "688256.SH", "market": "stock", "name": "寒武纪", "exchange": "SSE"},
    {"symbol": "688271.SH", "market": "stock", "name": "联影医疗", "exchange": "SSE"},
    {"symbol": "688981.SH", "market": "stock", "name": "中芯国际", "exchange": "SSE"},
]

_STATIC_FUTURES: list[dict] = domestic_futures_records()

_ALL_INSTRUMENTS: list[dict] = _STATIC_STOCKS + _STATIC_FUTURES


@router.get("/instruments")
def list_instruments(
    query: str = Query("", description="按代码或名称过滤"),
    market: str = Query("", description="按市场过滤：stock/futures"),
    limit: int = Query(50, ge=1, le=10_000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """返回动态标的目录；尚未同步成功的市场使用内置清单兜底。"""
    q = query.strip().lower()
    m = market.strip().lower()

    dynamic_rows = (
        db.query(Instrument)
        .filter(Instrument.is_active.is_(True))
        .order_by(Instrument.market.asc(), Instrument.symbol.asc())
        .all()
    )
    dynamic_items = [
        {
            "symbol": row.symbol,
            "market": row.market.value if isinstance(row.market, Market) else str(row.market),
            "name": row.name,
            "exchange": row.exchange,
            "source": str((row.raw_payload or {}).get("catalog_source") or "database"),
        }
        for row in dynamic_rows
    ]

    dynamic_markets = {item["market"] for item in dynamic_items}
    catalog = list(dynamic_items)
    for item in _ALL_INSTRUMENTS:
        if item["market"] not in dynamic_markets:
            catalog.append({**item, "source": "bundled"})

    filtered: list[dict] = []
    for item in catalog:
        if m and item["market"] != m:
            continue
        if (
            q
            and q not in item["symbol"].lower()
            and q not in item["name"].lower()
            and q not in item["exchange"].lower()
        ):
            continue
        filtered.append(item)

    counts = {
        market_name: sum(1 for item in catalog if item["market"] == market_name)
        for market_name in ("stock", "futures")
    }
    sources = {item["source"] for item in catalog}
    source = sources.pop() if len(sources) == 1 else "mixed"
    last_synced_at = max(
        (row.updated_at for row in dynamic_rows if row.updated_at is not None),
        default=None,
    )
    return ok(
        {
            "items": filtered[offset : offset + limit],
            "total": len(filtered),
            "counts": counts,
            "source": source,
            "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
        },
        correlation_id=correlation_id,
    )


@router.post("/instruments/sync")
def sync_instruments(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """立即从当前行情源同步股票与期货标的目录。"""
    if not market_service.started:
        try:
            market_service.start()
        except Exception as exc:
            return ok(
                {
                    "status": "failed",
                    "counts": instrument_catalog_service.counts(db),
                    "errors": [f"行情源连接失败: {exc}"],
                },
                correlation_id=correlation_id,
            )
    result = instrument_catalog_service.sync_all(db)
    return ok(result, correlation_id=correlation_id)
