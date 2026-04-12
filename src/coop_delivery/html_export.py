"""モバイルフレンドリーなHTML出力モジュール"""
from datetime import datetime, timezone, timedelta
from html import escape

from .models import DeliveryOrder

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, 'Hiragino Sans', 'Yu Gothic', sans-serif;
    font-size: 15px;
    color: #222;
    background: #f4f4f8;
    padding: 12px;
    max-width: 640px;
    margin: 0 auto;
}

h1 {
    font-size: 18px;
    font-weight: bold;
    margin-bottom: 4px;
    color: #1a1a2e;
}

.updated {
    font-size: 12px;
    color: #888;
    margin-bottom: 14px;
}

.order {
    background: #fff;
    border-radius: 12px;
    margin-bottom: 14px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}

.order-header {
    padding: 10px 14px;
    font-weight: bold;
    font-size: 14px;
    background: #1a1a2e;
    color: #fff;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.order-header .summary {
    font-size: 12px;
    font-weight: normal;
    opacity: 0.8;
}

.order-error {
    padding: 10px 14px;
    color: #c0392b;
    font-size: 13px;
    background: #fff5f5;
}

.item {
    padding: 10px 14px;
    border-top: 1px solid #f0f0f0;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px;
}

.item-name {
    font-size: 14px;
    line-height: 1.4;
    flex: 1;
}

.item-detail {
    font-size: 13px;
    color: #555;
    white-space: nowrap;
    text-align: right;
}

.total-row {
    padding: 10px 14px;
    border-top: 2px solid #1a1a2e;
    display: flex;
    justify-content: space-between;
    font-weight: bold;
    font-size: 15px;
}

.no-items {
    padding: 10px 14px;
    font-size: 13px;
    color: #aaa;
    border-top: 1px solid #f0f0f0;
}
"""


def _format_price(price: int) -> str:
    return f"¥{price:,}"


def generate_html(order: DeliveryOrder) -> str:
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST).strftime("%Y/%m/%d %H:%M 更新")

    item_count = len(order.items)
    summary = f"{item_count}品 / {_format_price(order.total)}"

    parts = [
        '<div class="order">',
        f'<div class="order-header">'
        f'{escape(order.delivery_date)}'
        f'<span class="summary">{summary}</span>'
        f'</div>',
    ]

    if order.error:
        parts.append(f'<div class="order-error">⚠ {escape(order.error)}</div>')
    elif order.items:
        for item in order.items:
            qty_str = f" x{item.quantity}" if item.quantity > 1 else ""
            price_str = _format_price(item.price * item.quantity) if item.price else ""
            detail = f"{qty_str} {price_str}".strip()
            parts.append(
                f'<div class="item">'
                f'<div class="item-name">{escape(item.name)}</div>'
                f'<div class="item-detail">{escape(detail)}</div>'
                f'</div>'
            )
        parts.append(
            f'<div class="total-row">'
            f'<span>合計</span>'
            f'<span>{_format_price(order.total)}</span>'
            f'</div>'
        )
    else:
        parts.append('<div class="no-items">注文品なし</div>')

    parts.append('</div>')
    body = "\n".join(parts)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>おうちコープ 注文一覧</title>
<style>{_CSS}</style>
</head>
<body>
<h1>おうちコープ 注文一覧</h1>
<p class="updated">{now}</p>
{body}
</body>
</html>"""
