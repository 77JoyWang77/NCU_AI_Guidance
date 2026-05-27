"""ContextVar-based user_id propagation for async request contexts."""
from contextvars import ContextVar

_user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)


def get_user_id() -> str | None:
    return _user_id_var.get()


def set_user_id(uid: str | None) -> None:
    _user_id_var.set(uid)
