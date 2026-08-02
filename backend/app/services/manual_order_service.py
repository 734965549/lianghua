import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.repositories.signal_repo import SignalRepository
from app.schemas.enums import Market, OrderSide, PriceType, SignalAction
from app.schemas.error_codes import ErrorCode
from app.sdk.models import PlaceOrderRequest
from app.services.order_service import order_service
from app.services.risk_service import RiskService

logger = logging.getLogger(__name__)

MANUAL_STRATEGY_ID = "manual"
ZERO_ACCOUNT_ID = UUID(int=0)


class ManualOrderService:
    """人工下单服务：直接创建信号并走风控/订单流程。"""

    def create_order(
        self,
        db: Session,
        *,
        symbol: str,
        market: Market,
        side: OrderSide,
        action: SignalAction,
        price_type: PriceType,
        quantity: Decimal,
        price: Decimal | None = None,
        reason: str = "人工下单",
        correlation_id: str = "",
    ) -> dict:
        signal_id = uuid4()
        signal_time = datetime.now(timezone.utc)
        client_order_id = f"lh_manual_{signal_time:%Y%m%d}_{signal_id.hex[:8]}"

        sig = SignalRepository(db).add_signal(
            signal_id=signal_id,
            strategy_id=MANUAL_STRATEGY_ID,
            symbol=symbol,
            market=market,
            side=side,
            action=action,
            price_type=price_type,
            price=Decimal(str(price)) if price is not None else Decimal("0"),
            quantity=Decimal(str(quantity)),
            reason=reason,
            signal_time=signal_time,
            metadata={"source": "manual"},
        )
        db.flush()

        request = PlaceOrderRequest(
            client_order_id=client_order_id,
            account_id=ZERO_ACCOUNT_ID,
            market=market,
            symbol=symbol,
            side=side,
            action=action,
            price_type=price_type,
            price=Decimal(str(price)) if price is not None else None,
            quantity=Decimal(str(quantity)),
            metadata={"strategy_id": MANUAL_STRATEGY_ID, "source": "manual"},
        )

        risk = RiskService(db, correlation_id=correlation_id)
        passed, results, check_id = risk.check(request, signal_id=sig.signal_id, exclude_signal_id=sig.signal_id)
        db.commit()

        if not passed:
            hit = next((r for r in results if r.result == "rejected"), None)
            raise BizError(
                ErrorCode.RISK_CHECK_NOT_PASSED,
                f"风控未通过: {hit.reason if hit else 'unknown'}",
                status=400,
            )

        order = order_service.create_from_signal(
            db, sig, request, check_id=check_id, correlation_id=correlation_id
        )
        from app.services.order_service import order_to_dict

        return order_to_dict(order)


manual_order_service = ManualOrderService()
