# 同花顺股票 SDK 调研笔记

> 阶段 6 骨架期文档。真实 SDK 到位后补充 TBD 项并更新字段对照表。

## 基本信息

| 项 | 状态 |
| --- | --- |
| SDK 版本 | TBD |
| 授权方式 | TBD |
| 语言绑定 | TBD（预计 Python 或 COM + pywin32） |
| 安装路径 | `LIANGHUA_STOCK_SDK_PATH` |
| 交易账号 | `LIANGHUA_STOCK_ACCOUNT` |

## 接入清单（SDK 到位后按序执行）

- [ ] 1. 获取官方 SDK 文档、授权文件、最小调用示例
- [ ] 2. 填写本文「基本信息」表全部 TBD 项
- [ ] 3. 在 `backend/app/sdk/drivers/native.py` 实现 `_load_sdk()`（DLL/COM 加载）
- [ ] 4. 逐方法实现 connect / get_account / get_positions / place_order / cancel_order 等
- [ ] 5. 更新 `backend/app/sdk/mapping.py` 中 `THS_ORDER_STATUS_MAP`（真实枚举）
- [ ] 6. 配置 `.env`：`LIANGHUA_SDK_MODE=real`、`LIANGHUA_SDK_DRIVER=native`
- [ ] 7. 运行探活：`scripts/sdk_smoke_query.py --market stock`
- [ ] 8. 运行小额验收：`scripts/sdk_small_order_cancel.py --market stock --symbol 600000.SH --quantity 100`
- [ ] 9. 勾选 `doc/testing-acceptance.md` 真实 SDK 验收项

## 连接方式

- **默认假设**：需同花顺客户端保持登录（见 `open-questions.md` §4）。
- **当前验收**：使用 `LIANGHUA_SDK_DRIVER=sim` + `SimulatedThsDriver` 验证适配层映射。
- **原生驱动**：`NativeThsDriver` 占位，SDK 文档到位后填充 `backend/app/sdk/drivers/native.py`。

## 回调机制

- **默认假设**：回调 + 轮询双通道（订单 5s、资金/持仓 15s）。
- Simulated 驱动支持异步订单/成交回调，用于双通道幂等测试。

## 字段对照（Simulated 模拟字段 → 标准模型）

| Simulated 原始字段 | 标准模型字段 | 说明 |
| --- | --- | --- |
| `AcctNo` | `account_no` | 资金账号 |
| `TotalAsset` | `total_asset` | 总资产 |
| `AvailCash` | `available_cash` | 可用资金 |
| `FrozenCash` | `frozen_cash` | 冻结资金 |
| `MktValue` | `market_value` | 市值 |
| `Symbol` | `symbol` | 标的，如 `600000.SH` |
| `LastPrice` | `last_price` | 最新价 |
| `OrderID` | `sdk_order_id` | SDK 委托号（**不透传** `client_order_id`） |
| `OrderStatus` | `status` | 见 mapping.py 状态表 |
| `Side` | `side` | `B`→buy, `S`→sell |

## 限制与注意事项

- 查询频率：保守 5–15s 轮询，以 SDK 文档为准后可调整。
- 未知订单状态 → 标准 `unknown` + `system_events`；人工确认走 `POST /api/orders/{id}/confirm-unknown`。
- 真实 DLL/COM 调用不得在本骨架中伪造；仅填 `NativeThsDriver`。
- **禁止**在探活/小额验收通过前对真实资金下单。

## 最小验证

```powershell
cd backend
$env:LIANGHUA_SDK_MODE="real"
$env:LIANGHUA_SDK_DRIVER="sim"
$env:LIANGHUA_STOCK_ACCOUNT="SIM_STOCK_001"
.\.venv\Scripts\python.exe scripts\sdk_smoke_query.py --market stock
```

## 原生驱动验收（SDK 到位后）

```powershell
cd backend
$env:LIANGHUA_SDK_MODE="real"
$env:LIANGHUA_SDK_DRIVER="native"
$env:LIANGHUA_STOCK_SDK_PATH="C:\path\to\ths\sdk"
$env:LIANGHUA_STOCK_ACCOUNT="YOUR_ACCOUNT"
.\.venv\Scripts\python.exe scripts\sdk_smoke_query.py --market stock
.\.venv\Scripts\python.exe scripts\sdk_small_order_cancel.py --market stock --symbol 600000.SH --quantity 100
```
