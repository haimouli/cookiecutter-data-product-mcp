from src.settings import get_settings


def get_summary(entity_id: str) -> str:
    """Return a placeholder summary. Replace this with the product query."""
    cleaned = entity_id.strip()
    if not cleaned:
        raise ValueError("id is required")
    product_name = get_settings().product_name
    return f"Data for {cleaned} from {product_name}"
