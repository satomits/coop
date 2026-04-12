"""eふれんず Playwright スクレイパー"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.async_api import async_playwright, Page

from .models import OrderItem, DeliveryOrder

LOGIN_URL = "https://ouchi.ef.cws.coop/ec/bb/ecTopInit.do"
ORDER_HISTORY_URL = "https://ouchi.ef.cws.coop/ec/bb/orderHistoryInit.do?sid=ComEcF00BB010&tcd=tcdcp003"
JST = timezone(timedelta(hours=9))


async def scrape_orders(
    email: str,
    password: str,
    *,
    debug: bool = False,
    debug_dir: Path | None = None,
) -> DeliveryOrder:
    """eふれんずにログインし、次回配達の注文品一覧を取得する。"""
    if debug and debug_dir is None:
        debug_dir = Path("debug")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.set_default_timeout(30000)

        try:
            return await _do_scrape(page, email, password, debug, debug_dir)
        finally:
            await browser.close()


async def _save_debug(page: Page, debug_dir: Path, name: str) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(debug_dir / f"{name}.png"), full_page=True)
    html = await page.content()
    (debug_dir / f"{name}.html").write_text(html, encoding="utf-8")
    print(f"  debug: {name} saved (url={page.url})")


def _parse_date_text(text: str) -> datetime | None:
    """'4月20日' のようなテキストから datetime を返す。"""
    m = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    now = datetime.now(JST)
    year = now.year
    if month - now.month > 6:
        year -= 1
    elif now.month - month > 6:
        year += 1
    return datetime(year, month, day, tzinfo=JST)


async def _do_scrape(
    page: Page,
    email: str,
    password: str,
    debug: bool,
    debug_dir: Path | None,
) -> DeliveryOrder:
    # ログイン
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    if debug and debug_dir:
        await _save_debug(page, debug_dir, "01_login_page")

    await page.fill('input#username', email)
    await page.fill('input[name="j_password"][type="password"]', password)
    await page.click('input[type="submit"]')
    await page.wait_for_load_state("domcontentloaded")

    if debug and debug_dir:
        await _save_debug(page, debug_dir, "02_after_login")

    today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)

    # 注文履歴ページへ遷移
    await page.goto(ORDER_HISTORY_URL, wait_until="domcontentloaded")

    if debug and debug_dir:
        await _save_debug(page, debug_dir, "03_order_history")

    # 企画週セレクタから全週を取得し、今日以降で直近のお届け日の週を選択
    best_week = await _find_nearest_week(page, today, debug, debug_dir)

    if best_week is not None:
        current = await page.eval_on_selector('select[name="history"]', "el => el.value")
        if current != best_week:
            await page.select_option('select[name="history"]', best_week)
            # 「表示」ボタンをクリックしてリロード
            await page.click('input.button.reload')
            await page.wait_for_load_state("domcontentloaded")

            if debug and debug_dir:
                await _save_debug(page, debug_dir, "04_selected_week")

    # 注文データをパース
    return await _parse_history_page(page, debug, debug_dir)


async def _find_nearest_week(
    page: Page,
    today: datetime,
    debug: bool,
    debug_dir: Path | None,
) -> str | None:
    """企画週セレクタの各週を評価し、今日以降で直近のお届け日の週の value を返す。

    注文履歴ページにはお届け日が表示されるが、企画週を切り替えないと
    各週のお届け日はわからない。そのため各週を順に選択してお届け日を確認する。
    ただし、デフォルトで表示されている週（最新の締め切り済み週）のお届け日が
    今日以降ならそれを使う。
    """
    # デフォルト表示のお届け日を確認
    delivery_el = await page.query_selector(".delivery")
    if delivery_el:
        delivery_text = (await delivery_el.inner_text()).strip()
        delivery_dt = _parse_date_text(delivery_text)
        if debug:
            print(f"  default delivery: {delivery_text} -> {delivery_dt}")
        if delivery_dt and delivery_dt >= today:
            # デフォルトの週が今日以降 → そのまま使う
            current = await page.eval_on_selector('select[name="history"]', "el => el.value")
            return current

    # デフォルトが過去の場合、各週を試す
    options = await page.eval_on_selector_all(
        'select[name="history"] option',
        "els => els.map(el => ({value: el.value, text: el.textContent.trim()}))",
    )

    if debug:
        print(f"  week options: {options}")

    best: tuple[datetime, str] | None = None

    for opt in options:
        value = opt["value"]
        text = opt["text"]

        # 週を選択してお届け日を確認
        await page.select_option('select[name="history"]', value)
        await page.click('input.button.reload')
        await page.wait_for_load_state("domcontentloaded")

        delivery_el = await page.query_selector(".delivery")
        if not delivery_el:
            continue
        delivery_text = (await delivery_el.inner_text()).strip()
        delivery_dt = _parse_date_text(delivery_text)

        if debug:
            print(f"  {text} ({value}): {delivery_text} -> {delivery_dt}")

        if delivery_dt and delivery_dt >= today:
            if best is None or delivery_dt < best[0]:
                best = (delivery_dt, value)

    if best:
        return best[1]
    # 全て過去 → 最も新しい週（デフォルト）
    return None


async def _parse_history_page(
    page: Page,
    debug: bool,
    debug_dir: Path | None,
) -> DeliveryOrder:
    """注文履歴ページから注文データをパースする。"""
    # お届け日
    delivery_date = ""
    delivery_el = await page.query_selector(".delivery")
    if delivery_el:
        delivery_date = (await delivery_el.inner_text()).strip()
        # "お届け日：4月13日" → "4月13日"
        delivery_date = delivery_date.replace("お届け日：", "").strip()

    # 企画週名
    week_name = ""
    selected = await page.query_selector('select[name="history"] option[selected]')
    if selected:
        week_name = (await selected.inner_text()).strip()

    # 商品行をパース: table.standard 内の tr（ヘッダ行を除く）
    items: list[OrderItem] = []
    rows = await page.query_selector_all("table.standard tbody tr")
    for row in rows:
        # ヘッダ行はスキップ
        th = await row.query_selector("th")
        if th:
            continue

        # 商品名: .name_clm
        name_el = await row.query_selector(".name_clm")
        if not name_el:
            continue
        name = (await name_el.inner_text()).strip()
        if not name:
            continue

        # 単価: .price_clm
        price = 0
        price_el = await row.query_selector(".price_clm")
        if price_el:
            price_text = (await price_el.inner_text()).strip()
            digits = "".join(c for c in price_text if c.isdigit())
            if digits:
                price = int(digits)

        # 数量: .quantity_clm
        quantity = 1
        qty_el = await row.query_selector(".quantity_clm")
        if qty_el:
            qty_text = (await qty_el.inner_text()).strip()
            digits = "".join(c for c in qty_text if c.isdigit())
            if digits:
                quantity = int(digits)

        items.append(OrderItem(name=name, quantity=quantity, price=price))

    # 合計金額: 「税込単純合計金額12,720円」から抽出
    total = 0
    amount_rows = await page.query_selector_all("tr.row_amount .total_amount_clm")
    for el in amount_rows:
        text = (await el.inner_text()).strip()
        m = re.search(r"税込単純合計金額([\d,]+)", text)
        if m:
            total = int(m.group(1).replace(",", ""))
            break
    if not total:
        total = sum(item.price * item.quantity for item in items)

    # 表示テキスト
    date_display = ""
    if week_name:
        date_display = week_name
    if delivery_date:
        date_display += f" お届け {delivery_date}"
    if not date_display:
        date_display = "次回配達"

    if debug:
        print(f"  result: date={date_display!r} items={len(items)} total={total}")
        for item in items[:5]:
            print(f"    {item.name} x{item.quantity} ¥{item.price}")
        if len(items) > 5:
            print(f"    ... and {len(items) - 5} more")

    if debug and debug_dir:
        await _save_debug(page, debug_dir, "05_parsed")

    return DeliveryOrder(
        delivery_date=date_display.strip(),
        items=items,
        total=total,
    )
