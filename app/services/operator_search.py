from sqlalchemy import or_


def operator_search(query: str, *columns):
    """Literal, case-insensitive matching over caller-allowlisted public context."""
    return or_(*(column.icontains(query.strip(), autoescape=True) for column in columns))
