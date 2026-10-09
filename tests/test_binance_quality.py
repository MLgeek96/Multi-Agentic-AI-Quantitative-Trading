from email.message import Message
import json
import unittest

import pandas as pd

from crypto_quant.binance_public import BinanceAPIError, BinancePublicClient, SimpleResponse


def row(day):
    opened = int(pd.Timestamp(day, tz="UTC").timestamp() * 1000)
    return [opened, "100", "102", "99", "101", "1000", opened + 86_400_000 - 1,
            "101000", 100, "500", "50500", 0]


class PublicClientQualityTests(unittest.TestCase):
    def fetch(self, rows):
        client = BinancePublicClient(opener=lambda *a, **k: SimpleResponse(json.dumps(rows).encode(), Message()))
        return client.fetch_klines("BTCUSDT", start=pd.Timestamp("2024-01-01", tz="UTC"),
                                   end=pd.Timestamp("2024-01-04", tz="UTC"), closed_at=pd.Timestamp("2024-01-04", tz="UTC"))

    def test_duplicate_response_is_not_silently_deduplicated(self):
        with self.assertRaisesRegex(BinanceAPIError, "Duplicate"):
            self.fetch([row("2024-01-01"), row("2024-01-01")])

    def test_unordered_response_is_not_silently_sorted(self):
        with self.assertRaisesRegex(BinanceAPIError, "Unordered"):
            self.fetch([row("2024-01-02"), row("2024-01-01")])

    def test_only_completed_bars_are_returned(self):
        frame = self.fetch([row("2024-01-01"), row("2024-01-04")])
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame["open_time"].iloc[-1], pd.Timestamp("2024-01-01", tz="UTC"))


if __name__ == "__main__":
    unittest.main()
