# Write-up — Expression Evaluation Engine

## Approach

I treated this as a *library* design problem first: it will be open-sourced,
pulled as a dependency, and run millions of times per second, so predictable
semantics, a clean API, and per-call speed matter more than feature count. I
split the two cost phases the brief hints at ("usually for *similar*
expressions") into an expensive **compile** done once and a cheap **evaluate**
done millions of times.

The pipeline is `source → lexer → parser → AST`, where **each AST node compiles
into a closure** (`compile() -> fn(scope) -> value`). The compiled artifact is a
tree of composed functions, so the hot path has no tree re-walking and no
per-node type dispatch. Compiled expressions are cached in a thread-safe LRU
keyed by source — directly serving the "similar expressions" case. No runtime
`eval()` is used.

**Thread safety** falls out of the design: the AST is immutable, the host
context and builtins are read-only, and every `evaluate()` allocates a fresh
scope chain — so assignments and lambda calls write only into per-call scopes
and concurrent evaluations can't interfere. No locks on the hot path.

## What I decided vs. what the AI decided

- **I decided** the language (Python — fast iteration, readable for reviewers),
  the compile-then-evaluate strategy, the ban on runtime `eval()`, and every
  semantic policy below.
- **The AI proposed** the representation: I asked it to compare AST vs.
  Shunting-Yard/RPN vs. closure-compilation. It recommended AST as the canonical
  form with closure-compilation for speed, and argued *against* shunting-yard
  because its weak spots (ternary, short-circuit, calls) are exactly this task's
  required features. I agreed.
- **The AI implemented** the lexer, parser, nodes, engine, and tests against the
  spec we settled; I directed every ambiguity resolution.

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

`exprengine.compile(src)` returns a reusable `CompiledExpression`; call
`.evaluate(variables)` repeatedly. `exprengine.evaluate(src, vars)` is a one-shot
convenience, and `Engine(functions=, constants=)` registers custom callables and
constants. Every failure derives from `ExpressionError` (`ParseError`,
`UndefinedVariableError`, `ExpressionTypeError`, `DivisionByZeroError`,
`FunctionError`) and carries the source position. See `examples.py` for a runnable
demo, `README.md` for the full feature table, and `tests/` (43 tests, including a
concurrency test) for precise behavior.
