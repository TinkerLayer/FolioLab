"""Derivatives in lines and graphs, formula cards with page values, exports, stored matrix results."""
import base64
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from rechner import bundle as B  # noqa: E402
from rechner import console as CON  # noqa: E402
from rechner import expr as E  # noqa: E402
from rechner import graph as G  # noqa: E402
from rechner import library as L  # noqa: E402
from rechner import units as U  # noqa: E402
from rechner import workspace as W  # noqa: E402


def calc(i, src, **kw):
    return {"id": f"l{i}", "type": "calc", "src": src, **kw}


def page(lines, values=(), cards=(), angle="rad", eid="e"):
    items = [calc(i, s) for i, s in enumerate(lines)] + list(cards)
    return W.evaluate({"values": list(values), "envs": [{"id": eid, "items": items}], "lang": "de", "angle": angle})["envs"][eid]


def value(env, i):
    return (env["lines"][f"l{i}"].get("result") or {}).get("value")


def newton(**kw):
    return {"id": "K", "type": "card", "eq": "dyn_newton", "vars": {}, **kw}


class Derivatives(unittest.TestCase):
    def test_prime_of_a_function(self):
        e = page(["f(x) = x^2", "f'(x)", "f''(x)", "f'(3)"])
        self.assertEqual(e["lines"]["l1"]["kind"], "symbolic")
        self.assertIn("2<i>x</i>", e["lines"]["l1"]["partial_html"])
        self.assertEqual(value(e, 2), 2)
        self.assertEqual(value(e, 3), 6)

    def test_prime_at_a_page_value_equals_the_numeric_derivative(self):
        e = page(["f(x) = sin(x^2)", "x = 1.2", "f'(x)", "deriv(f(x), x, 1.2)"])
        self.assertAlmostEqual(value(e, 2), value(e, 3), places=7)

    def test_diff_forms(self):
        e = page(["x = 2", "diff(x^3, x)", "diff(x^3, x, 2)"])
        self.assertEqual(value(e, 1), 12)
        self.assertEqual(value(e, 2), 12)

    def test_function_of_a_derivative(self):
        e = page(["f(x) = x^2", "g(x) = f'(x)", "g(4)"])
        self.assertIn("2<i>x</i>", e["lines"]["l1"]["html"])
        self.assertEqual(value(e, 2), 8)

    def test_equation_with_a_prime(self):
        e = page(["f(x) = x^2", "f'(x) = 3"])
        self.assertEqual(e["lines"]["l1"]["kind"], "solve")
        self.assertAlmostEqual(e["lines"]["l1"]["sets"][0]["store"], 1.5)

    def test_units_divide_by_the_variable(self):
        t = [{"id": "t", "sym": "t", "kind": "time", "value": "2", "unit": "s", "scope": "all"}]
        e = page(["s(t) = 3*t^2", "s'(t)", "diff(t^3, t)", "diff(t^3, t, 2)"], t)
        self.assertEqual((value(e, 1), e["lines"]["l1"]["unit"]), (12, "s"))
        self.assertEqual((value(e, 2), e["lines"]["l2"]["unit"]), (12, "s²"))
        self.assertEqual((value(e, 3), e["lines"]["l3"]["unit"]), (12, "s"))

    def test_no_rule_shows_a_note(self):
        e = page(["x = 2", "h = diff(gamma(x), x)"])
        self.assertTrue(any("numerisch" in n for n in e["lines"]["l1"]["notes"]))

    def test_degrees(self):
        e = page(["x = 30", "diff(sin(x), x)"], angle="deg")
        self.assertAlmostEqual(value(e, 1), 0.015114994701951816, places=10)


class GraphDerivatives(unittest.TestCase):
    ROWS = [{"id": 1, "src": "f(x) = x^3"}, {"id": 2, "src": "f'(x)"}, {"id": 3, "src": "y = f''(x)"},
            {"id": 4, "src": "diff(sin(x^2), x)"}, {"id": 5, "src": "f'(2)"}]
    VIEW = {"xmin": -2, "xmax": 2}

    def test_curves_with_the_derived_term(self):
        o = G.compute({"rows": self.ROWS, "view": self.VIEW})["rows"]
        self.assertEqual((o["2"]["type"], o["2"]["legend"]), ("curve", "3·x^2"))
        self.assertEqual((o["3"]["type"], o["3"]["legend"]), ("curve", "6·x"))
        self.assertEqual(o["4"]["legend"], "2·x·cos(x^2)")
        self.assertIn("3<i>x</i><sup>2</sup>", o["2"]["html"])
        self.assertAlmostEqual(o["2"]["y"][0], 12.0)
        self.assertAlmostEqual(o["3"]["y"][0], -12.0)
        self.assertEqual((o["5"]["type"], o["5"]["value"]), ("value", 12.0))

    def test_row_order_does_not_matter(self):
        o = G.compute({"rows": list(reversed(self.ROWS)), "view": self.VIEW})["rows"]
        self.assertEqual(o["2"]["legend"], "3·x^2")

    def test_report_legend(self):
        import matplotlib.pyplot as plt
        fig, data, _ = G.figure({"rows": self.ROWS, "view": self.VIEW}, {}, "de")
        plt.close(fig)
        self.assertIn("f'(x) = 3·x^2", [d["label"] for d in data])


class CardButtons(unittest.TestCase):
    VALS = {"F": ("6", "N"), "m": ("2", "kg"), "a": ("3", "m/s²")}

    def test_each_quantity_can_be_the_target(self):
        for t, si in (("F", 6.0), ("m", 2.0), ("a", 3.0)):
            with self.subTest(t):
                card = newton(target=t, vars={s: {"value": v, "unit": u} for s, (v, u) in self.VALS.items()})
                c = page([], cards=[card])["cards"][0]
                self.assertEqual((c["status"], c["target"]), ("ok", t))
                self.assertAlmostEqual(c["result"]["si"], si)

    def test_the_others_are_asked_for(self):
        c = page([], cards=[newton(target="a", vars={"m": {"value": "2", "unit": "kg"}})])["cards"][0]
        self.assertEqual(c["status"], "missing")
        self.assertEqual([m["sym"] for m in c["missing"]], ["F"])

    def test_page_has_no_target_dropdown(self):
        html = (ROOT / "rechner" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('<select class="tgt"', html)
        self.assertIn('class="vbtn f" data-tgt=', html)


class PageValues(unittest.TestCase):
    def test_unit_lines(self):
        e = page(["L = 2 km", "v = 72 km/h", "T = 20 °C", "t = L/v"])
        self.assertEqual(value(e, 0), 2000)
        self.assertEqual(e["lines"]["l0"]["unit"], "m")
        self.assertAlmostEqual(value(e, 1), 20)
        self.assertAlmostEqual(value(e, 2), 293.15)
        self.assertAlmostEqual(value(e, 3), 100)
        self.assertEqual(e["lines"]["l3"]["unit"], "s")

    def test_algebra_stays_algebra(self):
        for src in ("y = 2a", "y = 2t", "y = 2 a", "y = 3 x"):
            self.assertIsNone(W.parse_qty(src), src)
        e = page(["m = 3", "y = 2 m"])                      # a name of the page goes before the unit
        self.assertEqual(value(e, 1), 6)
        self.assertIsNone(e["lines"]["l1"].get("unit"))

    def test_line_feeds_a_card(self):
        card = newton(vars={"a": {"value": "3", "unit": "m/s²"}})
        e = page(["m = 2 kg"], cards=[card])
        c = e["cards"][0]
        self.assertEqual((c["status"], c["target"]), ("ok", "F"))
        self.assertAlmostEqual(c["result"]["si"], 6)
        self.assertEqual(next(v for v in c["vars"] if v["sym"] == "m")["src"], "line:m")

    def test_typed_value_overrides_the_line(self):
        card = newton(vars={"m": {"value": "5", "unit": "kg"}, "a": {"value": "3", "unit": "m/s²"}})
        c = page(["m = 2 kg"], cards=[card])["cards"][0]
        self.assertAlmostEqual(c["result"]["si"], 15)
        self.assertEqual(next(v for v in c["vars"] if v["sym"] == "m")["src"], "manual")

    def test_a_variable_goes_before_the_line(self):
        val = [{"id": "v1", "sym": "m", "kind": "mass", "value": "7", "unit": "kg", "scope": "all"}]
        card = newton(vars={"a": {"value": "1", "unit": "m/s²"}})
        c = page(["w = 2 kg"], val, cards=[card])["cards"][0]
        self.assertAlmostEqual(c["result"]["si"], 7)

    def test_wrong_dimension_is_not_taken(self):
        card = newton(vars={"a": {"value": "3", "unit": "m/s²"}})
        c = page(["m = 2 s"], cards=[card])["cards"][0]
        self.assertEqual(c["status"], "missing")

    def test_explicit_choice_of_a_line(self):
        card = newton(vars={"m": {"bind": "line:w"}, "a": {"value": "2", "unit": "m/s²"}})
        c = page(["w = 4 kg"], cards=[card])["cards"][0]
        self.assertAlmostEqual(c["result"]["si"], 8)
        self.assertIn("w", next(v for v in c["vars"] if v["sym"] == "m")["page"])

    def test_card_result_flows_back_into_lines(self):
        card = newton(vars={"a": {"value": "3", "unit": "m/s²"}})
        e = page(["m = 2 kg", "G = F*2"], cards=[card])
        self.assertAlmostEqual(value(e, 1), 12)
        self.assertEqual(e["lines"]["l1"]["unit"], "N")

    def test_uncertainty_on_a_unit_line(self):
        items = [calc(0, "m = 2 kg", unc={"parts": [{"kind": "u", "u": 0.1}]}), calc(1, "w = 3*m")]
        e = W.evaluate({"values": [], "envs": [{"id": "e", "items": items}], "lang": "de"})["envs"]["e"]
        self.assertAlmostEqual(e["lines"]["l1"]["unc"]["u"], 0.3, places=6)


class Exports(unittest.TestCase):
    def run_two(self, a, b):
        return W.evaluate({"values": [], "envs": [{"id": "A", "items": a}, {"id": "B", "items": b}], "lang": "de"})

    def test_card_result_goes_to_the_other_sheet(self):
        card = newton(export=True, vars={"m": {"value": "2", "unit": "kg"}, "a": {"value": "3", "unit": "m/s²"}})
        o = self.run_two([card], [calc(0, "G = F + 1 N"), calc(1, "H = F*2")])
        self.assertEqual(o["exports"]["F"], {"env": "A", "line": "K", "unit": "N", "card": True})
        self.assertAlmostEqual(o["envs"]["B"]["lines"]["l1"]["result"]["value"], 12)
        self.assertEqual(o["envs"]["B"]["lines"]["l1"]["unit"], "N")

    def test_without_the_flag_nothing_goes(self):
        card = newton(vars={"m": {"value": "2", "unit": "kg"}, "a": {"value": "3", "unit": "m/s²"}})
        self.assertEqual(self.run_two([card], [])["exports"], {})

    def test_export_feeds_a_card_on_the_other_sheet(self):
        card = newton(export=True, vars={"m": {"value": "2", "unit": "kg"}, "a": {"value": "3", "unit": "m/s²"}})
        other = {"id": "K2", "type": "card", "eq": "dyn_newton", "target": "a", "vars": {"m": {"value": "4", "unit": "kg"}}}
        c = self.run_two([card], [other])["envs"]["B"]["cards"][0]
        self.assertAlmostEqual(c["result"]["si"], 1.5)

    def test_solved_quantity_keeps_its_unit(self):
        a = [calc(0, "w = 2 m"), calc(1, "S2 = 6 m^2"), calc(2, "w*z = S2", export=True)]
        o = self.run_two(a, [calc(0, "q = z*2")])
        self.assertEqual(o["exports"]["z"]["unit"], "m")
        self.assertEqual(o["envs"]["A"]["lines"]["l2"]["sets"][0]["unit"], "m")
        self.assertAlmostEqual(o["envs"]["B"]["lines"]["l0"]["result"]["value"], 6)

    def test_line_keeps_u(self):
        runs, ex = W.run_all({"values": [], "lang": "de"}, [{"id": "A", "items": [calc(0, "x = 5,0 ± 0,1 mm", export=True)]}])
        self.assertAlmostEqual(ex["x"]["u"], 1e-4)


class MatrixResults(unittest.TestCase):
    A = "A = [[1, 2], [3, 4]]"

    def test_adjugate(self):
        e = page([self.A, "D = adj(A)", "A*D"])
        self.assertEqual(value(e, 1), [[4, -2], [-3, 1]])
        self.assertEqual(value(e, 2), [[-2, 0], [0, -2]])           # A·adj(A) = det(A)·E

    def test_product_assigned_to_a_free_name(self):
        e = page([self.A, "B = [[0, 1], [1, 0]]", "A*B = C", "C"])
        self.assertEqual((e["lines"]["l2"]["kind"], e["lines"]["l2"]["name"]), ("assign", "C"))
        self.assertEqual(value(e, 3), [[2, 1], [4, 3]])

    def test_defined_name_is_assigned_again_in_a_line(self):
        e = page([self.A, "C = eye(2)", "A*A = C", "C"])
        self.assertEqual(value(e, 3), [[7, 10], [15, 22]])

    def test_stored_scalar_and_matrix_are_usable(self):
        r = W.evaluate({"values": [], "vars": {"d": -2.0, "D": [[4, -2], [-3, 1]]},
                        "envs": [{"id": "e", "items": [calc(0, "d*2"), calc(1, "D[1, 1]")]}], "lang": "de"})["envs"]["e"]
        self.assertEqual(value(r, 0), -4)
        self.assertEqual(value(r, 1), 4)


class ComplexValues(unittest.TestCase):
    R = "R = [[0, -1], [1, 0]]"

    @staticmethod
    def cells(env, i):
        return env["lines"][f"l{i}"]["result"].get("cells")

    def test_complex_eigenvalues_survive_storage(self):
        e = page([self.R, "L = eig(R)", "L", "L*2", "L[1]"])
        self.assertEqual(self.cells(e, 1), ["1i", "-1i"])
        self.assertEqual(self.cells(e, 2), ["1i", "-1i"])
        self.assertEqual(self.cells(e, 3), ["2i", "-2i"])
        self.assertEqual(e["lines"]["l4"]["result"]["value"], [0.0, 1.0])

    def test_store_round_trip(self):
        for v in (np.array([1j, -1j]), np.array([[1 + 2j, 0], [3, 4j]]), np.array([1.5, 2.0])):
            back = E.from_json(E.to_json(v))
            np.testing.assert_array_equal(back, v)
            self.assertEqual(np.iscomplexobj(back), np.iscomplexobj(v))

    def test_complex_eigenvectors_keep_their_imaginary_part(self):
        e = page([self.R, "V = eigvec(R)", "R*V[1, 1]"])
        self.assertTrue(any("i" in c for row in self.cells(e, 1) for c in row))

    def test_report_text_shows_the_complex_values(self):
        e = page([self.R, "L = eig(R)"])
        self.assertIn(r"\mathrm{i}", e["lines"]["l1"]["result_tex"])

    def test_functions_for_real_numbers_refuse(self):
        e = page([self.R, "L = eig(R)", "sort(L)", "gamma(L)"])
        for i in (2, 3):
            self.assertIn("komplex", e["lines"][f"l{i}"]["error"].lower())

    def test_export_to_another_sheet_stays_complex(self):
        a = [calc(0, self.R), calc(1, "L = eig(R)", export=True)]
        o = W.evaluate({"values": [], "envs": [{"id": "A", "items": a}, {"id": "B", "items": [calc(0, "L*3")]}], "lang": "de"})
        self.assertEqual(o["envs"]["B"]["lines"]["l0"]["result"]["cells"], ["3i", "-3i"])

    def test_real_eigenvalues_stay_plain_numbers(self):
        e = page(["A = [[2, 0], [0, 3]]", "L = eig(A)"])
        self.assertEqual(value(e, 1), [2, 3])


class UnitsAndPageNames(unittest.TestCase):
    def test_compound_unit_stays_a_unit(self):
        e = page(["m = 2 kg", "a = 3 m/s^2", "F = m*a"])
        self.assertEqual((value(e, 1), e["lines"]["l1"]["unit"]), (3, "m/s²"))
        self.assertNotIn("notes", e["lines"]["l1"])
        self.assertAlmostEqual(value(e, 2), 6)
        self.assertEqual(e["lines"]["l2"]["unit"], "N")

    def test_simple_unit_stays_the_variable_with_a_note(self):
        e = page(["m = 2 kg", "L = 3 m"])
        self.assertEqual((value(e, 1), e["lines"]["l1"]["unit"]), (6, "kg"))
        note = " ".join(e["lines"]["l1"]["notes"])
        self.assertIn("Variable", note)
        self.assertIn("L = 3 [m]", note)

    def test_note_in_english(self):
        r = W.evaluate({"values": [], "envs": [{"id": "e", "items": [calc(0, "m = 2 kg"), calc(1, "L = 3 m")]}], "lang": "en"})
        self.assertIn("L = 3 [m]", " ".join(r["envs"]["e"]["lines"]["l1"]["notes"]))

    def test_brackets_ask_for_the_unit(self):
        e = page(["m = 2 kg", "L = 3 [m]", "A = 2 [m^2]", "t = 3 [t]"])
        self.assertEqual((value(e, 1), e["lines"]["l1"]["unit"]), (3, "m"))
        self.assertEqual((value(e, 2), e["lines"]["l2"]["unit"]), (2, "m²"))
        self.assertEqual((value(e, 3), e["lines"]["l3"]["unit"]), (3000, "kg"))

    def test_algebra_with_page_names_stays_algebra(self):
        e = page(["a = 2", "t = 3", "s = 0.5 a t^2", "m = 3", "y = 2 m^2"])
        self.assertAlmostEqual(value(e, 2), 9)
        self.assertEqual(value(e, 4), 18)
        self.assertTrue(e["lines"]["l2"]["notes"])
        self.assertTrue(e["lines"]["l4"]["notes"])

    def test_algebra_with_one_page_name(self):
        e = page(["a = 2", "s = 0.5 a t^2"])
        self.assertEqual(e["lines"]["l1"]["kind"], "symbolic")
        self.assertTrue(e["lines"]["l1"]["notes"])

    def test_no_note_without_a_collision(self):
        e = page(["L = 3 m", "v = 5 km/h"])
        self.assertEqual((value(e, 0), e["lines"]["l0"]["unit"]), (3, "m"))
        self.assertNotIn("notes", e["lines"]["l0"])
        self.assertNotIn("notes", e["lines"]["l1"])


class AdjacentMatrixNames(unittest.TestCase):
    A, B = "A = [[1, 2], [3, 4]]", "B = [[0, 1], [1, 0]]"
    AB = [[2, 1], [4, 3]]

    def test_product_is_assigned(self):
        e = page([self.A, self.B, "AB = C", "C"])
        self.assertEqual((e["lines"]["l2"]["kind"], e["lines"]["l2"]["name"]), ("assign", "C"))
        self.assertEqual(value(e, 3), self.AB)
        self.assertTrue(any("A·B" in n for n in e["lines"]["l2"]["notes"]))

    def test_definitions_may_stand_below(self):
        e = page(["AB = C", "C", self.A, self.B])
        self.assertEqual(value(e, 1), self.AB)

    def test_written_the_other_way(self):
        e = page([self.A, self.B, "C = AB"])
        self.assertEqual(value(e, 2), self.AB)

    def test_three_factors(self):
        e = page([self.A, self.B, "ABA = D", "D"])
        self.assertEqual(value(e, 3), (np.array(self.AB) @ np.array([[1, 2], [3, 4]])).tolist())

    def test_a_defined_name_wins(self):
        e = page([self.A, self.B, "AB = [[9, 9], [9, 9]]", "AB = C", "C"])
        self.assertEqual(e["lines"]["l3"]["name"], "C")
        self.assertEqual(value(e, 4), [[9, 9], [9, 9]])                         # the defined AB, not A*B

    def test_right_side_defined_later_is_no_product(self):
        e = page([self.A, self.B, "AB = C", "C = 5", "AB"])
        self.assertEqual(e["lines"]["l2"]["name"], "AB")
        self.assertEqual(value(e, 4), 5)

    def test_scalars_and_ordinary_names_are_left_alone(self):
        e = page(["a = 2", "b = 3", "ab = c", "Masse = 4", "Volumen = Masse"])
        self.assertEqual(e["lines"]["l2"]["name"], "ab")
        self.assertEqual(e["lines"]["l2"]["kind"], "symbolic")
        self.assertEqual(value(e, 4), 4)

    def test_matrix_tab(self):
        r = CON.evaluate_safe({"line": "AB = C", "vars": {"A": [[1, 2], [3, 4]], "B": [[0, 1], [1, 0]]}, "lang": "de"})
        self.assertEqual((r["kind"], r["name"], r["store"]), ("assign", "C", self.AB))


class MatrixFunctionsAssign(unittest.TestCase):
    A = "A = [[1, 2], [3, 4]]"
    V = {"A": [[1, 2], [3, 4]], "S": [[1, 2], [2, 4]], "b": [[5], [6]]}

    def ev(self, line, **vars_):
        return CON.evaluate_safe({"line": line, "vars": {**self.V, **vars_}, "lang": "de", "digits": 10})

    def test_free_name_on_the_right(self):
        for fn in ("inv", "adj", "eig", "rref", "cof", "eigvec"):
            with self.subTest(fn):
                e = page([self.A, f"{fn}(A) = Q", "Q", f"{fn}(A)"])
                self.assertEqual((e["lines"]["l1"]["kind"], e["lines"]["l1"]["name"]), ("assign", "Q"))
                np.testing.assert_allclose(value(e, 2), value(e, 3))

    def test_number_on_the_left(self):
        e = page([self.A, "det(A) = d", "d*2"])
        self.assertEqual(e["lines"]["l1"]["kind"], "assign")
        self.assertAlmostEqual(value(e, 2), -4)

    def test_matrix_tab_assigns_and_protects(self):
        r = self.ev("inv(A) = Q")
        self.assertEqual((r["kind"], r["name"]), ("assign", "Q"))
        self.assertEqual(self.ev("rref(A) = Q")["store"], [[1, 0], [0, 1]])
        kept = self.ev("adj(A) = Q", Q=[[1.0]])
        self.assertEqual((kept["kind"], kept["name"]), ("assign", "Q"))         # the page keeps Q until "Store"

    def test_a_number_against_a_defined_name_stays_a_check(self):
        self.assertEqual(self.ev("det(A) = q", q=-2.0)["kind"], "check")

    def test_solve_for_a_matrix(self):
        e = page([self.A, "b = [[5], [6]]", "A*x = b", "x", "A*x"])
        np.testing.assert_allclose(value(e, 3), [[-4], [4.5]])
        np.testing.assert_allclose(value(e, 4), [[5], [6]])

    def test_solve_for_a_square_matrix(self):
        e = page([self.A, "B = [[0, 1], [1, 0]]", "A*X = B", "X", "A*X"])
        self.assertEqual(e["lines"]["l2"]["name"], "X")
        np.testing.assert_allclose(value(e, 4), [[0, 1], [1, 0]], atol=1e-12)

    def test_unknown_on_the_right_of_the_product(self):
        e = page([self.A, "B = [[0, 1], [1, 0]]", "X*A = B", "X*A"])
        np.testing.assert_allclose(value(e, 3), [[0, 1], [1, 0]], atol=1e-12)

    def test_vector_right_hand_side(self):
        e = page([self.A, "A*x = [5, 6]", "x"])
        np.testing.assert_allclose(value(e, 2), [-4, 4.5])

    def test_overdetermined_but_consistent(self):
        e = page(["M = [[1, 0], [0, 1], [1, 1]]", "M*x = [[1], [2], [3]]", "x"])
        np.testing.assert_allclose(value(e, 2), [[1], [2]])

    def test_singular_with_many_solutions_is_said_plainly(self):
        r = self.ev("S*X = [[1], [2]]")
        self.assertIn("singulär", r["error"])
        self.assertIn("unendlich viele", r["error"])

    def test_inconsistent_system_is_said_plainly(self):
        r = self.ev("S*X = [[1], [3]]")
        self.assertIn("Keine Lösung", r["error"])

    def test_sizes_that_do_not_fit(self):
        self.assertIn("passen nicht", self.ev("A*X = [[1], [2], [3]]")["error"])

    def test_units_divide(self):
        e = page(["A = [[2, 0], [0, 2]]", "b = [3, 4]", "A*x = b", "x"])
        np.testing.assert_allclose(value(e, 3), [1.5, 2])

    def test_scalar_equations_still_solve(self):
        e = page(["k = 4", "2*x = k"])
        self.assertEqual(e["lines"]["l1"]["sets"][0]["store"], 2)

    def test_api_never_raises(self):
        for line in ("", "1 +", "inv([[1, 2], [2, 4]])", "A + [1, 2, 3]", "unknown_fn(2)", "AB = ", "[[1, 2], [3]]"):
            with self.subTest(line):
                self.assertIn("error", self.ev(line))
        self.assertEqual(CON.evaluate_safe({"line": "zz = yy + 1", "vars": {}, "lang": "de", "partial": True}).get("_node"), None)

    def test_cof_button(self):
        html = (ROOT / "rechner" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("`cof(${a})`", html)


class TypedDerivatives(unittest.TestCase):
    def test_rewrite(self):
        for src, want in (("d/dx(x^3)", "diff(x^3, x)"), ("d/dt(t^2 + 1)", "diff(t^2 + 1, t)"), ("d²/dx²(x^4)", "diff(x^4, x, 2)"),
                          ("d^2/dx^2(x^4)", "diff(x^4, x, 2)"), ("2*d/dx(x^3) + 1", "2*diff(x^3, x) + 1"),
                          ("d/dx x^3 + 1", "diff(x^3, x) + 1"), ("y = d/dx(d/dx(x^3))", "y = diff(diff(x^3, x), x)"),
                          ("d/dθ(sin(θ))", "diff(sin(θ), θ)")):
            self.assertEqual(E.rewrite_ddx(src), want)

    def test_a_real_quotient_stays(self):
        self.assertEqual(E.rewrite_ddx("d/dx(2)", {"d", "dx"}), "d/dx(2)")
        self.assertEqual(E.rewrite_ddx("d/dose(3)"), "d/dose(3)")
        self.assertEqual(E.rewrite_ddx("add/dx(3)"), "add/dx(3)")
        e = page(["d = 6", "dx = 2", "d/dx(1)"])
        self.assertEqual(value(e, 2), 3)

    def test_in_a_line(self):
        e = page(["d/dx(x^3)"])
        self.assertEqual(e["lines"]["l0"]["kind"], "symbolic")
        self.assertIn("3<i>x</i><sup>2</sup>", e["lines"]["l0"]["partial_html"])
        e = page(["x = 2", "d/dx(x^3)", "w = d/dx(x^3)"])
        self.assertEqual(value(e, 1), 12)
        self.assertEqual(value(e, 2), 12)

    def test_order_of_the_lines(self):
        e = page(["d/dx(x^3)", "x = 2"])
        self.assertEqual(value(e, 0), 12)


class GraphCurveDerivatives(unittest.TestCase):
    VIEW = {"xmin": -2, "xmax": 2}

    def rows(self, *src):
        return G.compute({"rows": [{"id": i + 1, "src": s} for i, s in enumerate(src)], "view": self.VIEW})["rows"]

    def test_typed_derivative(self):
        o = self.rows("d/dx(x^3)")
        self.assertEqual((o["1"]["type"], o["1"]["legend"]), ("curve", "3·x^2"))

    def test_y_prime_and_diff_of_a_curve(self):
        o = self.rows("y = x^3", "y'", "diff(y, x)", "y''", "diff(y, x, 2)")
        for k, term in (("2", "3·x^2"), ("3", "3·x^2"), ("4", "6·x"), ("5", "6·x")):
            self.assertEqual((o[k]["type"], o[k]["legend"]), ("curve", term), k)
        self.assertAlmostEqual(o["2"]["y"][0], 12.0)
        self.assertEqual(o["1"]["type"], "curve")

    def test_curve_below_and_nearest_above(self):
        o = self.rows("y'", "y = x^2")
        self.assertEqual(o["1"]["legend"], "2·x")
        o = self.rows("y = x^2", "y'", "y = x^3", "y'")
        self.assertEqual((o["2"]["legend"], o["4"]["legend"]), ("2·x", "3·x^2"))

    def test_curve_with_a_slider(self):
        o = self.rows("a = 2", "y = a*x^2", "y'")
        self.assertEqual(o["3"]["type"], "curve")
        self.assertAlmostEqual(o["3"]["y"][0], -8.0)

    def test_without_a_curve_y_prime_is_an_error(self):
        self.assertEqual(self.rows("y'")["1"]["type"], "error")

    def test_constant_derivative_shows_its_term(self):
        o = self.rows("f(x) = x^2", "f''(x)", "f'''(x)", "y = f''(x)", "g(t) = f''(t)")
        self.assertEqual((o["2"]["type"], o["2"]["legend"]), ("curve", "2"))
        self.assertEqual(o["3"]["legend"], "0")
        self.assertEqual(o["4"]["legend"], "2")
        self.assertEqual(o["5"]["legend"], "2")
        self.assertAlmostEqual(o["2"]["y"][0], 2.0)

    def test_value_at_a_point_stays_a_value(self):
        o = self.rows("f(x) = x^2", "f'(2)")
        self.assertEqual((o["2"]["type"], o["2"]["value"]), ("value", 4.0))
        self.assertNotIn("legend", o["2"])

    def test_implicit_curves_keep_their_y(self):
        o = self.rows("x^2 + y^2 = 4", "y = x")
        self.assertEqual(o["1"]["type"], "implicit")


class StoredComplexMatrices(unittest.TestCase):
    """What the Matrices tab keeps: {re, im} cells, through JSON, as the page saves and reloads them."""
    R = [[0, -1], [1, 0]]

    def stored(self):
        ev = lambda line: CON.evaluate_safe({"line": line, "vars": {"R": self.R}, "lang": "de"})["store"]
        return json.loads(json.dumps({"R": self.R, "L": ev("eig(R)"), "V": ev("eigvec(R)"),
                                      "M": [[{"re": 1.0, "im": 1.0}, 2.0], [3.0, {"re": 0.0, "im": 4.0}]],
                                      "z": {"re": 1.0, "im": 2.0}}))

    def ev(self, line):
        return CON.evaluate_safe({"line": line, "vars": self.stored(), "lang": "de", "complex": True})

    def test_store_survives_save_and_reload(self):
        s = self.stored()
        np.testing.assert_array_equal(E.from_json(s["L"]), [1j, -1j])
        self.assertEqual(E.to_json(E.from_json(s["M"])), s["M"])
        self.assertEqual(E.to_json(E.from_json(s["z"])), s["z"])

    def test_usable_from_lines_on_every_sheet(self):
        items = [calc(0, "W = M*2"), calc(1, "L*2"), calc(2, "z + 1")]
        o = W.evaluate({"values": [], "vars": self.stored(), "envs": [{"id": "e", "items": items}], "lang": "de"})
        lines = o["envs"]["e"]["lines"]
        self.assertEqual(lines["l0"]["result"]["cells"], [["2 + 2i", "4"], ["6", "8i"]])
        self.assertEqual(lines["l1"]["result"]["cells"], ["2i", "-2i"])
        self.assertEqual(lines["l2"]["result"]["text"], "2 + 2i")

    def test_operations_keep_the_imaginary_part(self):
        A = np.array([[1 + 1j, 2], [3, 4j]])
        for line, want in (("det(M)", np.linalg.det(A)), ("trace(M)", np.trace(A)), ("sum(L)", 0), ("sum(M)", A.sum()), ("prod(M)", A.prod())):
            with self.subTest(line):
                np.testing.assert_allclose(E.from_json(self.ev(line)["store"]), want, atol=1e-12)
        for line, want in (("inv(M)", np.linalg.inv(A)), ("adj(M)", np.linalg.det(A) * np.linalg.inv(A)), ("M*M", A @ A), ("M'", A.T)):
            with self.subTest(line):
                np.testing.assert_allclose(E.from_json(self.ev(line)["store"]), want, atol=1e-12)

    def test_a_result_can_be_stored_again(self):
        r = self.ev("Q = M*2")
        self.assertEqual((r["kind"], r["name"]), ("assign", "Q"))
        self.assertEqual(r["store"][0][0], {"re": 2.0, "im": 2.0})
        self.assertIsNone(r["result"]["value"])

    def test_real_only_functions_refuse_instead_of_rounding(self):
        for line in ("max(L)", "min(M)", "median(L)", "floor(z)", "mod(z, 2)", "gcd(L, 2)", "eye(z)", "z > 1", "sort(L)", "dot(L, L)",
                     "integral(z*x, x, 0, 1)", "deriv(z*x^2, x, 1)", "nsolve(z*x == 1, x, 1)", "sum(z*k, k, 1, 3)", "prod(z, k, 1, 2)"):
            with self.subTest(line):
                self.assertIn("komplex", self.ev(line).get("error", ""))

    def test_complex_root_is_the_principal_value(self):
        np.testing.assert_allclose(E.from_json(self.ev("root(z, 3)")["store"]) ** 3, 1 + 2j)

    def test_real_values_are_untouched(self):
        V = {"A": [[2.0, 1.0], [1.0, 3.0]]}
        for line, want in (("det(A)", 5.0), ("trace(A)", 5.0), ("sum(A)", 7.0), ("root(27, 3)", 3.0), ("root(-8, 3)", -2.0), ("max(A)", 3.0)):
            r = CON.evaluate_safe({"line": line, "vars": V, "lang": "de"})
            self.assertIsInstance(r["store"], float, line)
            self.assertAlmostEqual(r["store"], want, msg=line)

    def test_report_bundle(self):
        s = self.stored()
        req = {"values": [], "vars": s, "matrices": {k: s[k] for k in ("L", "V", "M", "R")},
               "envs": [{"id": "e", "name": "Blatt", "items": [calc(0, "W = M*2", report=True), calc(1, "L*2", report=True)]}]}
        for lang in ("de", "en"):
            b = B.build(json.loads(json.dumps(req)), lang=lang)
            tex = base64.b64decode(b["files"]["text-matrizen.tex"]).decode("utf-8")
            self.assertIn(r"1 + 1\,\mathrm{i}", tex)
            self.assertIn(r"4\,\mathrm{i}", tex)


class NameSolvedByTwoLines(unittest.TestCase):
    PAGE = ["k = 4", "x^2 = k", "x + y = k; x - y = 2"]

    def test_message_names_the_name_and_the_lines(self):
        e = page(self.PAGE)
        for i in (1, 2):
            msg = e["lines"][f"l{i}"]["error"]
            self.assertIn("x wird von zwei Zeilen bestimmt (Zeilen 2 und 3)", msg)
            self.assertNotIn("Zirkelbezug", msg)
        self.assertEqual(value(e, 0), 4)

    def test_english(self):
        items = [calc(i, s) for i, s in enumerate(self.PAGE)]
        o = W.evaluate({"values": [], "envs": [{"id": "e", "items": items}], "lang": "en"})
        msg = o["envs"]["e"]["lines"]["l1"]["error"]
        self.assertIn("x is determined by two lines (lines 2 and 3)", msg)
        self.assertNotIn("Circular", msg)

    def test_a_real_cycle_stays_a_cycle(self):
        for lines in (["a = b + 1", "b = a + 1"], ["x + 1 = y", "y + 1 = x"], ["x^2 = k", "x + y = k; x - y = 2"]):
            with self.subTest(lines):
                self.assertIn("Zirkelbezug", page(lines)["lines"]["l0"]["error"])

    def test_both_kinds_on_one_page(self):
        e = page([*self.PAGE, "a = b + 1", "b = a + 1"])
        self.assertIn("x wird von zwei Zeilen", e["lines"]["l1"]["error"])
        self.assertIn("Zirkelbezug: a, b", e["lines"]["l3"]["error"])
        self.assertIn("Zeilen 4, 5", e["lines"]["l3"]["error"])

    def test_valid_pages_keep_their_order(self):
        e = page(["k = 4", "z^2 = k", "x + y = k; x - y = 2", "w = x + y"])
        self.assertEqual(e["lines"]["l1"]["kind"], "solve")
        self.assertEqual(e["lines"]["l2"]["kind"], "system")
        self.assertEqual(value(e, 3), 4)


class LibraryStillSolves(unittest.TestCase):
    def test_equation_exists(self):
        self.assertIn("dyn_newton", L.BY_ID)
        self.assertEqual({v["kind"] for v in L.BY_ID["dyn_newton"].vars}, {"force", "mass", "acceleration"})
        self.assertTrue(U.KINDS["mass"].dims)


if __name__ == "__main__":
    unittest.main()
