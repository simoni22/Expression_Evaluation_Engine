"""Test suite for exprengine.

Run with:  python -m pytest    (or)    python tests/test_engine.py
"""

import math
import threading

import pytest

import exprengine as e
from exprengine import (
    DivisionByZeroError,
    ExpressionTypeError,
    FunctionError,
    ParseError,
    UndefinedVariableError,
)


# --- Arithmetic & precedence ----------------------------------------------

@pytest.mark.parametrize("src,expected", [
    ("2 + 3 * 4", 14),
    ("(2 + 3) * 4", 20),
    ("2 + 3 * (x - 1)", 11),          # with x=4
    ("10 - 2 - 3", 5),                # left assoc
    ("2 ** 3 ** 2", 512),             # right assoc
    ("-2 ** 2", -4),                  # unary lower than power
    ("2 ** -3", 0.125),
    ("7 // 2", 3),
    ("7 / 2", 3.5),
    ("7 % 3", 1),
    ("-(3 + 4)", -7),
])
def test_arithmetic(src, expected):
    assert e.evaluate(src, {"x": 4}) == expected


def test_division_true_vs_floor_types():
    assert isinstance(e.evaluate("4 / 2"), float)
    assert isinstance(e.evaluate("4 // 2"), int)


# --- Strings ---------------------------------------------------------------

def test_string_concat():
    assert e.evaluate('"hello " + name', {"name": "world"}) == "hello world"


def test_string_comparison():
    assert e.evaluate('"abc" < "abd"') is True


def test_string_escapes():
    assert e.evaluate(r'"a\nb"') == "a\nb"


# --- Booleans, logical, ternary -------------------------------------------

def test_logical_short_circuit():
    # right side references undefined var; must not be evaluated
    assert e.evaluate("false and missing", {}) is False
    assert e.evaluate("true or missing", {}) is True


def test_ternary():
    assert e.evaluate("a > b ? a : b", {"a": 3, "b": 7}) == 7


def test_not():
    assert e.evaluate("not (1 < 2)") is False


# --- Strict equality / typing ---------------------------------------------

def test_strict_equality():
    assert e.evaluate("1 == true") is False     # number vs boolean
    assert e.evaluate("1 == 1.0") is True
    assert e.evaluate('1 == "1"') is False
    assert e.evaluate("null == null") is True
    assert e.evaluate("null == 0") is False


@pytest.mark.parametrize("src", ['"3" + 4', "1 + true", "true + false"])
def test_no_implicit_coercion(src):
    with pytest.raises(ExpressionTypeError):
        e.evaluate(src)


@pytest.mark.parametrize("src,vars", [
    ("a and b", {"a": 1, "b": True}),       # non-bool to logical
    ("a ? 1 : 2", {"a": 5}),                # non-bool condition
    ("not 5", {}),
])
def test_boolean_required(src, vars):
    with pytest.raises(ExpressionTypeError):
        e.evaluate(src, vars)


# --- Null / undefined ------------------------------------------------------

def test_undefined_raises():
    with pytest.raises(UndefinedVariableError):
        e.evaluate("x + 1", {})


def test_null_is_a_value_but_not_arithmetic():
    # present null is fine to pass around / compare
    assert e.evaluate("x == null", {"x": None}) is True
    # but arithmetic on null is rejected (strict)
    with pytest.raises(ExpressionTypeError):
        e.evaluate("x + 1", {"x": None})


def test_division_by_zero():
    for src in ["1 / 0", "1 // 0", "1 % 0"]:
        with pytest.raises(DivisionByZeroError):
            e.evaluate(src)


# --- Variables, bindings, lambdas -----------------------------------------

def test_sequence_bindings():
    assert e.evaluate("x = 5; double = (n) => n * 2; double(x)") == 10


def test_lambda_closure_captures_scope():
    assert e.evaluate("base = 10; add = (n) => n + base; add(5)") == 15


def test_lambda_arity_error():
    with pytest.raises(FunctionError):
        e.evaluate("f = (a, b) => a + b; f(1)")


def test_assignment_does_not_leak_into_host_context():
    ctx = {"x": 1}
    assert e.evaluate("x = 99; x", ctx) == 99
    assert ctx == {"x": 1}   # host dict untouched


# --- Host-provided functions ----------------------------------------------

def test_host_function():
    eng = e.Engine(functions={"clamp": lambda x, lo, hi: max(lo, min(hi, x))})
    assert eng.evaluate("clamp(x, 0, 1)", {"x": 1.4}) == 1
    assert eng.evaluate("clamp(x, 0, 1)", {"x": -2}) == 0


def test_builtin_math():
    assert e.evaluate("sqrt(pow(3,2) + pow(4,2))") == 5.0
    assert e.evaluate("max(1, 9, 4)") == 9
    assert e.evaluate("round(3.14159, 2)") == 3.14
    assert e.evaluate("abs(-7)") == 7
    assert math.isclose(e.evaluate("pi"), math.pi)


def test_not_callable():
    with pytest.raises(FunctionError):
        e.evaluate("x(1)", {"x": 5})


# --- Parsing ---------------------------------------------------------------

@pytest.mark.parametrize("src", ["2 +", "(1 + 2", "1 2", "* 3", "a ? b"])
def test_parse_errors(src):
    with pytest.raises(ParseError):
        e.evaluate(src, {"a": True, "b": 1})


# --- Compile-then-evaluate & caching --------------------------------------

def test_compile_once_evaluate_many():
    expr = e.compile("price * qty")
    assert expr.evaluate({"price": 2.0, "qty": 3}) == 6.0
    assert expr.evaluate({"price": 5.0, "qty": 4}) == 20.0


def test_cache_returns_same_object():
    a = e.compile("1 + 1")
    b = e.compile("1 + 1")
    assert a is b


# --- Thread safety ---------------------------------------------------------

def test_thread_safety_under_concurrency():
    expr = e.compile("acc = 0; step = (n) => n * 2 + offset; step(x)")
    results: dict[int, list] = {}
    errors: list = []

    def worker(tid: int):
        try:
            out = [expr.evaluate({"x": i, "offset": tid}) for i in range(500)]
            results[tid] = out
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # Each thread's offset must be reflected with no cross-contamination.
    for tid, out in results.items():
        assert out == [i * 2 + tid for i in range(500)]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
