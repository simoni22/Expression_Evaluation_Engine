# exprengine — Expression Evaluation Engine

A small, safe, fast, thread-safe library for evaluating expressions like
`2 + 3 * (x - 1)` against named variables. Built for a use case where
data scientists define computed variables and logic as expressions that run
**millions of times per second** in production.

It does **not** use Python's `eval()`. Expressions are lexed, parsed into an
immutable AST, and **compiled once** into a tree of closures; the resulting
object is then evaluated many times against varying variable contexts.

## Install / run

Pure standard library (Python 3.10+). Tests use `pytest`:

```bash
python -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest -q
```

## Quick start

```python
import exprengine

# Compile once, evaluate many times (the production pattern):
expr = exprengine.compile("price * qty * (1 - discount)")
expr.evaluate({"price": 9.99, "qty": 3, "discount": 0.1})   # -> 26.973

# One-shot convenience:
exprengine.evaluate("a > b ? a : b", {"a": 3, "b": 7})       # -> 7

# Register custom functions / constants:
eng = exprengine.Engine(
    functions={"clamp": lambda x, lo, hi: max(lo, min(hi, x))},
    constants={"TAU": 6.28318},
)
eng.evaluate("clamp(x, 0, 1)", {"x": 1.4})                   # -> 1
```

## Language features

| Category | Supported |
|---|---|
| Numbers | int & float; `+ - * / // % **`; unary `-`/`+` |
| Strings | literals (`"..."`/`'...'`, escapes), `+` concat, comparisons |
| Booleans | `true`, `false`; `and`, `or`, `not` (short-circuit); ternary `cond ? a : b` |
| Comparison / equality | `< <= > >= == !=` |
| Variables | host-provided via the eval context, **and** in-expression `x = 5; ...` |
| Functions | host-provided Python callables, **and** in-expression lambdas `(n) => n * 2` |
| Math builtins | `abs min max round floor ceil sqrt pow log exp`; constants `pi`, `e` |
| Null / undefined | `null` is a first-class value; referencing an undefined name **raises** |

```text
x = 5;
double = (n) => n * 2;
double(x) + max(1, 2, 3)        # -> 13
```

### Operator precedence (lowest → highest)

`;`  →  `=`  →  `?:`  →  `or`  →  `and`  →  `== !=`  →  `< <= > >=`  →
`+ -`  →  `* / // %`  →  unary `not - +`  →  `**` (right-assoc)  →  call `f(...)`.

## Semantics (the deliberate decisions)

- **Strict typing — no implicit coercion.** `"3" + 4`, `1 + true` raise
  `ExpressionTypeError`. `+` means numeric add *or* string concat; never mixed.
  Booleans are **not** numbers.
- **Strict null/undefined.** A referenced-but-missing name raises
  `UndefinedVariableError`; arithmetic on `null` raises. This is intentional —
  it prevents expressions silently collapsing to `0`. `null == null` is `True`.
- **Booleans required** for `and`/`or`/`not` and ternary conditions.
- **Division by zero raises** `DivisionByZeroError` (never `inf`/`nan`).
- `/` is true division (→ float), `//` is floor division, like Python.

## Thread safety

A `CompiledExpression` is immutable and shares only read-only state (builtins +
engine namespace). Each `evaluate()` allocates a fresh scope chain, and
top-level assignments write into that per-call scope — never into the host
context. The same compiled object can be evaluated concurrently from many
threads without locks. The compile cache is guarded by a lock.

## Errors

All errors derive from `exprengine.ExpressionError`:
`ParseError`, `UndefinedVariableError`, `ExpressionTypeError`,
`DivisionByZeroError`, `FunctionError`. Messages include the source position.

## Layout

```
exprengine/
  lexer.py       tokenizer
  parser.py      recursive-descent parser -> AST
  ast_nodes.py   AST; each node compiles to a closure (the hot path)
  values.py      Scope + strict type helpers
  builtins.py    default math functions / constants
  engine.py      Engine, CompiledExpression, thread-safe LRU compile cache
  errors.py      public exception hierarchy
tests/           pytest suite (incl. a concurrency test)
```
