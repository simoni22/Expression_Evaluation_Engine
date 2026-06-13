"""Runtime value model and lexical scope.

Value mapping (expression value  ->  Python value):
    number   -> int | float
    string   -> str
    boolean  -> bool
    null     -> None

"undefined" is *not* a value: it is the absence of a binding, surfaced as an
``UndefinedVariableError`` at lookup time. That is the deliberate distinction
between "null" (a present value meaning nothing) and "undefined" (no binding).

Note on booleans: in Python ``bool`` is a subclass of ``int``. Under our strict
typing rules a boolean is NOT a number, so ``is_number`` explicitly excludes it.
"""

from __future__ import annotations

from typing import Any

from .errors import UndefinedVariableError


def is_number(value: Any) -> bool:
    """True for ints and floats, but NOT booleans (strict typing)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def is_string(value: Any) -> bool:
    return isinstance(value, str)


def type_name(value: Any) -> str:
    """Human-readable type name for use in error messages."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if callable(value):
        return "function"
    return type(value).__name__


class Scope:
    """A lexical scope: a dict of bindings plus an optional parent.

    Lookup walks the parent chain (innermost first). The root scope wraps the
    host-provided context and is treated as read-only — top-level assignments
    and lambda calls always write into fresh child scopes. Because a new scope
    chain is built per ``evaluate`` call and nodes only ever *read* shared
    state, evaluation is thread-safe with no locking.
    """

    __slots__ = ("vars", "parent")

    def __init__(self, vars: dict[str, Any] | None = None, parent: "Scope | None" = None) -> None:
        self.vars: dict[str, Any] = vars if vars is not None else {}
        self.parent = parent

    def lookup(self, name: str) -> Any:
        scope: "Scope | None" = self
        while scope is not None:
            # `in` then index keeps a binding to None (null) distinct from
            # an absent binding (undefined).
            if name in scope.vars:
                return scope.vars[name]
            scope = scope.parent
        raise UndefinedVariableError(name)

    def define(self, name: str, value: Any) -> None:
        self.vars[name] = value

    def child(self, vars: dict[str, Any] | None = None) -> "Scope":
        return Scope(vars, parent=self)
