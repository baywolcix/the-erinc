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
    # Uzun istem kademesi: toplam giriş token'ı bu eşiği aşarsa `long` fiyatı uygulanır
    long_threshold: int | None = None
    long: "Price | None" = None

    def for_prompt(self, prompt_tokens: int) -> "Price":
        if self.long is not None and self.long_threshold is not None and prompt_tokens > self.long_threshold:
            return self.long
        return self

    @property
    def worst(self) -> "Price":
        return self.long or self


ANTHROPIC_PRICES: dict[str, Price] = {
    # Haiku 5.5: 100K token altı istemler için; üstünde $0.50/$2.50
    "claude-haiku-5-5": Price(0.10, 0.50, long_threshold=100_000, long=Price(0.50, 2.50)),
    "claude-sonnet-5-5": Price(2.00, 10.00, cache_read=0.10),
    "claude-opus-5-5": Price(4.00, 20.00, cache_read=0.20),
    # Sunucu tarafı reddetme yedeğinde kullanılan modeller (bkz. providers.REFUSAL_FALLBACK)
    "claude-sonnet-5": Price(2.00, 10.00),
    "claude-opus-4-8": Price(5.00, 25.00),
}


def cost_usd(price: Price | None, input_tokens: int, output_tokens: int,
             cache_read: int = 0, cache_write: int = 0) -> float | None:
    if price is None:
        return None
    price = price.for_prompt(input_tokens + cache_read + cache_write)
    cr = price.cache_read if price.cache_read is not None else price.input * 0.1
    cw = price.cache_write if price.cache_write is not None else price.input * 1.25
    return (input_tokens * price.input + output_tokens * price.output
            + cache_read * cr + cache_write * cw) / 1_000_000


def worst_case_usd(price: Price, prompt_tokens: int, max_output: int) -> float:
    """Bütçe ön kontrolü için üst sınır: tüm giriş önbelleğe yazma (1.25x) fiyatından, uzun istem kademesi."""
    p = price.worst if price.long_threshold is not None and prompt_tokens > price.long_threshold else price
    cw = p.cache_write if p.cache_write is not None else p.input * 1.25
    return (prompt_tokens * max(p.input, cw) + max_output * p.output) / 1_000_000
