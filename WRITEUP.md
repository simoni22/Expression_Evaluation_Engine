# Write-up — Expression Evaluation Engine

## Approach

I treated this as a *library* design problem first: it will be open-sourced,
pulled as a dependency, and run millions of times per second, so predictable
semantics, a clean API, and per-call speed matter more than feature count. I
split the two cost phases the brief hints at ("usually for *similar*
expressions") into an expensive **compile** done once and a cheap **evaluate**
done millions of times.

The pipeline is `source → lexer → parser → AST`, where **each AST node compiles
once into a native Python closure** (`compile() -> fn(scope) -> value`). The
compiled artifact is a tree of composed functions, so the hot path avoids
re-walking the tree and per-node type dispatch — it runs at composed-function
speed and sidesteps Python's overhead on deep recursive calls. Compiled
expressions are cached in a thread-safe LRU keyed by source, directly serving the
"similar expressions" case. No runtime `eval()` is used.

**Thread safety** falls out of the design: the AST is immutable, the host
context and builtins are read-only, and every `evaluate()` allocates a fresh
scope chain — so assignments and lambda calls write only into per-call scopes
and concurrent evaluations can't interfere. No locks on the hot path.

## What I decided vs. what the AI decided

- I architected the engine's core paradigm, decided the language (Python — fast iteration, readable for
  reviewers), and mandated every semantic policy below — notably strict typing and null handling, 
  to prevent silent data corruption.
- I identified the performance bottleneck of standard recursive AST
  evaluation in Python, then asked the AI to address this problem, and compare AST vs. Shunting-Yard/RPN
  vs. other approaches. It recommended AST as the canonical form with
  closure-compilation for speed, and argued *against* shunting-yard because its
  weak spots (ternary, short-circuit, calls) are exactly this task's required
  features — recommendations I approved and asked to integrate.
- **I utilized the AI** (Claude Code CLI agent) to scaffold the boilerplate,
  implement the lexer/parser/engine logic, and generate the unit test suite
  strictly against the constraints and specifications we defined. I relied on the AI for the raw implementation, allowing me to focus entirely on system efficiency, architectural trade-offs, and getting the core design concepts right.

## Vague-by-design decisions (and why)

1. **Strict typing, no implicit coercion.** `"3" + 4` and `1 + true` raise;
   booleans aren't numbers. Silent coercion is a debugging trap in a shared dep.
2. **null vs. undefined are distinct.** *null* is a real value (`null == null`);
   an *undefined* (missing) name **raises**, and arithmetic on `null` raises.
   This strictness is the direct antidote to the "always evaluates to 0"
   complaint — values never silently default.
3. **Booleans required** for `and`/`or`/`not` and ternary conditions.
4. **"Define variables/functions inside expressions"** → a sequential semicolon
   syntax plus lambdas: `x = 5; double = (n) => n*2; double(x)`. Host injection
   via the context is the primary mechanism; this is its in-expression complement.
5. **"Common math"** → `abs min max round floor ceil sqrt pow log exp` + `pi`,
   `e`, all extensible via `Engine(functions=, constants=)`.
6. **Division by zero raises** (never inf/nan); `/` is true division, `//` floor.
7. **Deferred** to keep v1 polished: arrays, regex, dotted attribute access.

## Using the library

The `exprengine/` package is pure standard library (Python 3.10+) — drop it in
and import it. `compile(src)` returns a reusable `CompiledExpression` you call
many times; `evaluate(src, vars)` is a one-shot; `Engine(functions=, constants=)`
registers custom callables/constants.

```python
import exprengine

expr = exprengine.compile("price * qty * (1 - discount)")   # parse + compile once
expr.evaluate({"price": 9.99, "qty": 3, "discount": 0.1})    # -> 26.973
exprengine.evaluate("a > b ? a : b", {"a": 3, "b": 7})       # one-shot -> 7
```

Every failure derives from `ExpressionError` (`ParseError`,
`UndefinedVariableError`, `ExpressionTypeError`, `DivisionByZeroError`,
`FunctionError`) and carries the source position. To run the included demo and
test suite:

```bash
python examples.py
python -m pytest -q        # 43 tests, including a concurrency test
```

See `README.md` for the full feature table and operator-precedence reference.
