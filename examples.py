"""Runnable demo of exprengine. Run with:  python examples.py"""

import exprengine


def main() -> None:
    # 1) Basic math with operator precedence and parentheses
    expr = exprengine.compile("2 + 3 * (x - 1)")
    print("1) basic math      2 + 3 * (x - 1)  with x=4   ->", expr.evaluate({"x": 4}))

    # 2) Variables from the host context (compile once, evaluate many)
    total = exprengine.compile("price * qty * (1 - discount)")
    print("2) variables       price=9.99 qty=3 discount=0.1 ->",
          round(total.evaluate({"price": 9.99, "qty": 3, "discount": 0.1}), 4))

    # 3) Ternary if/else with booleans and comparison
    print("3) ternary if/else a > b ? a : b  with a=3 b=7  ->",
          exprengine.evaluate("a > b ? a : b", {"a": 3, "b": 7}))

    # 4) Custom (host-provided) function registered on an Engine
    engine = exprengine.Engine(
        functions={"clamp": lambda x, lo, hi: max(lo, min(hi, x))},
    )
    print("4) custom function clamp(x, 0, 1)  with x=1.4    ->",
          engine.evaluate("clamp(x, 0, 1)", {"x": 1.4}))

    # Bonus: variables and a lambda defined *inside* the expression
    print("   in-expr lambda   x = 5; double = (n) => n*2; double(x) ->",
          exprengine.evaluate("x = 5; double = (n) => n * 2; double(x)"))

    # Bonus: strict handling turns silent bugs into clear errors
    try:
        exprengine.evaluate("revenue + 1", {"revenu": 100})  # typo in the key
    except exprengine.UndefinedVariableError as err:
        print("   strict safety    revenue + 1 (typo'd key)     -> raises:", err)


if __name__ == "__main__":
    main()
