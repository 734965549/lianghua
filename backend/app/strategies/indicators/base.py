from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from typing import Any

from app.sdk.models import KlineBar

OHLCV_FIELDS = {"open", "high", "low", "close", "volume"}


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _safe_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        d = _to_decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not d.is_finite():
        return None
    return d


class Indicator(ABC):
    """增量指标基类。回测与实时模拟共用同一实现。"""

    output_names: tuple[str, ...] = ("value",)

    def __init__(self, *, period: int | None = None, source: str = "close"):
        if period is not None and (period < 1 or period > 500):
            raise ValueError(f"指标周期无效: {period}")
        if source not in OHLCV_FIELDS:
            raise ValueError(f"不支持的数据源: {source}")
        self.period = period
        self.source = source
        self._ready = False
        self._value: Decimal | None = None
        self._prev_value: Decimal | None = None
        self._outputs: dict[str, Decimal | None] = {}
        self._prev_outputs: dict[str, Decimal | None] = {}

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def value(self) -> Decimal | None:
        return self.get_output("value")

    @property
    def prev_value(self) -> Decimal | None:
        return self.get_prev_output("value")

    @property
    def warmup_bars(self) -> int:
        return self.period or 1

    def get_output(self, name: str = "value") -> Decimal | None:
        if name == "value":
            return self._value
        return self._outputs.get(name)

    def get_prev_output(self, name: str = "value") -> Decimal | None:
        if name == "value":
            return self._prev_value
        return self._prev_outputs.get(name)

    def _set_outputs(self, outputs: dict[str, Decimal | None]) -> None:
        cleaned: dict[str, Decimal | None] = {}
        for key, val in outputs.items():
            if val is not None and not val.is_finite():
                val = None
            cleaned[key] = val

        self._prev_outputs = dict(self._outputs)
        self._outputs = cleaned

        primary = cleaned.get("value")
        if primary is None and len(cleaned) == 1:
            primary = next(iter(cleaned.values()))
        self._prev_value = self._value
        self._value = primary
        self._ready = primary is not None or any(v is not None for v in cleaned.values())

    def _set_value(self, new_value: Decimal | None) -> None:
        self._set_outputs({"value": new_value})

    def _bar_field(self, bar: KlineBar) -> Decimal:
        return _to_decimal(getattr(bar, self.source))

    @abstractmethod
    def update(self, bar: KlineBar) -> None: ...


class IndicatorRegistry:
    _registry: dict[str, type[Indicator]] = {}
    _catalog_meta: dict[str, dict[str, Any]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        indicator_cls: type[Indicator],
        *,
        catalog: dict[str, Any] | None = None,
    ) -> type[Indicator]:
        cls._registry[name] = indicator_cls
        if catalog:
            cls._catalog_meta[name] = catalog
        return indicator_cls

    @classmethod
    def get(cls, name: str) -> type[Indicator]:
        if name not in cls._registry:
            raise KeyError(f"未知指标类型: {name}")
        return cls._registry[name]

    @classmethod
    def catalog(cls) -> list[dict[str, Any]]:
        items = []
        for name, meta in cls._catalog_meta.items():
            items.append({"type": name, **meta})
        return items


def resolve_spec_value(spec: Any, parameters: dict) -> Any:
    if isinstance(spec, dict) and "parameter" in spec:
        return parameters.get(spec["parameter"])
    return spec


def create_indicator_from_def(ind_def: dict, parameters: dict) -> Indicator:
    ind_type = ind_def["type"]
    cls = IndicatorRegistry.get(ind_type)
    source = ind_def.get("source", "close")

    period = None
    if "period" in ind_def:
        period_spec = ind_def["period"]
        if isinstance(period_spec, int):
            period = period_spec
        elif isinstance(period_spec, dict) and "parameter" in period_spec:
            period = int(parameters[period_spec["parameter"]])

    params: dict[str, Any] = {}
    for key, spec in ind_def.get("params", {}).items():
        val = resolve_spec_value(spec, parameters)
        if val is not None:
            params[key] = val

    return cls(period=period, source=source, **params)


def create_indicator(indicator_type: str, *, period: int, source: str = "close", **kwargs) -> Indicator:
    cls = IndicatorRegistry.get(indicator_type)
    return cls(period=period, source=source, **kwargs)
