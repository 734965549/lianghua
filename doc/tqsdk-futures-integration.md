# TqSdk（天勤）期货实盘通道实施说明

> 更新日期：2026-08-19  
> 定位：用天勤中继作为期货实盘交易通道，**绕开直接申请原生 CTP SDK 的资金门槛**。  
> 原生 CTP 直连仍以 [ctp-futures-integration.md](ctp-futures-integration.md) 为准；两条通道互斥选用，不要混用同一进程的两套实盘开关。

## 重要边界

- 绕过的是**原生 CTP 接入权限/SDK 门槛**，不是期货公司合规要求。
- 最终仍须确认：所选期货公司允许该资金账号经天勤登录，并完成客户端认证 / AppID 绑定。
- 天勤免费版只支持指定期货公司；其他公司需要专业版。见 [天勤版本说明](https://doc.shinnytech.com/tqsdk/latest/profession.html)。
- 若报「CTP客户端认证失败」，需让期货公司把账户绑定到天勤中继 AppID。见 [实盘交易说明](https://doc.shinnytech.com/tqsdk/latest/usage/trade.html)。

## 为什么独立通道，不改 CTPBroker

TqSdk 是完整上层交易 API，不是底层 CTP 动态库；它采用单线程事件循环，需要持续调用 `wait_update()`，所有 `TqApi` 操作必须集中在同一工作线程。见 [TqApi 文档](https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.api.html)。

```text
策略 / 手工下单
       ↓
BrokerManager
       ↓
TqSdkBroker（实现现有 Broker 接口）
       ↓
TqSdkRuntime（独占工作线程 + 有界命令队列）
       ↓
TqApi / 天勤中继
       ↓
期货公司实盘账户
```

## 实现现状（代码已落地）

| 项 | 路径 | 说明 |
| --- | --- | --- |
| 依赖 | `backend/requirements.txt` | `tqsdk==3.10.1` |
| 配置 | `backend/app/core/config.py`、`.env.example` | 全部 `LIANGHUA_TQSDK_*` |
| 映射 | `backend/app/broker/tqsdk_mapping.py` | 合约、开平、订单状态、账号脱敏 |
| Runtime | `backend/app/broker/tqsdk_runtime.py` | 单线程、命令队列、`Future` 回传、订单/成交指纹去重 |
| Broker | `backend/app/broker/tqsdk_broker.py` | 实现 `Broker`；查询 + 下单门禁 + 撤单 |
| 路由 | `backend/app/broker/manager.py` | `FUTURES_BROKER_TYPE=tqsdk` |
| 启动连接 | `backend/app/services/market_service.py` | 启动 connect / 停止 disconnect |
| 就绪判定 | `backend/app/services/futures_channel_service.py` | 通用期货通道 readiness（CTP/TqSdk） |
| 只读冒烟 | `backend/scripts/tqsdk_smoke_query.py` | 禁止 `insert_order` |
| 单测 | `backend/app/tests/broker/test_tqsdk_broker.py` | Fake TqApi，不连真柜台 |

### 已实现能力

- 连接 / 断开 / `is_connected` / `health`
- 查询：账户、持仓、当日委托、当日成交
- 下单 / 撤单映射（见下文）；下单需双开关
- 订单状态映射与运行中订单/成交变更回调
- 日志隐藏资金账号与密码（`***` + 后四位）

### 刻意延后（账户打通后再做）

- `trade_repo` / 迁移：把期货成交唯一键从「CTP 特例」泛化为通用五字段键
- `broker_reconciliation`：硬编码 `"ctp"` 改为实际 `broker.name`
- 生产级重连全量扫描与 DB 落库加固验收

## 配置

```env
LIANGHUA_FUTURES_BROKER_TYPE=tqsdk

LIANGHUA_TQSDK_BROKER_ID=
LIANGHUA_TQSDK_ACCOUNT_ID=
LIANGHUA_TQSDK_PASSWORD=

LIANGHUA_TQSDK_AUTH_USER=
LIANGHUA_TQSDK_AUTH_PASSWORD=

LIANGHUA_TQSDK_LIVE_ENABLED=false
LIANGHUA_TQSDK_LIVE_ARM_TOKEN=
LIANGHUA_TQSDK_COMMAND_TIMEOUT_SECONDS=10
LIANGHUA_TQSDK_COMMAND_QUEUE_SIZE=1000
```

说明：

| 变量 | 含义 |
| --- | --- |
| `TQSDK_BROKER_ID` | TqSdk 期货公司标识；**问客户经理确认**，不要写死在代码里 |
| `TQSDK_ACCOUNT_ID` / `PASSWORD` | 期货资金账号与交易密码 |
| `TQSDK_AUTH_USER` / `AUTH_PASSWORD` | 天勤平台账号密码（`TqAuth`） |
| `TQSDK_LIVE_ENABLED` | 实盘总开关；默认 `false` |
| `TQSDK_LIVE_ARM_TOKEN` | 第二道确认口令；需调用 `arm_live_trading(token)` |

### 实盘双开关

关闭 `TQSDK_LIVE_ENABLED` 后：

- 禁止新开仓和普通下单
- **仍允许撤单**
- **仍允许**查询账户、持仓、委托、成交

开启后还须 `arm_live_trading()` 校验 arm token，才允许报单。

## 选期货公司时要问客户经理的问题

1. 是否允许资金账号通过天勤 / TqSdk 实盘交易？
2. 是否有最低入金或留存资金要求？
3. 是否需要程序化交易报备？
4. 是否需要绑定天勤中继 AppID？
5. TqSdk 中对应的准确期货公司标识（`TQSDK_BROKER_ID`）是什么？

## 字段与行为映射

### 合约

| 项目 | TqSdk |
| --- | --- |
| `rb2610` + `exchange_id=SHFE` | `SHFE.rb2610` |
| `SHFE.rb2610` | 原样 |
| `RB2610.SHF` | `SHFE.RB2610` |

缺少明确交易所代码时**拒绝下单**，不猜测。

### 开平 / 方向 / 价格

| 项目 | TqSdk |
| --- | --- |
| `BUY` / `SELL` | `direction` |
| `OPEN` | `OPEN` |
| `CLOSE` | `CLOSE` |
| `CLOSE_TODAY` | `CLOSETODAY`（仅 SHFE/INE；其他交易所拒绝） |
| `CLOSE_YESTERDAY` | `CLOSE`（SHFE/INE 平昨语义） |
| `LIMIT` + 价格 | `limit_price` |

首版只支持：限价单、正整数手数、投机单、明确交易所。套利 / 套保 / 市价等**明确拒绝**，不静默降级。

### 订单状态

| TqSdk | 项目状态 |
| --- | --- |
| `ALIVE`，成交量 0 | `SUBMITTED` |
| `ALIVE`，已有部分成交 | `PARTIALLY_FILLED` |
| `FINISHED`，全部成交 | `FILLED` |
| `FINISHED`，`is_error` | `FAILED` |
| `FINISHED`，仍有剩余数量 | `CANCELLED` |

```text
filled_quantity = volume_orign - volume_left
```

### 成交

- `sdk_trade_id = trade.trade_id`
- `sdk_order_id = trade.order_id`
- `broker_type = "tqsdk"`
- 保留 `exchange_trade_id`、交易所、原始字段于 `raw_payload`

### 稳定 order_id

`client_order_id` 会转换成符合 TqSdk 的稳定 `order_id`（`insert_order(order_id=...)`），便于重连后匹配本地订单。

### 最重要的一条

> 下单超时或网络断开时，返回「结果未知」（`BrokerSubmitOutcomeUnknown`），**绝对不能自动重试**。  
> 第一次请求可能已到交易所，自动重试可能造成双单。

## Runtime 模型

```text
启动线程
  → 创建 TqApi(TqAccount + TqAuth)
  → 查询初始账户/持仓/委托/成交
  → 初始对账，状态 ready
  → 循环：处理命令队列 + wait_update()
```

- FastAPI / 业务线程**不能**直接碰 `TqApi`
- 请求经有界队列提交命令，Runtime 用 `Future` 返回结果
- 维护：订单状态指纹、已处理 `trade_id` 集合；启动时预填，避免把历史单当新事件推送

## 只读验收（第一优先）

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # 含 tqsdk==3.10.1
# 填好 .env 后：
.\.venv\Scripts\python.exe scripts\tqsdk_smoke_query.py
```

脚本只做：登录、查资金/持仓/委托/成交；**永不报单**。

建议顺序：

1. 只读登录成功，连续跑至少一个交易时段
2. 账户、持仓与期货公司官方客户端一致
3. 重启服务后查询无异常重复
4. （再开 live）人工限价 1 手 → 官方客户端可见 → 撤单一致
5. 真实成交一次
6. 断网 / 重连 / 下单超时：确认不会自动重复下单
7. 实盘总开关与风控拦截

## 与 CTP 通道对照

| 维度 | 原生 CTP | TqSdk |
| --- | --- | --- |
| 配置开关 | `FUTURES_BROKER_TYPE=ctp` | `FUTURES_BROKER_TYPE=tqsdk` |
| 门槛 | 需原生 SDK / 期货公司程序化权限资料较全 | 天勤账号 + 支持的期货公司账户 |
| 运行模型 | SPI 回调 + 事件队列 | 单线程 `wait_update` + 命令队列 |
| 委托关联 | `front_id/session_id/order_ref` | 稳定 `order_id` |
| 冒烟脚本 | `scripts/ctp_smoke_query.py` | `scripts/tqsdk_smoke_query.py` |
| 设计文档 | [ctp-futures-integration.md](ctp-futures-integration.md) | 本文 |

## 相关链接

- [TqApi 参考](https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.api.html)
- [业务对象 Account / Position / Order / Trade](https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.objs.html)
- [实盘交易与 AppID](https://doc.shinnytech.com/tqsdk/latest/usage/trade.html)
- [专业版 / 免费版期货公司范围](https://doc.shinnytech.com/tqsdk/latest/profession.html)
