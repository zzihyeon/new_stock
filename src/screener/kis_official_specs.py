"""
KIS endpoint/TR specs aligned with Korea Investment official open-trading-api examples.

Reference:
- examples_llm/domestic_stock/inquire_price/inquire_price.py
- examples_llm/domestic_stock/inquire_daily_price/inquire_daily_price.py
"""

INQUIRE_PRICE_API_URL = "/uapi/domestic-stock/v1/quotations/inquire-price"
INQUIRE_PRICE_TR_ID = "FHKST01010100"

INQUIRE_DAILY_PRICE_API_URL = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
INQUIRE_DAILY_PRICE_TR_ID = "FHKST01010400"

INQUIRE_DAILY_ITEMCHART_API_URL = (
    "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
)
INQUIRE_DAILY_ITEMCHART_TR_ID = "FHKST03010100"
