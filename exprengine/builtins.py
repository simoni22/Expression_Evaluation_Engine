"""Default math functions and constants available in every expression.

These are the "common math operations" from the spec (Q1). They are ordinary
Python callables; if misused (wrong arity / type) the ``Call`` node converts the
resulting Python error into a clean ``FunctionError`` / ``ExpressionTypeError``.

Consumers can add or override entries via ``Engine(functions=..., constants=...)``.
"""

from __future__ import annotations

import math
from typing import Any

from .errors import ExpressionTypeError
from .values import is_number, type_name


def _check_numbers(name: str, *args: Any) -> None:
    for a in args:
        if not is_number(a):
            raise ExpressionTypeError(f"{name}() requires numbers, got {type_name(a)}")


def _abs(x): _check_numbers("abs", x); return abs(x)
def _sqrt(x): _check_numbers("sqrt", x); return math.sqrt(x)
def _floor(x): _check_numbers("floor", x); return math.floor(x)
def _ceil(x): _check_numbers("ceil", x); return math.ceil(x)
def _exp(x): _check_numbers("exp", x); return math.exp(x)
def _pow(x, y): _check_numbers("pow", x, y); return math.pow(x, y)


def _log(x, base=None):
    if base is None:
        _check_numbers("log", x)
        return math.log(x)
    _check_numbers("log", x, base)
    return math.log(x, base)


def _round(x, ndigits=None):
    if ndigits is None:
        _check_numbers("round", x)
        return round(x)
    _check_numbers("round", x, ndigits)
    return round(x, ndigits)


def _min(*args):
    _check_numbers("min", *args)
    if not args:
        raise ExpressionTypeError("min() requires at least one argument")
    return min(args)


def _max(*args):
    _check_numbers("max", *args)
    if not args:
        raise ExpressionTypeError("max() requires at least one argument")
    return max(args)


DEFAULT_FUNCTIONS: dict[str, Any] = {
    "abs": _abs,
    "min": _min,
    "max": _max,
    "round": _round,
    "floor": _floor,
    "ceil": _ceil,
    "sqrt": _sqrt,
    "pow": _pow,
    "log": _log,
    "exp": _exp,
}

DEFAULT_CONSTANTS: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
}
