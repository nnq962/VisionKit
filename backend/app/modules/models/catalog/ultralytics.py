"""Danh mục được xác minh từ ultralytics/assets release v8.4.0."""

import json
from pathlib import Path

from app.core.errors import SourceError
from app.modules.models.schemas import CatalogVariant

CATALOG = json.loads(Path(__file__).with_suffix(".json").read_text())
VARIANTS = {
    item["id"]: CatalogVariant.model_validate(item) for item in CATALOG["variants"]
}


# ------------------------------- Tra cứu model -------------------------------
def get_variant(catalog_id: str) -> CatalogVariant:
    """Trả model đã duyệt theo catalog_id; SourceError 404 nếu ID không có trong catalog."""
    variant = VARIANTS.get(catalog_id)
    if variant is None:
        raise SourceError(404, "Model không có trong danh mục tải.")
    return variant
