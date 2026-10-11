"""Traceable estimator rules for rectangular duct pricing."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


DUCT_DEFAULTS = {
    "rect_duct_area_rate_enabled": "false",
    "lt_area_rate_enabled": "false",
    "fitting_section_area_factor": "1.0",
    "rect_fitting_material_mode": "quote_required",
}


def duct_pricing(parameters: dict) -> dict:
    return {**DUCT_DEFAULTS, **parameters.get("duct_pricing", {})}


def enabled(value: Any) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes", "on", "enabled"}


def decimal_value(value: Any, name: str = "value", *, minimum: Decimal | None = None) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{name} must be a finite decimal number") from None
    if not result.is_finite() or (minimum is not None and result < minimum):
        raise ValueError(f"{name} is outside its permitted range")
    return result


def raw(value: Decimal) -> str:
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def section_perimeter(width_mm: Any, height_mm: Any) -> Decimal:
    return Decimal(2) * (decimal_value(width_mm, "width_mm", minimum=Decimal(0)) + decimal_value(height_mm, "height_mm", minimum=Decimal(0)))


def area_from_length(width_mm: Any, height_mm: Any, length_mm: Any, factor: Any = "1") -> Decimal:
    perimeter = section_perimeter(width_mm, height_mm)
    length = decimal_value(length_mm, "length_mm", minimum=Decimal(0))
    multiplier = decimal_value(factor, "fitting_section_area_factor", minimum=Decimal(0))
    return perimeter * length / Decimal("1000000") * multiplier


def catalog_rect_products(catalog: list[dict]) -> list[tuple[Decimal, dict]]:
    result: list[tuple[Decimal, dict]] = []
    for product in catalog:
        if product.get("install_code") != "DUCT_RECT" or product.get("unit") != "m2" or not product.get("net_cost_chf"):
            continue
        match = re.search(r"(\d{2,4})x(\d{2,4})", product.get("model", "") or product.get("description", ""))
        if not match:
            continue
        perimeter = section_perimeter(match.group(1), match.group(2))
        result.append((perimeter, product))
    return sorted(result, key=lambda item: (item[0], item[1]["product_id"]))


def select_rect_product(catalog: list[dict], width_mm: Any, height_mm: Any) -> tuple[dict, Decimal] | None:
    tender_perimeter = section_perimeter(width_mm, height_mm)
    for perimeter, product in catalog_rect_products(catalog):
        if perimeter >= tender_perimeter:
            return product, perimeter
    return None


def area_rule_assumption(product: dict, width_mm: Any, height_mm: Any) -> str:
    tender = section_perimeter(width_mm, height_mm)
    selected_perimeter = section_perimeter(*re.search(r"(\d{2,4})x(\d{2,4})", product.get("model", "")).groups())
    return (f"Rectangular duct area rate: tender section {width_mm}x{height_mm} mm "
            f"(perimeter {raw(tender)} mm) -> {product['product_id']} "
            f"(perimeter {raw(selected_perimeter)} mm), CHF {product['net_cost_chf']}/m2.")
