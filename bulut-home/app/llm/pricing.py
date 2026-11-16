"""Model fiyatları (USD / 1M token).

UYARI: Bu tablo canlı doğrulanmış değildir. Anthropic değerleri 2026-11-03 tarihli
önbellekli listeden alınmıştır. Faturalandırma kararları için sağlayıcının güncel
fiyat sayfasını kontrol et. Tabloda olmayan model için maliyet "bilinmiyor" sayılır.
"""
from __future__ import annotations

from dataclasses import dataclass

PRICES_AS_OF = "2026-11-03"


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float | None = None   # None => input * 0.1
    cache_write: float | None = None  # None => input * 1.25


ANTHROPIC_PRICES: dict[str, Price] = {
    # Haiku 5.5: 100K token altı istemler için; üstünde $0.50/$2.50
    "claude-haiku-5-5": Price(0.10, 0.50),
    "claude-sonnet-5-5": Price(2.00, 10.00, cache_read=0.10),
    "claude-opus-5-5": Price(4.00, 20.00, cache_read=0.20),
}


def cost_usd(price: Price | None, input_tokens: int, output_tokens: int,
             cache_read: int = 0, cache_write: int = 0) -> float | None:
    if price is None:
        return None
    cr = price.cache_read if price.cache_read is not None else price.input * 0.1
    cw = price.cache_write if price.cache_write is not None else price.input * 1.25
    return (input_tokens * price.input + output_tokens * price.output
            + cache_read * cr + cache_write * cw) / 1_000_000
