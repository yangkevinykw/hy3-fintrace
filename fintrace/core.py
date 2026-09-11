"""Safe arithmetic and exact bounded rational-expression equivalence. No eval."""
from __future__ import annotations

import re
from fractions import Fraction
from decimal import Decimal, localcontext

OPS = {"add", "subtract", "multiply", "divide"}
NUMBER = re.compile(r"(?<![\w.])\(?[-+−]?\$?\s*\d[\d,]*(?:\.\d+)?\s*%?\)?(?![\w.])")


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("数值必须是有限数字或数字字符串")
    s = str(value).strip().replace(",", "").replace("$", "").replace("−", "-").replace(" ", "")
    if len(s) > 48:
        raise ValueError("数值过长")
    if s.startswith("const_"):
        s = s[6:].replace("m1", "-1")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    pct = s.endswith("%")
    if pct:
        s = s[:-1]
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d{1,2})?", s):
        raise ValueError("无法解析数值")
    n = Fraction(s) / (100 if pct else 1)
    if abs(n) > 10**30 or n.denominator > 10**50:
        raise ValueError("数值超出支持范围")
    return n


def render(n):
    if isinstance(n, Fraction):
        if n.denominator == 1:
            return str(n.numerator)
        with localcontext() as context:
            context.prec = 36
            return format(Decimal(n.numerator) / Decimal(n.denominator), "f").rstrip("0").rstrip(".")
    return str(n)


def close(a, b):
    # FinQA official execution comparison rounds to five decimal places.
    return round(float(a), 5) == round(float(b), 5)


def calculation_close(a, b):
    # Exact integers have no decimal rounding error. A relative tolerance would
    # otherwise hide e.g. a one-unit mistake in a billion-unit total.
    if a.denominator == 1 and b.denominator == 1:
        return a == b
    # Solver protocol asks for >=8 decimal digits. Keep tiny intermediate values
    # meaningful; FinQA's five-place final-answer rounding is not appropriate here.
    return abs(a-b) <= max(abs(a), abs(b)) * Fraction(1, 10**8) + Fraction(1, 10**12)


def calculate(op, a, b):
    if op not in OPS:
        raise ValueError("不支持的运算")
    if op == "divide" and b == 0:
        raise ValueError("除数为零")
    out = {"add": lambda: a + b, "subtract": lambda: a - b,
           "multiply": lambda: a * b, "divide": lambda: a / b}[op]()
    if len(str(abs(out.numerator))) > 180 or len(str(out.denominator)) > 180:
        raise ValueError("计算超出精度预算")
    return out


def parse_program(program):
    matches = list(re.finditer(r"(\w+)\(([^(),]+),\s*([^(),]+)\)", program))
    if not matches or len(matches) > 16:
        raise ValueError("标准程序为空或超出长度范围")
    remaining = re.sub(r"(\w+)\(([^(),]+),\s*([^(),]+)\)", "", program)
    if remaining.strip(" ,\n"):
        raise ValueError("标准程序格式不支持")
    result = []
    for i, m in enumerate(matches):
        op, a, b = m.groups()
        if op not in OPS:
            raise ValueError("当前题集仅支持四则运算")
        args = [a.strip(), b.strip()]
        for arg in args:
            if arg.startswith("#"):
                if not re.fullmatch(r"#\d+", arg) or int(arg[1:]) >= i:
                    raise ValueError("标准程序依赖非法")
            else:
                number(arg)
        result.append((op, args))
    return result


def execute_program(program):
    outputs = []
    for op, args in parse_program(program):
        vals = [outputs[int(x[1:])] if x.startswith("#") else number(x) for x in args]
        outputs.append(calculate(op, *vals))
    return outputs


# Polynomial monomials are sorted tuples of variable IDs, coefficients Fractions.
def poly_add(a, b, sign=1):
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, Fraction(0)) + sign * v
    out = {k: v for k, v in out.items() if v}
    if len(out) > 256:
        raise ValueError("符号验证超过预算")
    return out


def poly_mul(a, b):
    if len(a) * len(b) > 4096:
        raise ValueError("符号验证超过预算")
    out = {}
    for ka, va in a.items():
        for kb, vb in b.items():
            k = tuple(sorted(ka + kb))
            if len(k) > 24:
                raise ValueError("符号次数超过预算")
            out[k] = out.get(k, Fraction(0)) + va * vb
    return poly_add(out, {})


def symbol(key):
    return ({(key,): Fraction(1)}, {(): Fraction(1)})


def constant(value):
    return ({(): number(value)}, {(): Fraction(1)})


def expression(op, a, b):
    an, ad = a
    bn, bd = b
    if op in ("add", "subtract"):
        return (poly_add(poly_mul(an, bd), poly_mul(bn, ad), 1 if op == "add" else -1), poly_mul(ad, bd))
    if op == "multiply":
        return poly_mul(an, bn), poly_mul(ad, bd)
    if op == "divide":
        if not bn:
            raise ValueError("符号除数为零")
        return poly_mul(an, bd), poly_mul(ad, bn)
    raise ValueError("不支持的符号运算")


def equivalent(a, b):
    return poly_mul(a[0], b[1]) == poly_mul(b[0], a[1])
