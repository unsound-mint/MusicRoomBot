# app/services/config_utils.py
def parse_int(
    s: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> tuple[int | None, str | None]:
    try:
        v = int(s)
    except Exception:
        return None, "not an integer"
    if minimum is not None and v < minimum:
        return None, f"must be >= {minimum}"
    if maximum is not None and v > maximum:
        return None, f"must be <= {maximum}"
    return v, None


def parse_float(
    s: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> tuple[float | None, str | None]:
    try:
        v = float(s)
    except Exception:
        return None, "not a number"
    if minimum is not None and v < minimum:
        return None, f"must be >= {minimum}"
    if maximum is not None and v > maximum:
        return None, f"must be <= {maximum}"
    return v, None
