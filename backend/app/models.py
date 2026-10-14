"""Imports every module's ORM models so Base.metadata is complete (Alembic, create_all)."""

from app.core.db import Base
from app.modules.agent.models import AgentRun, LlmCall
from app.modules.auth.models import User
from app.modules.budget.models import Budget
from app.modules.catalog.models import Node, Product
from app.modules.erp_mock.models import ErpBehaviour, ErpPurchaseOrder, ErpRequest
from app.modules.inventory.models import DemandForecast, InventorySnapshot, SalesHistory
from app.modules.notifications.models import Notification
from app.modules.purchasing.models import PoLine, PurchaseOrder
from app.modules.recommendations.models import Recommendation
from app.modules.storage.models import StorageZone
from app.modules.suppliers.models import Supplier, SupplierProduct

__all__ = [
    "AgentRun",
    "Base",
    "Budget",
    "DemandForecast",
    "ErpBehaviour",
    "ErpPurchaseOrder",
    "ErpRequest",
    "InventorySnapshot",
    "LlmCall",
    "Node",
    "Notification",
    "PoLine",
    "Product",
    "PurchaseOrder",
    "Recommendation",
    "SalesHistory",
    "StorageZone",
    "Supplier",
    "SupplierProduct",
    "User",
]
