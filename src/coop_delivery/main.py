"""メインエントリーポイント"""
import sys
from pathlib import Path

import anyio
import yaml

from .models import DeliveryOrder
from .scraper import scrape_orders
from .html_export import generate_html


def load_config(config_path: Path | None = None) -> dict:
    if config_path is None:
        config_path = Path("config.yaml")
    if not config_path.exists():
        print(f"設定ファイルが見つかりません: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


async def main_async(
    config_path: Path | None = None,
    *,
    debug: bool = False,
) -> DeliveryOrder:

    config = load_config(config_path)
    email = config.get("email", "")
    password = config.get("password", "")

    if not email or not password:
        print("config.yaml に email と password を設定してください。", file=sys.stderr)
        sys.exit(1)

    print("eふれんずから注文情報を取得中...")

    try:
        order = await scrape_orders(
            email,
            password,
            debug=debug,
            debug_dir=Path("debug") if debug else None,
        )
    except Exception as e:
        order = DeliveryOrder(
            delivery_date="取得エラー",
            error=str(e) or repr(e),
        )

    if order.error:
        print(f"エラー: {order.error}", file=sys.stderr)
    else:
        print(f"配達日: {order.delivery_date}")
        print(f"注文品: {len(order.items)}品")
        print(f"合計: ¥{order.total:,}")

    return order


def run() -> None:
    """CLIエントリーポイント"""
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    args = sys.argv[1:]
    html_path: Path | None = None
    config_path: Path | None = None
    debug = False

    i = 0
    while i < len(args):
        if args[i] == "--html":
            i += 1
            html_path = Path(args[i] if i < len(args) else "output.html")
        elif args[i] == "--debug":
            debug = True
        elif args[i] == "--config":
            i += 1
            config_path = Path(args[i]) if i < len(args) else None
        else:
            config_path = Path(args[i])
        i += 1

    async def _run() -> DeliveryOrder:
        return await main_async(config_path, debug=debug)

    order = anyio.run(_run)

    if html_path is not None:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(generate_html(order), encoding="utf-8")
        print(f"HTML saved: {html_path}")


if __name__ == "__main__":
    run()
