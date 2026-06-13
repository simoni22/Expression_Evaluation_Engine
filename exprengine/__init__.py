"""exprengine — a safe, fast, thread-safe expression evaluation engine.

Compile an expression once, evaluate it many times against varying variables::

    import exprengine

    expr = exprengine.compile("price * qty * (1 - discount)")
    expr.evaluate({"price": 9.99, "qty": 3, "discount": 0.1})

Or evaluate in one shot::

    exprengine.evaluate("a > b ? a : b", {"a": 3, "b": 7})   # -> 7

Register custom functions/constants with an Engine::

    eng = exprengine.Engine(functions={"clamp": lambda x, lo, hi: max(lo, min(hi, x))})
    eng.evaluate("clamp(x, 0, 1)", {"x": 1.4})               # -> 1

The engine supports numbers, strings, booleans and null; arithmetic
(+ - * / // % **), comparison, equality, logical and/or/not, ternary ?:,
in-expression bindings and lambdas (``x = 5; double = (n) => n*2; double(x)``),
and host- or expression-defined functions. Typing is strict and undefined
variables raise rather than defaulting to 0.
"""

from __future__ import annotations

from .engine import CompiledExpression, Engine, compile, evaluate
from .errors import (
    DivisionByZeroError,
    EvaluationError,
    ExpressionError,
    ExpressionTypeError,
    FunctionError,
    ParseError,
    UndefinedVariableError,
)

__all__ = [
    "compile",
    "evaluate",
    "Engine",
    "CompiledExpression",
    "ExpressionError",
    "ParseError",
    "EvaluationError",
    "UndefinedVariableError",
    "ExpressionTypeError",
    "DivisionByZeroError",
    "FunctionError",
]

__version__ = "0.1.0"
