# Design answer — "my expressions always evaluate to 0"

## What's almost certainly going on

"Always 0" is the classic signature of **silent defaulting**. In many expression
engines a misspelled or missing variable (`reveue` instead of `revenue`), a null
upstream value, or a type mismatch is quietly coerced to `0`/empty rather than
failing. The scientist's expression is *correct*; the engine is hiding the real
problem — a missing, null, or mistyped input — behind a plausible-looking number,
and gives them no signal pointing at the cause.

Our engine already blocks the worst version of this: undefined names and null
arithmetic raise instead of defaulting. But "*that* it broke" isn't "*why*," and
a raw error mid-pipeline is still a poor experience for a non-engineer running
thousands of expressions.

## Proposed feature: **Explain Mode (a trace / dry-run evaluator)**

An opt-in evaluation mode that returns, instead of a bare value, a structured
**explanation** of how the result was produced:

- **Per-subexpression trace** — a tree mirroring the expression, each part showing
  its computed value and type, so the scientist sees exactly *where* the value
  became `0`/`null` and what each variable resolved to.
- **Input report** — which variables were used, which were provided, and which
  were **referenced but missing**, flagging fuzzy near-misses (`reveue` ≈
  `revenue`) as likely typos.
- **Type & null highlights** — the first point where a `null` or unexpected type
  entered, with its location in the source.

It would surface as a human-readable trace plus a one-line "why is this 0?"
summary.

## Why this

It's **diagnostic, not behavioral**: it changes nothing about normal evaluation
or its speed, so results and the hot path are untouched. It fits the real
workflow — debugging one expression out of thousands, self-service, without a
ticket — turning an opaque number into an answer, and it targets the single most
common root cause (a typo'd or missing input) head-on. A natural follow-on is a
**compile-time lint** that warns when a referenced variable isn't in a declared
input schema, catching the mistake before the expression ever runs.
