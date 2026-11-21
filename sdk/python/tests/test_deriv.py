"""Symbolic derivatives (labcalc.deriv): known answers and a check against central differences."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcalc import deriv as D  # noqa: E402
from labcalc import expr as E  # noqa: E402


def d(src, n=1, var="x", **kw):
    node, numeric = D.derivative(E.parse(src), var, n, **kw)
    return D.text(node), numeric


def value(node, x, angle="rad"):
    return float(E.evaluate(node, E.Ctx(names={"x": x}, angle=angle)))


def central(src, x, n=1, h=1e-4, angle="rad"):
    node = E.parse(src)
    f = lambda t: value(node, t, angle)  # noqa: E731
    if n == 1:
        return (f(x - 2 * h) - 8 * f(x - h) + 8 * f(x + h) - f(x + 2 * h)) / (12 * h)
    return (-f(x - 2 * h) + 16 * f(x - h) - 30 * f(x) + 16 * f(x + h) - f(x + 2 * h)) / (12 * h * h)


class KnownAnswers(unittest.TestCase):
    def test_first_derivatives(self):
        for src, want in [("x^2", "2*x"), ("x^3", "3*x^2"), ("sin(x)", "cos(x)"), ("sin(x^2)", "2*x*cos(x^2)"),
                          ("sin(x)/x", "(x*cos(x)-sin(x))/x^2"), ("ln(x)", "1/x"), ("exp(x)", "exp(x)"),
                          ("x^x", "x^x*(ln(x)+1)"), ("x/(x+1)", "1/(x+1)^2"), ("atan(x)", "1/(1+x^2)"),
                          ("asin(x)", "1/sqrt(1-x^2)"), ("5", "0"), ("x", "1")]:
            with self.subTest(src):
                self.assertEqual(d(src), (want, []))

    def test_second_derivatives(self):
        self.assertEqual(d("x^2", 2)[0], "2")
        self.assertEqual(d("x^3", 2)[0], "6*x")
        self.assertEqual(d("sin(x)", 2)[0], "-sin(x)")
        self.assertEqual(d("sin(x^2)", 2)[0], "2*cos(x^2)-4*x^2*sin(x^2)")

    def test_other_variable_is_a_constant(self):
        self.assertEqual(d("a*x^2")[0], "2*a*x")
        self.assertEqual(d("a*x^2", var="a")[0], "x^2")

    def test_degrees_carry_the_factor(self):
        self.assertEqual(d("sin(x)", angle="deg")[0], "pi*cos(x)/180")

    def test_user_function_and_prime(self):
        ctx = E.Ctx(funcs={"f": (["x"], E.parse("x^2"))})
        cal = ctx.callables()
        for src, want in [("f'(x)", "2*x"), ("f''(x)", "2"), ("f'(3)", "6")]:
            node, _ = D.expand(E.parse(src, cal), ctx.funcs)
            self.assertEqual(D.text(D.simplify(node)), want, src)
        ctx.names["x"] = 3.0
        self.assertEqual(float(E.evaluate(E.parse("f'(x)", cal), ctx)), 6.0)

    def test_transpose_is_not_a_prime(self):
        ctx = E.Ctx(names={"A": E.evaluate(E.parse("[[1, 2], [3, 4]]"), E.Ctx())})
        self.assertEqual(E.evaluate(E.parse("A'"), ctx).tolist(), [[1, 3], [2, 4]])

    def test_list_diff_still_gives_differences(self):
        self.assertEqual(E.evaluate(E.parse("diff([1, 4, 9])"), E.Ctx()).tolist(), [3, 5])

    def test_no_rule_falls_back_with_a_note(self):
        text, numeric = d("gamma(x)")
        self.assertIn("dnum_", text)
        self.assertEqual(numeric, ["gamma(x)"])
        node = D.derivative(E.parse("gamma(x)"), "x")[0]
        self.assertAlmostEqual(value(node, 2.0), 1 - 0.5772156649, places=5)     # Γ'(2) = 1 − γ

    def test_order_limits(self):
        for n in (0, 11):
            with self.assertRaises(E.CalcError):
                D.derivative(E.parse("x^2"), "x", n)


class AgainstCentralDifference(unittest.TestCase):
    FUNCS = ["x^2", "x^3 - 2x + 1", "sin(x)", "cos(x)", "tan(x)", "exp(2x)", "ln(x)", "log10(x)", "log(x, 2)", "sqrt(x)",
             "cbrt(x)", "x^x", "2^x", "sinh(x)", "cosh(x)", "tanh(x)", "atan(x)", "erf(x)", "sin(x^2)", "sin(x)/x",
             "x^2*sin(x)", "exp(-x^2)", "ln(x^2 + 1)", "1/(1 + x^2)", "root(x, 3)", "abs(x)", "sqrt(1 + x^2)*cos(x)"]

    def test_first(self):
        for src in self.FUNCS:
            node = D.derivative(E.parse(src), "x")[0]
            for x in (0.7, 1.3):
                with self.subTest(src, x=x):
                    self.assertAlmostEqual(value(node, x), central(src, x), delta=1e-5 * max(1, abs(central(src, x))))

    def test_second(self):
        for src in self.FUNCS:
            node = D.derivative(E.parse(src), "x", 2)[0]
            with self.subTest(src):
                b = central(src, 0.9, 2, h=1e-3)
                self.assertAlmostEqual(value(node, 0.9), b, delta=2e-4 * max(1, abs(b)))

    def test_inverse_functions_in_range(self):
        for src in ("asin(x)", "acos(x)"):
            node = D.derivative(E.parse(src), "x")[0]
            self.assertAlmostEqual(value(node, 0.4), central(src, 0.4), places=6)

    def test_degrees(self):
        node = D.derivative(E.parse("sin(x)"), "x", angle="deg")[0]
        self.assertAlmostEqual(value(node, 30.0, "deg"), math.pi / 180 * math.cos(math.radians(30)), places=10)


if __name__ == "__main__":
    unittest.main()
