#!/usr/bin/env python3
"""小额限价下单并立即撤单验收脚本（sim 可跑通；native 占位安全退出）。"""

from __future__ import annotations

import argparse
import os
import sys
import time
from decimal import Decimal
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.schemas.enums import Market, OrderSide, PriceType, SignalAction
from app.sdk.base import AdapterError, SDKNotConfigured
from app.sdk.factory import get_adapter
from app.sdk.models import CancelOrderRequest, PlaceOrderRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Small limit order + cancel acceptance")
    parser.add_argument("--market", choices=["stock", "futures"], default="stock")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--price", default="10.00")
    parser.add_argument("--quantity", default="100")
    args = parser.parse_args()

    market = Market.STOCK if args.market == "stock" else Market.FUTURES
    symbol = args.symbol or ("600000.SH" if market == Market.STOCK else "IF2509")

    config = {
        "mode": settings.sdk_mode if settings.sdk_mode == "real" else "real",
        "sdk_driver": settings.sdk_driver,
        "stock_sdk_path": settings.stock_sdk_path,
        "futures_sdk_path": settings.futures_sdk_path,
        "stock_account": settings.stock_account or "SIM_STOCK_001",
        "futures_account": settings.futures_account or "SIM_FUTURES_001",
    }

    print(f"acceptance: mode=real driver={config['sdk_driver']} market={args.market}")

    if config["sdk_driver"] == "native":
        try:
            adapter = get_adapter(market, config)
            adapter.connect()
        except SDKNotConfigured as exc:
            print(f"安全退出（native 未实现，未下单）: {exc.message}")
            return 3
        except AdapterError as exc:
            print(f"安全退出（未下单）: [{exc.code}] {exc.message}")
            return 3

    if config["sdk_driver"] == "auto":
        path = settings.stock_sdk_path if market == Market.STOCK else settings.futures_sdk_path
        if path and settings.sdk_driver == "auto":
            print("auto 检测到 SDK 路径已配置，将尝试 native 占位（若未实现则安全退出）")

    try:
        adapter = get_adapter(market, config)
        adapter.connect()
        account = adapter.get_account()
        client_order_id = f"accept_{int(time.time())}_{uuid4().hex[:8]}"

        req = PlaceOrderRequest(
            client_order_id=client_order_id,
            account_id=account.account_id,
            market=market,
            symbol=symbol,
            side=OrderSide.BUY,
            action=SignalAction.OPEN,
            price_type=PriceType.LIMIT,
            price=Decimal(args.price),
            quantity=Decimal(args.quantity),
            metadata={"offset": "open"} if market == Market.FUTURES else {},
        )
        print(f"place_order: client_order_id={client_order_id} symbol={symbol}")
        place_result = adapter.place_order(req)
        print(
            f"  -> success={place_result.success} sdk_order_id={place_result.sdk_order_id} "
            f"status={place_result.status.value}"
        )

        time.sleep(0.05)
        cancel_result = adapter.cancel_order(
            CancelOrderRequest(
                client_order_id=client_order_id,
                sdk_order_id=place_result.sdk_order_id,
                market=market,
                reason="acceptance_script",
            )
        )
        print(
            f"cancel_order: success={cancel_result.success} status={cancel_result.status.value} "
            f"message={cancel_result.message}"
        )

        polled = adapter.query_orders({})
        matched = [r for r in polled if r.get("client_order_id") == client_order_id]
        if matched:
            print(f"query_orders: status={matched[0].get('status')}")

        adapter.disconnect()
        print("OK: acceptance script completed")
        return 0
    except SDKNotConfigured as exc:
        print(f"安全退出（未下单）: {exc.message}")
        return 3
    except AdapterError as exc:
        print(f"SDK 错误 [{exc.code}]: {exc.message}")
        return 1
    except Exception as exc:
        print(f"失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
