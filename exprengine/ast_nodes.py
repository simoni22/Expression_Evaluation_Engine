"""AST nodes — the canonical, immutable representation of an expression.

Every node implements ``compile() -> Callable[[Scope], Any]``. Compilation walks
the tree *once* and returns a closure; evaluating the expression is then just
calling that closure against a scope. This is the "compile-to-closures"
optimization: the hot path is composed function calls with no tree re-walking
and no per-node type dispatch.

Nodes are immutable (constructed once, only read), so a compiled expression is
safe to share across threads. All type/null checks live here, enforcing the
strict semantics agreed in the spec.
"""

from __future__ import annotations

from typing import Any, Callable

from .errors import (
    DivisionByZeroError,
    ExpressionTypeError,
    FunctionError,
)
from .values import Scope, is_number, is_string, type_name

EvalFn = Callable[[Scope], Any]


class Node:
    """Base AST node. ``position`` is the source offset for error reporting."""

    __slots__ = ("position",)

    def __init__(self, position: int = 0) -> None:
        self.position = position

    def compile(self) -> EvalFn:  # pragma: no cover - abstract
        raise NotImplementedError


# --- Leaves ----------------------------------------------------------------

class Literal(Node):
    """A constant: number, string, boolean, or null (None)."""

    __slots__ = ("value",)

    def __init__(self, value: Any, position: int = 0) -> None:
        super().__init__(position)
        self.value = value

    def compile(self) -> EvalFn:
        value = self.value
        return lambda scope: value


class Variable(Node):
    """A name lookup. Absent name -> UndefinedVariableError (strict)."""

    __slots__ = ("name",)

    def __init__(self, name: str, position: int = 0) -> None:
        super().__init__(position)
        self.name = name

    def compile(self) -> EvalFn:
        name = self.name
        return lambda scope: scope.lookup(name)


# --- Statements ------------------------------------------------------------

class Assignment(Node):
    """``name = expr`` — binds in the current (local) scope and returns value."""

    __slots__ = ("name", "value")

    def __init__(self, name: str, value: Node, position: int = 0) -> None:
        super().__init__(position)
        self.name = name
        self.value = value

    def compile(self) -> EvalFn:
        name = self.name
        value_fn = self.value.compile()

        def run(scope: Scope) -> Any:
            v = value_fn(scope)
            scope.define(name, v)
            return v

        return run


class Sequence(Node):
    """``stmt ; stmt ; ... ; expr`` — runs in order, returns the last value."""

    __slots__ = ("statements",)

    def __init__(self, statements: list[Node], position: int = 0) -> None:
        super().__init__(position)
        self.statements = statements

    def compile(self) -> EvalFn:
        fns = [s.compile() for s in self.statements]
        if len(fns) == 1:
            return fns[0]

        def run(scope: Scope) -> Any:
            result = None
            for fn in fns:
                result = fn(scope)
            return result

        return run


# --- Operators -------------------------------------------------------------

class BinaryOp(Node):
    """Arithmetic, comparison, and equality operators."""

    __slots__ = ("op", "left", "right")

    def __init__(self, op: str, left: Node, right: Node, position: int = 0) -> None:
        super().__init__(position)
        self.op = op
        self.left = left
        self.right = right

    def compile(self) -> EvalFn:
        lf = self.left.compile()
        rf = self.right.compile()
        impl = _BINARY_IMPL[self.op]
        pos = self.position
        op = self.op

        def run(scope: Scope) -> Any:
            return impl(lf(scope), rf(scope), op, pos)

        return run


class UnaryOp(Node):
    """Prefix ``-``, ``+`` (numbers) and ``not`` (boolean)."""

    __slots__ = ("op", "operand")

    def __init__(self, op: str, operand: Node, position: int = 0) -> None:
        super().__init__(position)
        self.op = op
        self.operand = operand

    def compile(self) -> EvalFn:
        operand_fn = self.operand.compile()
        op = self.op
        pos = self.position

        if op == "not":
            def run_not(scope: Scope) -> Any:
                v = operand_fn(scope)
                _require_bool(v, "not", pos)
                return not v
            return run_not

        sign = -1 if op == "-" else 1

        def run_num(scope: Scope) -> Any:
            v = operand_fn(scope)
            if not is_number(v):
                raise ExpressionTypeError(
                    f"unary '{op}' requires a number, got {type_name(v)} (at position {pos})"
                )
            return sign * v

        return run_num


class Logical(Node):
    """Short-circuiting ``and`` / ``or``. Both operands must be boolean."""

    __slots__ = ("op", "left", "right")

    def __init__(self, op: str, left: Node, right: Node, position: int = 0) -> None:
        super().__init__(position)
        self.op = op
        self.left = left
        self.right = right

    def compile(self) -> EvalFn:
        lf = self.left.compile()
        rf = self.right.compile()
        pos = self.position
        is_and = self.op == "and"

        def run(scope: Scope) -> Any:
            left = lf(scope)
            _require_bool(left, "and" if is_and else "or", pos)
            if is_and:
                if not left:
                    return False  # short-circuit
            else:
                if left:
                    return True   # short-circuit
            right = rf(scope)
            _require_bool(right, "and" if is_and else "or", pos)
            return right

        return run


class Ternary(Node):
    """``cond ? then : otherwise`` — condition must be boolean."""

    __slots__ = ("cond", "then", "otherwise")

    def __init__(self, cond: Node, then: Node, otherwise: Node, position: int = 0) -> None:
        super().__init__(position)
        self.cond = cond
        self.then = then
        self.otherwise = otherwise

    def compile(self) -> EvalFn:
        cf = self.cond.compile()
        tf = self.then.compile()
        of = self.otherwise.compile()
        pos = self.position

        def run(scope: Scope) -> Any:
            c = cf(scope)
            _require_bool(c, "ternary condition", pos)
            return tf(scope) if c else of(scope)

        return run


# --- Functions -------------------------------------------------------------

class UserFunction:
    """A callable produced by evaluating a lambda. Captures its defining scope."""

    __slots__ = ("params", "body_fn", "def_scope", "name")

    def __init__(self, params: list[str], body_fn: EvalFn, def_scope: Scope, name: str = "<lambda>") -> None:
        self.params = params
        self.body_fn = body_fn
        self.def_scope = def_scope
        self.name = name

    def __call__(self, *args: Any) -> Any:
        if len(args) != len(self.params):
            raise FunctionError(
                f"function '{self.name}' expected {len(self.params)} argument(s), got {len(args)}"
            )
        call_scope = Scope(dict(zip(self.params, args)), parent=self.def_scope)
        return self.body_fn(call_scope)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserFunction {self.name}({', '.join(self.params)})>"


class Lambda(Node):
    """``(params) => body`` — evaluates to a UserFunction closing over scope."""

    __slots__ = ("params", "body")

    def __init__(self, params: list[str], body: Node, position: int = 0) -> None:
        super().__init__(position)
        self.params = params
        self.body = body

    def compile(self) -> EvalFn:
        params = self.params
        body_fn = self.body.compile()
        return lambda scope: UserFunction(params, body_fn, scope)


class Call(Node):
    """``callee(args...)`` — host callables or user functions."""

    __slots__ = ("callee", "args")

    def __init__(self, callee: Node, args: list[Node], position: int = 0) -> None:
        super().__init__(position)
        self.callee = callee
        self.args = args

    def compile(self) -> EvalFn:
        callee_fn = self.callee.compile()
        arg_fns = [a.compile() for a in self.args]
        pos = self.position
        name = self.callee.name if isinstance(self.callee, Variable) else "<expression>"

        def run(scope: Scope) -> Any:
            target = callee_fn(scope)
            if not callable(target):
                raise FunctionError(
                    f"'{name}' is not callable (it is {type_name(target)}) (at position {pos})"
                )
            argv = [fn(scope) for fn in arg_fns]
            try:
                return target(*argv)
            except (FunctionError, ExpressionTypeError, DivisionByZeroError):
                raise
            except ZeroDivisionError as exc:
                raise DivisionByZeroError(f"division by zero in '{name}'") from exc
            except TypeError as exc:
                raise FunctionError(f"bad call to '{name}': {exc}") from exc
            except ValueError as exc:
                raise ExpressionTypeError(f"invalid argument to '{name}': {exc}") from exc

        return run


# --- Operator implementations & type guards --------------------------------

def _require_bool(value: Any, where: str, pos: int) -> None:
    if not isinstance(value, bool):
        raise ExpressionTypeError(
            f"{where} requires a boolean, got {type_name(value)} (at position {pos})"
        )


def _kind(value: Any) -> str:
    """Coarse type tag used for strict, type-aware equality."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "other"


def _both_numbers_or_strings(a: Any, b: Any) -> bool:
    return (is_number(a) and is_number(b)) or (is_string(a) and is_string(b))


def _add(a: Any, b: Any, op: str, pos: int) -> Any:
    if is_number(a) and is_number(b):
        return a + b
    if is_string(a) and is_string(b):
        return a + b
    raise ExpressionTypeError(
        f"'+' needs two numbers or two strings, got {type_name(a)} and {type_name(b)} (at position {pos})"
    )


def _arith(fn, name):
    def impl(a: Any, b: Any, op: str, pos: int) -> Any:
        if not (is_number(a) and is_number(b)):
            raise ExpressionTypeError(
                f"'{name}' needs two numbers, got {type_name(a)} and {type_name(b)} (at position {pos})"
            )
        return fn(a, b)
    return impl


def _div(a: Any, b: Any, op: str, pos: int) -> Any:
    if not (is_number(a) and is_number(b)):
        raise ExpressionTypeError(
            f"'/' needs two numbers, got {type_name(a)} and {type_name(b)} (at position {pos})"
        )
    if b == 0:
        raise DivisionByZeroError(f"division by zero (at position {pos})")
    return a / b


def _floordiv(a: Any, b: Any, op: str, pos: int) -> Any:
    if not (is_number(a) and is_number(b)):
        raise ExpressionTypeError(
            f"'//' needs two numbers, got {type_name(a)} and {type_name(b)} (at position {pos})"
        )
    if b == 0:
        raise DivisionByZeroError(f"floor division by zero (at position {pos})")
    return a // b


def _mod(a: Any, b: Any, op: str, pos: int) -> Any:
    if not (is_number(a) and is_number(b)):
        raise ExpressionTypeError(
            f"'%' needs two numbers, got {type_name(a)} and {type_name(b)} (at position {pos})"
        )
    if b == 0:
        raise DivisionByZeroError(f"modulo by zero (at position {pos})")
    return a % b


def _compare(pyop, name):
    def impl(a: Any, b: Any, op: str, pos: int) -> Any:
        if not _both_numbers_or_strings(a, b):
            raise ExpressionTypeError(
                f"'{name}' needs two numbers or two strings, "
                f"got {type_name(a)} and {type_name(b)} (at position {pos})"
            )
        return pyop(a, b)
    return impl


def _eq(a: Any, b: Any, op: str, pos: int) -> Any:
    # Type-aware: differing kinds are never equal (so 1 == true is False,
    # not a Python quirk). null only equals null.
    if a is None or b is None:
        return a is None and b is None
    if _kind(a) != _kind(b):
        return False
    return a == b


def _ne(a: Any, b: Any, op: str, pos: int) -> Any:
    return not _eq(a, b, op, pos)


_BINARY_IMPL: dict[str, Callable[[Any, Any, str, int], Any]] = {
    "+": _add,
    "-": _arith(lambda a, b: a - b, "-"),
    "*": _arith(lambda a, b: a * b, "*"),
    "/": _div,
    "//": _floordiv,
    "%": _mod,
    "**": _arith(lambda a, b: a ** b, "**"),
    "<": _compare(lambda a, b: a < b, "<"),
    "<=": _compare(lambda a, b: a <= b, "<="),
    ">": _compare(lambda a, b: a > b, ">"),
    ">=": _compare(lambda a, b: a >= b, ">="),
    "==": _eq,
    "!=": _ne,
}
