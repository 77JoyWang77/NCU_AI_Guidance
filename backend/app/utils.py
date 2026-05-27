"""UUID generation utilities. All system IDs use UUID7 for time-ordered, sortable IDs."""
from uuid_extensions import uuid7str as _uuid7str


def new_id() -> str:
    """Generate a new UUID7 string."""
    return _uuid7str()
