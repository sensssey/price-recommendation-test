"""
ПРАВИЛА В ПОРЯДКЕ ПРИМЕНЕНИЯ
1. Ограничьте ожидание fetch_offers значением timeout_s. При ошибке источника,
   тайм-ауте или status != success верните текущую цену и HOLD.
2. Учитывайте предложения с известной доставкой не более 6 дней.
   Исключайте собственный магазин MYSHOP независимо от регистра букв.
3. Если подходящих предложений нет, верните текущую цену и HOLD,
   даже если текущая цена ниже min_price.
4. Минимальную цену подходящего конкурента уменьшите на 1,5% и округлите
   вниз до копейки. Рекомендация — максимум из этой суммы и min_price.
5. Если рекомендация отличается от текущей цены более чем на 30% в любую
   сторону, верните рекомендацию и REVIEW. Иначе — рекомендацию и APPLY.
   Ровно 30% допускается. REVIEW означает, что автоматическое применение
   запрещено до ручной проверки.

"""

import asyncio
from decimal import ROUND_DOWN, Decimal

OWN_SELLER = "myshop"
MAX_DELIVERY_DAYS = 6
UNDERCUT_FACTOR = Decimal("0.985")
REVIEW_SHARE = Decimal("0.30")
KOPECK = Decimal("0.01")


def _hold(current_price, reason):
    return {"price": current_price, "decision": "HOLD", "reason": reason}


def _is_eligible(offer):
    days = offer["delivery_days"]
    return (
        days is not None
        and days <= MAX_DELIVERY_DAYS
        and offer["seller"].casefold() != OWN_SELLER
    )


async def recommend_price(fetch_offers, current_price, min_price, timeout_s=2.0):
    # Любой сбой источника оставляет цену как есть. Отмена задачи проходит наружу.
    try:
        result = await asyncio.wait_for(fetch_offers(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return _hold(current_price, f"Источник не ответил за {timeout_s:g} с")
    except Exception as exc:
        return _hold(current_price, f"Ошибка источника: {type(exc).__name__}")

    status = result.get("status")
    if status != "success":
        return _hold(current_price, f"Статус источника: {status}")

    prices = [offer["price"] for offer in result["offers"] if _is_eligible(offer)]
    if not prices:
        return _hold(current_price, "Нет подходящих предложений конкурентов")

    undercut = (min(prices) * UNDERCUT_FACTOR).quantize(KOPECK, rounding=ROUND_DOWN)
    price = max(undercut, min_price)
    if price == undercut:
        reason = "Минимальная цена конкурента минус 1,5%"
    else:
        reason = "Цена конкурента ниже допустимой, взята минимальная цена"

    # Умножение вместо деления, чтобы граница ровно в 30% считалась точно.
    if abs(price - current_price) > current_price * REVIEW_SHARE:
        return {
            "price": price,
            "decision": "REVIEW",
            "reason": f"{reason}. Отклонение от текущей цены больше 30%, нужна ручная проверка",
        }
    return {"price": price, "decision": "APPLY", "reason": reason}


async def sample_fetch_offers():
    return {
        "status": "success",
        "offers": [
            {"seller": "myshop", "price": Decimal("4300.00"), "delivery_days": 2},
            {"seller": "PARTS", "price": Decimal("4800.00"), "delivery_days": 3},
            {"seller": "SLOW", "price": Decimal("4700.00"), "delivery_days": 8},
        ],
    }


if __name__ == "__main__":
    print(asyncio.run(recommend_price(
        sample_fetch_offers,
        current_price=Decimal("4900.00"),
        min_price=Decimal("4500.00"),
    )))
