"""国内期货品种主力连续合约目录。

目录使用新浪/AKShare 可识别的 ``品种代码 + 0`` 形式。主连比固定交割月
合约更适合行情工作台：不会因为合约到期而让整个品种从列表中消失。
"""

from __future__ import annotations

from typing import Final


DOMESTIC_FUTURES_MAIN: Final[tuple[dict[str, str], ...]] = (
    # 上海期货交易所
    {"symbol": "FU0", "market": "futures", "name": "燃料油主连", "exchange": "SHFE"},
    {"symbol": "AL0", "market": "futures", "name": "沪铝主连", "exchange": "SHFE"},
    {"symbol": "RU0", "market": "futures", "name": "天然橡胶主连", "exchange": "SHFE"},
    {"symbol": "ZN0", "market": "futures", "name": "沪锌主连", "exchange": "SHFE"},
    {"symbol": "CU0", "market": "futures", "name": "沪铜主连", "exchange": "SHFE"},
    {"symbol": "AU0", "market": "futures", "name": "黄金主连", "exchange": "SHFE"},
    {"symbol": "RB0", "market": "futures", "name": "螺纹钢主连", "exchange": "SHFE"},
    {"symbol": "WR0", "market": "futures", "name": "线材主连", "exchange": "SHFE"},
    {"symbol": "PB0", "market": "futures", "name": "沪铅主连", "exchange": "SHFE"},
    {"symbol": "AG0", "market": "futures", "name": "白银主连", "exchange": "SHFE"},
    {"symbol": "BU0", "market": "futures", "name": "沥青主连", "exchange": "SHFE"},
    {"symbol": "HC0", "market": "futures", "name": "热轧卷板主连", "exchange": "SHFE"},
    {"symbol": "SN0", "market": "futures", "name": "沪锡主连", "exchange": "SHFE"},
    {"symbol": "NI0", "market": "futures", "name": "沪镍主连", "exchange": "SHFE"},
    {"symbol": "SP0", "market": "futures", "name": "纸浆主连", "exchange": "SHFE"},
    {"symbol": "SS0", "market": "futures", "name": "不锈钢主连", "exchange": "SHFE"},
    {"symbol": "AO0", "market": "futures", "name": "氧化铝主连", "exchange": "SHFE"},
    {"symbol": "BR0", "market": "futures", "name": "丁二烯橡胶主连", "exchange": "SHFE"},
    {"symbol": "AD0", "market": "futures", "name": "铸造铝合金主连", "exchange": "SHFE"},
    {"symbol": "OP0", "market": "futures", "name": "胶版印刷纸主连", "exchange": "SHFE"},
    # 上海国际能源交易中心
    {"symbol": "SC0", "market": "futures", "name": "原油主连", "exchange": "INE"},
    {"symbol": "NR0", "market": "futures", "name": "20号胶主连", "exchange": "INE"},
    {"symbol": "LU0", "market": "futures", "name": "低硫燃料油主连", "exchange": "INE"},
    {"symbol": "BC0", "market": "futures", "name": "国际铜主连", "exchange": "INE"},
    {"symbol": "EC0", "market": "futures", "name": "集运指数（欧线）主连", "exchange": "INE"},
    # 大连商品交易所
    {"symbol": "V0", "market": "futures", "name": "PVC主连", "exchange": "DCE"},
    {"symbol": "P0", "market": "futures", "name": "棕榈油主连", "exchange": "DCE"},
    {"symbol": "B0", "market": "futures", "name": "豆二主连", "exchange": "DCE"},
    {"symbol": "M0", "market": "futures", "name": "豆粕主连", "exchange": "DCE"},
    {"symbol": "I0", "market": "futures", "name": "铁矿石主连", "exchange": "DCE"},
    {"symbol": "JD0", "market": "futures", "name": "鸡蛋主连", "exchange": "DCE"},
    {"symbol": "L0", "market": "futures", "name": "塑料主连", "exchange": "DCE"},
    {"symbol": "PP0", "market": "futures", "name": "聚丙烯主连", "exchange": "DCE"},
    {"symbol": "FB0", "market": "futures", "name": "纤维板主连", "exchange": "DCE"},
    {"symbol": "BB0", "market": "futures", "name": "胶合板主连", "exchange": "DCE"},
    {"symbol": "Y0", "market": "futures", "name": "豆油主连", "exchange": "DCE"},
    {"symbol": "C0", "market": "futures", "name": "玉米主连", "exchange": "DCE"},
    {"symbol": "A0", "market": "futures", "name": "豆一主连", "exchange": "DCE"},
    {"symbol": "J0", "market": "futures", "name": "焦炭主连", "exchange": "DCE"},
    {"symbol": "JM0", "market": "futures", "name": "焦煤主连", "exchange": "DCE"},
    {"symbol": "CS0", "market": "futures", "name": "玉米淀粉主连", "exchange": "DCE"},
    {"symbol": "EG0", "market": "futures", "name": "乙二醇主连", "exchange": "DCE"},
    {"symbol": "RR0", "market": "futures", "name": "粳米主连", "exchange": "DCE"},
    {"symbol": "EB0", "market": "futures", "name": "苯乙烯主连", "exchange": "DCE"},
    {"symbol": "PG0", "market": "futures", "name": "液化石油气主连", "exchange": "DCE"},
    {"symbol": "LH0", "market": "futures", "name": "生猪主连", "exchange": "DCE"},
    {"symbol": "LG0", "market": "futures", "name": "原木主连", "exchange": "DCE"},
    {"symbol": "BZ0", "market": "futures", "name": "纯苯主连", "exchange": "DCE"},
    # 郑州商品交易所
    {"symbol": "TA0", "market": "futures", "name": "PTA主连", "exchange": "CZCE"},
    {"symbol": "OI0", "market": "futures", "name": "菜籽油主连", "exchange": "CZCE"},
    {"symbol": "RS0", "market": "futures", "name": "油菜籽主连", "exchange": "CZCE"},
    {"symbol": "RM0", "market": "futures", "name": "菜籽粕主连", "exchange": "CZCE"},
    {"symbol": "ZC0", "market": "futures", "name": "动力煤主连", "exchange": "CZCE"},
    {"symbol": "WH0", "market": "futures", "name": "强麦主连", "exchange": "CZCE"},
    {"symbol": "JR0", "market": "futures", "name": "粳稻主连", "exchange": "CZCE"},
    {"symbol": "SR0", "market": "futures", "name": "白糖主连", "exchange": "CZCE"},
    {"symbol": "CF0", "market": "futures", "name": "棉花主连", "exchange": "CZCE"},
    {"symbol": "RI0", "market": "futures", "name": "早籼稻主连", "exchange": "CZCE"},
    {"symbol": "MA0", "market": "futures", "name": "甲醇主连", "exchange": "CZCE"},
    {"symbol": "FG0", "market": "futures", "name": "玻璃主连", "exchange": "CZCE"},
    {"symbol": "LR0", "market": "futures", "name": "晚籼稻主连", "exchange": "CZCE"},
    {"symbol": "SF0", "market": "futures", "name": "硅铁主连", "exchange": "CZCE"},
    {"symbol": "SM0", "market": "futures", "name": "锰硅主连", "exchange": "CZCE"},
    {"symbol": "CY0", "market": "futures", "name": "棉纱主连", "exchange": "CZCE"},
    {"symbol": "AP0", "market": "futures", "name": "苹果主连", "exchange": "CZCE"},
    {"symbol": "CJ0", "market": "futures", "name": "红枣主连", "exchange": "CZCE"},
    {"symbol": "UR0", "market": "futures", "name": "尿素主连", "exchange": "CZCE"},
    {"symbol": "SA0", "market": "futures", "name": "纯碱主连", "exchange": "CZCE"},
    {"symbol": "PF0", "market": "futures", "name": "短纤主连", "exchange": "CZCE"},
    {"symbol": "PK0", "market": "futures", "name": "花生主连", "exchange": "CZCE"},
    {"symbol": "SH0", "market": "futures", "name": "烧碱主连", "exchange": "CZCE"},
    {"symbol": "PX0", "market": "futures", "name": "对二甲苯主连", "exchange": "CZCE"},
    {"symbol": "PR0", "market": "futures", "name": "瓶片主连", "exchange": "CZCE"},
    {"symbol": "PL0", "market": "futures", "name": "丙烯主连", "exchange": "CZCE"},
    # 广州期货交易所
    {"symbol": "SI0", "market": "futures", "name": "工业硅主连", "exchange": "GFEX"},
    {"symbol": "LC0", "market": "futures", "name": "碳酸锂主连", "exchange": "GFEX"},
    {"symbol": "PS0", "market": "futures", "name": "多晶硅主连", "exchange": "GFEX"},
    {"symbol": "PT0", "market": "futures", "name": "铂主连", "exchange": "GFEX"},
    {"symbol": "PD0", "market": "futures", "name": "钯主连", "exchange": "GFEX"},
    # 中国金融期货交易所
    {"symbol": "IF0", "market": "futures", "name": "沪深300股指主连", "exchange": "CFFEX"},
    {"symbol": "IH0", "market": "futures", "name": "上证50股指主连", "exchange": "CFFEX"},
    {"symbol": "IC0", "market": "futures", "name": "中证500股指主连", "exchange": "CFFEX"},
    {"symbol": "IM0", "market": "futures", "name": "中证1000股指主连", "exchange": "CFFEX"},
    {"symbol": "TS0", "market": "futures", "name": "2年期国债主连", "exchange": "CFFEX"},
    {"symbol": "TF0", "market": "futures", "name": "5年期国债主连", "exchange": "CFFEX"},
    {"symbol": "T0", "market": "futures", "name": "10年期国债主连", "exchange": "CFFEX"},
    {"symbol": "TL0", "market": "futures", "name": "30年期国债主连", "exchange": "CFFEX"},
)


FUTURES_NAME_BY_SYMBOL: Final[dict[str, str]] = {
    item["symbol"]: item["name"] for item in DOMESTIC_FUTURES_MAIN
}

FUTURES_EXCHANGE_BY_PRODUCT: Final[dict[str, str]] = {
    "".join(character for character in item["symbol"].upper() if character.isalpha()): item[
        "exchange"
    ]
    for item in DOMESTIC_FUTURES_MAIN
}


def domestic_futures_records() -> list[dict[str, str]]:
    """返回可安全修改的目录副本。"""

    return [dict(item) for item in DOMESTIC_FUTURES_MAIN]
