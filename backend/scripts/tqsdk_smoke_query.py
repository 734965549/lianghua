#!/usr/bin/env python3
"""TqSdk 只读探活脚本。

验证天勤账号 + 期货公司资金账号能否登录，并查询资金/持仓/委托/成交。
绝不调用 insert_order()。日志隐藏资金账号与密码。
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.broker import manager as broker_manager
from app.broker.errors import (
    BrokerAuthenticationError,
    BrokerConfigurationError,
    BrokerLoginError,
    BrokerNativeRuntimeError,
    BrokerNotReady,
    BrokerReconciliationError,
)
from app.broker.tqsdk_mapping import mask_account_id
from app.core.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TqSdk smoke query (read-only, never places orders)"
    )
    parser.parse_args()

    broker_type = (settings.futures_broker_type or settings.broker_type).strip().lower()
    print(
        "TqSdk smoke: "
        f"futures_broker_type={broker_type or '(empty)'} "
        f"live_enabled={settings.tqsdk_live_enabled} "
        f"broker_id={settings.tqsdk_broker_id or '(empty)'} "
        f"account={mask_account_id(settings.tqsdk_account_id)} "
        f"auth_user={mask_account_id(settings.tqsdk_auth_user)} "
        "(只读探活，禁止报单)"
    )

    if broker_type != "tqsdk":
        print(
            "阻断：期货 Broker 不是 tqsdk。请设置 LIANGHUA_FUTURES_BROKER_TYPE=tqsdk。"
        )
        return 2
    if not settings.tqsdk_broker_id:
        print("阻断：缺少 LIANGHUA_TQSDK_BROKER_ID（期货公司标识，问客户经理确认）。")
        return 2
    if not settings.tqsdk_account_id or not settings.tqsdk_password:
        print("阻断：缺少 LIANGHUA_TQSDK_ACCOUNT_ID / LIANGHUA_TQSDK_PASSWORD。")
        return 2
    if not settings.tqsdk_auth_user or not settings.tqsdk_auth_password:
        print("阻断：缺少 LIANGHUA_TQSDK_AUTH_USER / LIANGHUA_TQSDK_AUTH_PASSWORD（天勤账号）。")
        return 2

    broker = None
    try:
        broker = broker_manager.get_broker("futures")
    except Exception as exc:
        print(f"Broker 初始化失败: {exc}")
        return 2

    if getattr(broker, "name", "") != "tqsdk":
        print(f"阻断：期望 TqSdkBroker，实际 name={getattr(broker, 'name', '')!r}")
        return 2

    try:
        status = broker.connect()
        print(f"connect: ready={status.get('ready')} state={status.get('trader_state')}")

        account = broker.get_account()
        print(
            f"account: total_asset={account.total_asset} available_cash={account.available_cash} "
            f"balance={account.balance} curr_margin={account.curr_margin} "
            f"account_no={account.account_no}"
        )

        positions = broker.get_positions()
        print(f"positions: count={len(positions)}")
        for pos in positions[:20]:
            print(
                f"  - {pos.symbol} {pos.direction} qty={pos.quantity} "
                f"today={pos.quantity_today} yest={pos.quantity_yesterday} margin={pos.margin}"
            )

        orders = broker.query_orders()
        print(f"orders: count={len(orders)}")
        for order in orders[:20]:
            print(
                f"  - id={order.sdk_order_id} {order.symbol} status={order.status} "
                f"filled={order.filled_quantity} left={order.remaining_quantity}"
            )

        trades = broker.query_trades()
        print(f"trades: count={len(trades)}")
        for trade in trades[:20]:
            print(
                f"  - trade={trade.sdk_trade_id} order={trade.sdk_order_id} "
                f"{trade.symbol} {trade.side} qty={trade.quantity} px={trade.price}"
            )

        print("OK: TqSdk smoke query completed (no orders placed)")
        return 0
    except BrokerNotReady as exc:
        print(f"TqSdk 通道未就绪: {exc.message}")
        return 3
    except BrokerAuthenticationError as exc:
        print(
            f"认证失败: {exc.message}\n"
            "  若提示 CTP 客户端认证失败，请让期货公司把账户绑定到天勤中继 AppID。"
        )
        return 3
    except BrokerLoginError as exc:
        print(f"登录失败: {exc.message}")
        return 3
    except BrokerConfigurationError as exc:
        print(f"配置错误: {exc.message}")
        return 2
    except BrokerReconciliationError as exc:
        print(f"对账/查询失败: {exc.message}")
        return 4
    except BrokerNativeRuntimeError as exc:
        print(f"运行时错误: {exc.message}")
        return 1
    except Exception as exc:
        print(f"失败: {exc}")
        return 1
    finally:
        if broker is not None:
            try:
                broker.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
