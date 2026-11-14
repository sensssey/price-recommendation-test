"""Тесты recommend_price. Запуск из папки с файлами: python -m unittest -v"""

import asyncio
import unittest
from decimal import Decimal

from starter import recommend_price, sample_fetch_offers


def offer(seller, price, days):
    return {"seller": seller, "price": Decimal(price), "delivery_days": days}


def source(*offers, status="success"):
    async def fetch_offers():
        return {"status": status, "offers": list(offers)}

    return fetch_offers


async def recommend(fetch_offers, current="1000.00", minimum="100.00", **kwargs):
    return await recommend_price(
        fetch_offers,
        current_price=Decimal(current),
        min_price=Decimal(minimum),
        **kwargs,
    )


class NormalCalculation(unittest.IsolatedAsyncioTestCase):
    async def test_example_from_task(self):
        result = await recommend(sample_fetch_offers, current="4900.00", minimum="4500.00")
        self.assertEqual(result["price"], Decimal("4728.00"))
        self.assertIsInstance(result["price"], Decimal)
        self.assertEqual(result["decision"], "APPLY")
        self.assertTrue(result["reason"])

    async def test_rounds_down_to_kopeck(self):
        # 100.01 * 0.985 = 98.50985, обычное округление дало бы 98.51
        fetch = source(offer("PARTS", "100.01", 1))
        result = await recommend(fetch, current="100.00", minimum="50.00")
        self.assertEqual(result["price"], Decimal("98.50"))

    async def test_min_price_is_a_floor(self):
        fetch = source(offer("PARTS", "900.00", 1))
        result = await recommend(fetch, current="1000.00", minimum="950.00")
        self.assertEqual((result["price"], result["decision"]), (Decimal("950.00"), "APPLY"))


class SourceFailures(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_holds_current_price(self):
        async def slow():
            await asyncio.sleep(30)

        result = await recommend(slow, timeout_s=0.01)
        self.assertEqual((result["price"], result["decision"]), (Decimal("1000.00"), "HOLD"))

    async def test_exception_holds_current_price(self):
        async def broken():
            raise ConnectionError("площадка недоступна")

        result = await recommend(broken)
        self.assertEqual((result["price"], result["decision"]), (Decimal("1000.00"), "HOLD"))

    async def test_non_success_status_holds_even_with_good_offers(self):
        for status in ("partial", "error"):
            with self.subTest(status=status):
                result = await recommend(source(offer("PARTS", "900.00", 1), status=status))
                self.assertEqual(result["price"], Decimal("1000.00"))
                self.assertEqual(result["decision"], "HOLD")


class Filtering(unittest.IsolatedAsyncioTestCase):
    async def test_no_eligible_offers_holds_even_below_min_price(self):
        fetch = source(
            offer("MyShop", "500.00", 1),
            offer("NODATE", "600.00", None),
            offer("SLOW", "700.00", 7),
        )
        result = await recommend(fetch, current="1000.00", minimum="2000.00")
        self.assertEqual((result["price"], result["decision"]), (Decimal("1000.00"), "HOLD"))

    async def test_delivery_boundary_six_days_is_eligible(self):
        result = await recommend(source(offer("PARTS", "1000.00", 6), offer("FAST", "1100.00", 0)))
        self.assertEqual(result["price"], Decimal("985.00"))


class ReviewThreshold(unittest.IsolatedAsyncioTestCase):
    async def test_exactly_30_percent_is_applied(self):
        # 1319.80 * 0.985 = 1300.003, после округления вниз ровно +30%
        up = await recommend(source(offer("PARTS", "1319.80", 1)))
        down = await recommend(source(offer("PARTS", "500.00", 1)), minimum="700.00")
        self.assertEqual((up["price"], up["decision"]), (Decimal("1300.00"), "APPLY"))
        self.assertEqual((down["price"], down["decision"]), (Decimal("700.00"), "APPLY"))

    async def test_one_kopeck_over_30_percent_goes_to_review(self):
        up = await recommend(source(offer("PARTS", "1319.81", 1)))
        down = await recommend(source(offer("PARTS", "500.00", 1)), minimum="699.99")
        self.assertEqual((up["price"], up["decision"]), (Decimal("1300.01"), "REVIEW"))
        self.assertEqual((down["price"], down["decision"]), (Decimal("699.99"), "REVIEW"))


if __name__ == "__main__":
    unittest.main()
