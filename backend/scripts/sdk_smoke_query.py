#!/usr/bin/env python3
"""最小 SDK 查询脚本：连接、查账户、查持仓（不下单）。"""

from __future__ import annotations

import argparse
import os
import sys

# 确保 backend 根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.schemas.enums import Market
from app.sdk.base import AdapterError
from app.sdk.factory import get_adapter


def main() -> int:
    parser = argparse.ArgumentParser(description="SDK smoke query (no orders)")
    parser.add_argument("--market", choices=["stock", "futures"], default="stock")
    args = parser.parse_args()

    market = Market.STOCK if args.market == "stock" else Market.FUTURES
    config = {
        "mode": settings.sdk_mode,
        "sdk_driver": settings.sdk_driver,
        "stock_sdk_path": settings.stock_sdk_path,
        "futures_sdk_path": settings.futures_sdk_path,
        "stock_account": settings.stock_account or "SIM_STOCK_001",
        "futures_account": settings.futures_account or "SIM_FUTURES_001",
    }

    print(f"SDK mode={settings.sdk_mode} driver={settings.sdk_driver} market={args.market}")

    if settings.sdk_mode == "mock":
        print("当前为 mock 模式，将使用 MockTradingAdapter 做查询验证。")
    elif settings.sdk_driver == "auto":
        path = settings.stock_sdk_path if market == Market.STOCK else settings.futures_sdk_path
        account = settings.stock_account if market == Market.STOCK else settings.futures_account
        if not path or not account:
            print(
                "阻断：real + auto 模式下 SDK 路径或账号未配置。\n"
                "  请设置 LIANGHUA_STOCK/FUTURES_SDK_PATH 与 ACCOUNT，\n"
                "  或临时使用 LIANGHUA_SDK_DRIVER=sim 做映射验收。"
            )
            return 2

    try:
        adapter = get_adapter(market, config)
        status = adapter.connect()
        print(f"connect: connected={status.connected} account_no={status.account_no} latency_ms={status.latency_ms}")

        account = adapter.get_account()
        print(
            f"account: total_asset={account.total_asset} available_cash={account.available_cash} "
            f"market_value={account.market_value}"
        )

        positions = adapter.get_positions()
        print(f"positions: count={len(positions)}")
        for pos in positions[:5]:
            print(f"  - {pos.symbol} qty={pos.quantity} pnl={pos.pnl}")

        adapter.disconnect()
        print("OK: smoke query completed (no orders placed)")
        return 0
    except AdapterError as exc:
        print(f"SDK 错误 [{exc.code}]: {exc.message}")
        return 1
    except Exception as exc:
        print(f"失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
