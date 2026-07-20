from app.strategies.base import Strategy

_REGISTRY: dict[str, type[Strategy]] = {}


def register(strategy_cls: type[Strategy]):
    _REGISTRY[strategy_cls.strategy_id] = strategy_cls
    return strategy_cls


def get_strategy_class(strategy_id: str) -> type[Strategy]:
    if strategy_id not in _REGISTRY:
        raise KeyError(f"策略未注册: {strategy_id}")
    return _REGISTRY[strategy_id]


def list_strategies() -> list[type[Strategy]]:
    return list(_REGISTRY.values())


def import_samples() -> None:
    """导入示例策略以完成注册。"""
    from app.strategies.samples import ma_cross  # noqa: F401
