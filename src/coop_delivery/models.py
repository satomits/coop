"""データモデル"""
from dataclasses import dataclass, field


@dataclass
class OrderItem:
    name: str
    quantity: int = 1
    price: int = 0
    category: str = ""


@dataclass
class DeliveryOrder:
    delivery_date: str
    items: list[OrderItem] = field(default_factory=list)
    total: int = 0
    error: str | None = None
