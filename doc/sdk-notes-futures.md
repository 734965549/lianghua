# 同花顺期货 SDK 调研笔记

> 阶段 6 骨架期文档。真实 SDK 到位后补充 TBD 项并更新字段对照表。

## 基本信息

| 项 | 状态 |
| --- | --- |
| SDK 版本 | TBD |
| 授权方式 | TBD |
| 语言绑定 | TBD（预计 Python 或 COM + pywin32） |
| 安装路径 | `LIANGHUA_FUTURES_SDK_PATH` |
| 交易账号 | `LIANGHUA_FUTURES_ACCOUNT` |

## 接入清单（SDK 到位后按序执行）

- [ ] 1. 获取官方 SDK 文档、授权文件、最小调用示例
- [ ] 2. 填写本文「基本信息」表全部 TBD 项
- [ ] 3. 在 `backend/app/sdk/drivers/native.py` 实现 `_load_sdk()`（DLL/COM 加载）
- [ ] 4. 逐方法实现 connect / get_account / get_positions / place_order / cancel_order 等
- [ ] 5. 更新 `backend/app/sdk/mapping.py` 中期货开平/平今昨/投机套保映射
- [ ] 6. 配置 `.env`：`LIANGHUA_SDK_MODE=real`、`LIANGHUA_SDK_DRIVER=native`
- [ ] 7. 运行探活：`scripts/sdk_smoke_query.py --market futures`
- [ ] 8. 运行小额验收：`scripts/sdk_small_order_cancel.py --market futures --symbol IF2509 --quantity 1`
- [ ] 9. 勾选 `doc/testing-acceptance.md` 真实 SDK 验收项

## 连接方式

- **默认假设**：需同花顺客户端保持登录；期货含日盘/夜盘时段（见风控 `trading_sessions`）。
- **当前验收**：`LIANGHUA_SDK_DRIVER=sim` + `SimulatedThsDriver`。
- **原生驱动**：占位于 `backend/app/sdk/drivers/native.py`。

## 回调机制

- 与股票相同：回调 + 轮询双通道。

## 字段对照（期货扩展）

| Simulated 原始字段 | 标准表达 | 说明 |
| --- | --- | --- |
| `OffsetFlag` | `action` + `metadata.offset` | `O` 开, `C` 平, `CT` 平今, `CY` 平昨 |
| `HedgeFlag` | `metadata.hedge` | `S` 投机, `H` 套保 |
| `Symbol` | `symbol` | 如 `IF2509` |
| 其余账户/订单字段 | 同股票笔记 | 见 `sdk-notes-stock.md` |

### metadata 约定

```json
{
  "offset": "close_today",
  "hedge": "speculation"
}
```

## 限制与注意事项

- 平今/平昨/开平均通过 `PlaceOrderRequest.action` + `metadata` 映射到 SDK 原始字段。
- 真实枚举列表 TBD；未知状态 → `unknown`；人工确认走 `POST /api/orders/{id}/confirm-unknown`。
- **禁止**在探活/小额验收通过前对真实资金下单。

## 最小验证

```powershell
cd backend
$env:LIANGHUA_SDK_MODE="real"
$env:LIANGHUA_SDK_DRIVER="sim"
$env:LIANGHUA_FUTURES_ACCOUNT="SIM_FUTURES_001"
.\.venv\Scripts\python.exe scripts\sdk_smoke_query.py --market futures
```

## 原生驱动验收（SDK 到位后）

```powershell
cd backend
$env:LIANGHUA_SDK_MODE="real"
$env:LIANGHUA_SDK_DRIVER="native"
$env:LIANGHUA_FUTURES_SDK_PATH="C:\path\to\ths\futures\sdk"
$env:LIANGHUA_FUTURES_ACCOUNT="YOUR_ACCOUNT"
.\.venv\Scripts\python.exe scripts\sdk_smoke_query.py --market futures
.\.venv\Scripts\python.exe scripts\sdk_small_order_cancel.py --market futures --symbol IF2509 --quantity 1
```
