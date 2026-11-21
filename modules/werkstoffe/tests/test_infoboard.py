"""Info board: pins, snapshots, boards per project, report export with sources per statement, and the page script."""
import base64
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from labproject import ModuleEnvs  # noqa: E402
from werk import bundle as B, infoboard as IB, kompendium as KP, tools as T  # noqa: E402

MAT, MAT2 = "c45e-qt", "en-aw-1050a-weich"
NODE = HERE.parents[2] / "tools" / "node" / ("node.exe" if os.name == "nt" else "node")
STATIC = HERE.parent / "werk" / "static"


def all_statements(lang="de"):
    for e in KP.entries(lang):
        for s in KP.statements_of(e):
            yield e, s


def find_statement(test):
    """First statement satisfying ``test`` that is not a material value."""
    for _, s in all_statements():
        if "prop" not in s and test(s):
            return s["id"]
    raise AssertionError("no such statement in the compendium")


def card(pin, x=0, y=0, frame=None):
    return {**pin, "x": x, "y": y, "w": 260, "h": 80, **({"frame": frame} if frame else {})}


def frame(fid, name, x=0):
    return {"id": fid, "name": name, "x": x, "y": 0, "w": 800, "h": 600}


def build(board, lang="de", leave=(), frame_id=None, include=None):
    req = {"sections": [{"tool": "infotafel", "req": {"board": board, "frame": frame_id, "leave_out": list(leave)}}], "lang": lang, "include": include or {}, "title": None}
    return B.build(req, T.Ctx(), {})


def tex(bundle):
    return {k: base64.b64decode(v).decode("utf-8") for k, v in bundle["files"].items() if k.endswith(".tex")}


def text_of(bundle):
    return "\n".join(tex(bundle).values())


SOFTWARE = "folio-lab-werkstoffe"        # the module's own reference, cited by the methods piece only


def all_bib_keys(bundle):
    return set(re.findall(r"@\w+\{([^,]+),", base64.b64decode(bundle["files"]["refs.bib"]).decode("utf-8"))) if "refs.bib" in bundle["files"] else set()


def bib_keys(bundle):
    return all_bib_keys(bundle) - {SOFTWARE}


def cited(s):
    return set(k for g in re.findall(r"\\cite\{([^}]*)\}", s) for k in g.split(",")) - {SOFTWARE}


class PinTest(unittest.TestCase):
    def test_every_kind_keeps_ids_and_sources(self):
        e = KP.entry("material:" + MAT)
        val = next(s for s in e["statements"] if s.get("prop"))
        sec = next(s for s in KP.entry("tool:xrd")["sections"] if s["statements"])
        specs = [{"kind": "entry", "id": e["id"]}, {"kind": "section", "id": sec["id"]}, {"kind": "statement", "id": "atlas:ferrit.1"}, {"kind": "value", "id": val["id"]},
                 {"kind": "figure", "fig": "atlas", "gef": "perlit"}, {"kind": "figure", "fig": "mech", "mech": "bain", "frame": 5}, {"kind": "compare", "materials": [MAT, MAT2]}]
        for sp in specs:
            with self.subTest(sp):
                p = IB.make_pin(sp, thumb=False)
                self.assertEqual(p["spec"]["kind"], sp["kind"])
                self.assertTrue(p["hash"])
                self.assertEqual(set(p["content"]), {"de", "en"})
                for key, q in p["sources"].items():
                    self.assertIn("rec", q)
                    self.assertIn("status", q)
                if sp["kind"] != "compare":
                    self.assertTrue(p["entry"])
                    KP.entry(p["entry"])
                for s in IB._pin_statements(p):
                    if sp["kind"] != "compare":
                        self.assertEqual(KP.statement(s["id"])["id"], s["id"])

    def test_statement_ids_are_the_same_in_both_languages(self):
        p = IB.make_pin({"kind": "entry", "id": "material:" + MAT}, thumb=False)
        self.assertEqual([s["id"] for s in IB._pin_statements(p, "de")], [s["id"] for s in IB._pin_statements(p, "en")])

    def test_value_keeps_range_and_its_sources(self):
        e = KP.entry("material:" + MAT)
        val = next(s for s in e["statements"] if s.get("prop") and s.get("range"))
        p = IB.make_pin({"kind": "value", "id": val["id"]}, thumb=False)
        s = p["content"]["de"]["blocks"][0]["statements"][0]
        self.assertEqual(s["range"], val["range"])
        self.assertEqual(s["shown"], val["shown"])
        self.assertTrue(set(val["value_keys"] + val["range_keys"]) <= set(p["sources"]))

    def test_a_statement_is_not_a_value(self):
        with self.assertRaises(T.ToolError):
            IB.make_pin({"kind": "value", "id": "atlas:ferrit.1"}, thumb=False)

    def test_unknown_kind_and_id_are_refused(self):
        with self.assertRaises(T.ToolError):
            IB.make_pin({"kind": "nonsense"})
        with self.assertRaises((LookupError, T.ToolError)):
            IB.make_pin({"kind": "statement", "id": "atlas:gibt-es-nicht.1"})

    def test_chart_pin_keeps_view_and_cites_only_what_it_shows(self):
        full = IB.make_pin({"kind": "figure", "fig": "chart", "req": {"x": "rho", "y": "E"}, "view": {}, "limits": None}, thumb=False)
        zoom = IB.make_pin({"kind": "figure", "fig": "chart", "req": {"x": "rho", "y": "E"}, "view": {}, "limits": [2, 3, 60, 90]}, thumb=False)
        self.assertEqual(zoom["spec"]["limits"], [2, 3, 60, 90])
        self.assertTrue(set(zoom["sources"]) < set(full["sources"]), "a zoomed chart cites fewer sources")

    def test_mechanism_frame_is_kept(self):
        a = IB.make_pin({"kind": "figure", "fig": "mech", "mech": "bain", "frame": 2}, thumb=False)
        b = IB.make_pin({"kind": "figure", "fig": "mech", "mech": "bain", "frame": 7}, thumb=False)
        self.assertEqual((a["content"]["de"]["figure"]["frame"], b["content"]["de"]["figure"]["frame"]), (2, 7))
        self.assertNotEqual(a["hash"], b["hash"])

    def test_walk_holds_selected_and_linked_entries_only(self):
        items = IB.walk([MAT, "gibt-es-nicht"])
        self.assertEqual(items[0]["id"], "material:" + MAT)
        linked = {x["id"] for k in ("atlas", "mech") for x in KP.entry("material:" + MAT)["links"][k]}
        self.assertEqual({x["id"] for x in items[1:]}, linked)
        self.assertEqual(len(items), len({x["id"] for x in items}))


class ChangedTest(unittest.TestCase):
    def setUp(self):
        self.pin = IB.make_pin({"kind": "statement", "id": "atlas:ferrit.1"}, thumb=False)

    def test_unchanged_pin_is_ok(self):
        self.assertEqual(IB.state([self.pin])["states"][self.pin["id"]]["state"], "ok")

    def test_changed_text_is_reported(self):
        old = copy.deepcopy(self.pin)
        old["content"]["de"]["blocks"][0]["statements"][0]["text"] += " (alt)"
        old["hash"] = IB._fingerprint(old)
        st = IB.state([old])["states"][old["id"]]
        self.assertEqual(st["state"], "changed")
        self.assertIn("text", st["what"])

    def test_changed_source_status_is_reported(self):
        old = copy.deepcopy(self.pin)
        k = next(iter(old["sources"]))
        old["sources"][k]["status"] = "partial" if old["sources"][k]["status"] != "partial" else "unchecked"
        old["hash"] = IB._fingerprint(old)
        st = IB.state([old])["states"][old["id"]]
        self.assertEqual(st["state"], "changed")
        self.assertIn("check", st["what"])

    def test_removed_entry_is_reported(self):
        old = copy.deepcopy(self.pin)
        old["spec"]["id"] = "atlas:gibt-es-nicht.1"
        self.assertEqual(IB.state([old])["states"][old["id"]]["state"], "missing")

    def test_report_keeps_the_snapshot_until_updated(self):
        old = copy.deepcopy(self.pin)
        old["content"]["de"]["blocks"][0]["statements"][0]["text"] = "Stand beim Anheften."
        old["hash"] = IB._fingerprint(old)
        board = {"id": "b", "name": "T", "frames": [frame("f", "R")], "cards": [card(old, frame="f")]}
        self.assertIn("Stand beim Anheften", text_of(build(board)))
        new = IB.renew({**old, "x": 40, "y": 60, "frame": "f"})
        self.assertEqual((new["id"], new["x"], new["y"], new["frame"]), (old["id"], 40, 60, "f"))
        self.assertNotIn("Stand beim Anheften", json.dumps(new["content"], ensure_ascii=False))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("FOLIO_SUITE_DIR", None)
        self.envs = ModuleEnvs(Path(self.tmp), "werkstoffe")
        reg = self.envs.suite.registry
        reg["projects"].append({"id": "zweites", "name": "Zweites", "reports": [], "created": "2026-01-01"})
        (Path(self.envs.suite.root) / "suite.json").write_text(json.dumps(reg), "utf-8")

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def activate(self, pid):
        reg = self.envs.suite.registry
        reg["active"] = pid
        (Path(self.envs.suite.root) / "suite.json").write_text(json.dumps(reg), "utf-8")

    def test_save_and_load(self):
        got = IB.load(self.envs)
        doc = got["doc"]
        pin = IB.make_pin({"kind": "statement", "id": "atlas:ferrit.1"}, thumb=False)
        doc["boards"][0]["frames"].append(frame("f1", "Rahmen"))
        doc["boards"][0]["cards"] += [card(pin, 20, 40, "f1"), {"id": "n1", "kind": "note", "text": "Notiz", "x": 0, "y": 0, "w": 260, "h": 80}]
        doc["selection"] = [MAT]
        r = IB.save(self.envs, {"project": got["project"], "rev": 0, "doc": doc})
        self.assertTrue(r["ok"])
        back = IB.load(self.envs)["doc"]
        self.assertEqual(back["rev"], 1)
        self.assertEqual(back["selection"], [MAT])
        self.assertEqual(back["boards"][0]["cards"][0]["hash"], pin["hash"])
        self.assertEqual(back["boards"][0]["cards"][0]["frame"], "f1")
        self.assertEqual(back["boards"][0]["cards"][1]["text"], "Notiz")

    def test_boards_are_per_project(self):
        a = IB.load(self.envs)
        a["doc"]["boards"][0]["name"] = "Tafel von A"
        IB.save(self.envs, {"project": a["project"], "rev": 0, "doc": a["doc"]})
        self.activate("zweites")
        b = IB.load(self.envs)
        self.assertEqual(b["project"], "zweites")
        self.assertNotEqual(b["doc"]["boards"][0]["name"], "Tafel von A")

    def test_late_save_goes_to_the_project_it_came_from(self):
        a = IB.load(self.envs)
        self.activate("zweites")
        IB.load(self.envs)
        a["doc"]["boards"][0]["name"] = "Spät gespeichert"
        IB.save(self.envs, {"project": a["project"], "rev": 0, "doc": a["doc"]})
        self.assertNotEqual(IB.load(self.envs)["doc"]["boards"][0]["name"], "Spät gespeichert")
        self.assertEqual(IB.load(self.envs, a["project"])["doc"]["boards"][0]["name"], "Spät gespeichert")

    def test_conflict_is_detected(self):
        a = IB.load(self.envs)
        IB.save(self.envs, {"project": a["project"], "rev": 0, "doc": a["doc"]})
        r = IB.save(self.envs, {"project": a["project"], "rev": 0, "doc": a["doc"]})
        self.assertTrue(r.get("conflict"))
        self.assertEqual(r["doc"]["rev"], 1)

    def test_cards_of_a_lost_frame_become_loose(self):
        a = IB.load(self.envs)
        a["doc"]["boards"][0]["cards"].append({"id": "n1", "kind": "note", "text": "x", "x": 0, "y": 0, "frame": "weg"})
        self.assertNotIn("frame", IB.normalize(a["doc"])["boards"][0]["cards"][0])

    def test_file_is_not_listed_as_an_environment(self):
        a = IB.load(self.envs)
        IB.save(self.envs, {"project": a["project"], "rev": 0, "doc": a["doc"]})
        self.assertTrue(IB.FILE.startswith("_"))
        self.assertFalse(any("infotafeln" in str(x.get("id")) for x in self.envs.envs.list()))


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.unchecked = find_statement(lambda s: s["basis"] == "statement" and s["check"] == "unchecked" and s["keys"])
        cls.open = find_statement(lambda s: s.get("unsourced") == "open")
        cls.partial = next((s["id"] for _, s in all_statements() if "prop" not in s and s["basis"] == "statement" and s["check"] in ("partial", "no_record") and s["keys"]), None)
        cls.p_unch = IB.make_pin({"kind": "statement", "id": cls.unchecked}, thumb=False)
        cls.p_open = IB.make_pin({"kind": "statement", "id": cls.open}, thumb=False)

    def board(self, *cards_, frames=None):
        return {"id": "b", "name": "Tafel", "frames": frames if frames is not None else [frame("f1", "Rahmen")], "cards": list(cards_)}

    def test_frame_order_drives_report_order(self):
        a, b = card(self.p_unch, frame="f1"), card(self.p_open, frame="f2")
        fr = [frame("f2", "Zuerst"), frame("f1", "Danach", 900)]
        bd = build(self.board(a, b, frames=fr))
        texts = [i for i in bd["items"] if i["kind"] == "text" and i["id"] != "methodik"]
        self.assertEqual([i["title"] for i in texts], ["Zuerst", "Danach"])
        rev = build(self.board(a, b, frames=list(reversed(fr))))
        self.assertEqual([i["title"] for i in rev["items"] if i["kind"] == "text" and i["id"] != "methodik"], ["Danach", "Zuerst"])

    def test_pieces_keep_their_order_in_the_hub_section(self):
        bd = build(self.board(card(self.p_unch, frame="f1")))
        pieces = [i for i in bd["items"] if i["kind"] in ("text", "figure", "table")]
        self.assertTrue(pieces and all(i.get("flow") for i in pieces))
        if any(i.get("methods") for i in pieces):
            self.assertTrue(pieces[0].get("methods"))           # the methods text opens the section

    def test_cards_inside_a_frame_follow_reading_order(self):
        low, high = card(self.p_open, 0, 300, "f1"), card(self.p_unch, 0, 0, "f1")
        got = [c["id"] for c in IB.ordered(self.board(low, high))[0][1]]
        self.assertEqual(got, [high["id"], low["id"]])

    def test_single_frame_export(self):
        fr = [frame("f1", "Eins"), frame("f2", "Zwei", 900)]
        bd = build(self.board(card(self.p_unch, frame="f1"), card(self.p_open, frame="f2"), frames=fr), frame_id="f2")
        self.assertEqual([i["title"] for i in bd["items"] if i["kind"] == "text" and i["id"] != "methodik"], ["Zwei"])
        self.assertEqual(bib_keys(bd), set())

    def test_only_pinned_sources_are_cited(self):
        pin = IB.make_pin({"kind": "statement", "id": self.unchecked}, thumb=False)
        bd = build(self.board(card(pin, frame="f1")))
        want = {IB._bibkey(k) for k in KP.statement(self.unchecked)["keys"]}
        self.assertEqual(bib_keys(bd), want)
        self.assertEqual(cited(text_of(bd)), want)

    def test_software_reference_stays_in_the_methods(self):
        bd = build(self.board(card(self.p_unch, frame="f1")))
        for name, body in tex(bd).items():
            if SOFTWARE in body:
                self.assertIn("method", name)

    def test_each_sentence_carries_its_own_citation(self):
        e = KP.entry("atlas:perlit")
        st = [s for s in KP.statements_of(e) if s["keys"] and s.get("unsourced") is None]
        pins = [card(IB.make_pin({"kind": "statement", "id": s["id"]}, thumb=False), 0, k * 100, "f1") for k, s in enumerate(st[:3])]
        body = text_of(build(self.board(*pins)))
        for s in st[:3]:
            frag = B.tx(s["text"].rstrip("."))
            self.assertIn(frag, body)
            after = body[body.index(frag) + len(frag):]
            m = re.match(r"\s*~\\cite\{([^}]*)\}", after)
            self.assertTrue(m, s["id"])
            self.assertEqual(set(m.group(1).split(",")), {IB._bibkey(k) for k in s["keys"]})

    def test_table_cites_the_sources_of_its_values(self):
        val = next(s for s in KP.entry("material:" + MAT)["statements"] if s.get("prop") and s.get("value_keys"))
        p = IB.make_pin({"kind": "value", "id": val["id"]}, thumb=False)
        bd = build(self.board(card(p, frame="f1")))
        tb = next(i for i in bd["items"] if i["kind"] == "table")
        want = {IB._bibkey(k) for k in val["value_keys"] + val["range_keys"]}
        self.assertEqual(set(tb["cites"]), want)
        self.assertEqual(bib_keys(bd), want)

    def test_figure_cites_exactly_its_sources(self):
        p = IB.make_pin({"kind": "figure", "fig": "mech", "mech": "bain", "frame": 3}, thumb=False)
        bd = build(self.board(card(p, frame="f1")))
        fg = next(i for i in bd["items"] if i["kind"] == "figure")
        self.assertEqual(set(fg["cites"]), {IB._bibkey(k) for k in p["content"]["de"]["figure"]["keys"]})

    def test_unchecked_gets_dagger_and_note(self):
        body = text_of(build(self.board(card(self.p_unch, frame="f1"))))
        self.assertIn(IB.DAG, body)
        self.assertIn("nicht am Original geprüft", body)
        self.assertNotIn("nachvollziehbare", body, "the note only explains what occurs")

    def test_open_statement_is_marked_and_has_no_citation(self):
        bd = build(self.board(card(self.p_open, frame="f1")))
        body = text_of(bd)
        self.assertIn("(ohne Quelle)", body)
        self.assertIn(IB.DAG, body)
        self.assertIn("keine nachvollziehbare Quelle", body)
        self.assertEqual(bib_keys(bd), set())

    def test_no_mark_is_never_called_checked(self):
        if not self.partial:
            self.skipTest("no such statement")
        p = IB.make_pin({"kind": "statement", "id": self.partial}, thumb=False)
        body = text_of(build(self.board(card(p, frame="f1"))))
        self.assertNotIn(IB.DAG, body)
        for word in ("geprüft", "verified", "checked"):
            self.assertNotIn(word, body)

    def test_warning_data_lists_flagged_pins(self):
        pl = IB.plan(self.board(card(self.p_unch, frame="f1"), card(self.p_open, frame="f1")))
        by = {x["pin"]: x for x in pl["flagged"]}
        self.assertEqual(set(by), {self.p_unch["id"], self.p_open["id"]})
        self.assertEqual(by[self.p_open["id"]]["n_open"], 1)
        self.assertEqual(by[self.p_unch["id"]]["statements"][0]["reason"], "unchecked")
        self.assertFalse(by[self.p_unch["id"]]["partial"])

    def test_leave_out_drops_the_pin(self):
        a, b = card(self.p_unch, frame="f1"), card(self.p_open, frame="f1")
        bd = build(self.board(a, b), leave=[self.p_open["id"]])
        self.assertNotIn("(ohne Quelle)", text_of(bd))
        self.assertIn(B.tx(KP.statement(self.unchecked)["text"].rstrip(".")), text_of(bd))

    def test_leave_out_on_an_entry_drops_only_its_flagged_statements(self):
        ent = next((x for x in KP.entries("de") if any(IB.flag_of(s) for s in KP.statements_of(x) if "prop" not in s) and any(not IB.flag_of(s) and s.get("keys") and "prop" not in s for s in KP.statements_of(x))), None)
        if not ent:
            self.skipTest("no entry with both kinds of statement")
        p = IB.make_pin({"kind": "entry", "id": ent["id"]}, thumb=False)
        kept = build(self.board(card(p, frame="f1")))
        out = build(self.board(card(p, frame="f1")), leave=[p["id"]])
        self.assertLess(len(text_of(out)), len(text_of(kept)))
        self.assertTrue(any(i["kind"] == "text" for i in out["items"]))

    def test_leaving_everything_out_is_an_error(self):
        with self.assertRaises(T.ToolError):
            build(self.board(card(self.p_open, frame="f1")), leave=[self.p_open["id"]])

    def test_notes_are_uncited_user_text(self):
        note = {"id": "n1", "kind": "note", "text": "Meine Beobachtung 50 % & mehr", "x": 0, "y": 0, "w": 260, "h": 80, "frame": "f1"}
        bd = build(self.board(note))
        body = text_of(bd)
        self.assertIn("Eigene Notiz", body)
        self.assertIn(B.tx("Meine Beobachtung 50 % & mehr"), body)
        self.assertNotIn("\\cite", body)
        self.assertEqual(bib_keys(bd), set())
        en = text_of(build(self.board(note), lang="en"))
        self.assertIn("Own note", en)

    def test_steps_declared_on_everything(self):
        mix = [card(self.p_unch, 0, 0, "f1"), card(IB.make_pin({"kind": "figure", "fig": "atlas", "gef": "perlit"}, thumb=False), 300, 0, "f1"),
               card(IB.make_pin({"kind": "compare", "materials": [MAT, MAT2]}, thumb=False), 0, 300, "f1"),
               {"id": "n1", "kind": "note", "text": "x", "x": 0, "y": 600, "w": 260, "h": 80, "frame": "f1"}]
        bd = build(self.board(*mix))
        for it in bd["items"]:
            if it["kind"] in ("figure", "table", "text") and it.get("id") != "methodik":
                with self.subTest(it["id"]):
                    self.assertIn("rahmen1", (it.get("needs") or {}).get("steps") or [])

    def test_refresh_reproduces_the_report(self):
        b0 = self.board(card(self.p_unch, frame="f1"), card(IB.make_pin({"kind": "figure", "fig": "atlas", "gef": "perlit"}, thumb=False), 300, 0, "f1"))
        bd = build(b0)
        again = B.build(bd["source"]["request"], T.Ctx(), {})
        self.assertEqual(again["slug"], bd["slug"])
        self.assertEqual(tex(again), tex(bd))
        self.assertEqual(bib_keys(again), bib_keys(bd))

    def test_english_report_uses_english_text(self):
        body = text_of(build(self.board(card(self.p_unch, frame="f1")), lang="en"))
        self.assertIn(B.tx(KP.statement(self.unchecked, "en")["text"].rstrip(".")), body)
        self.assertIn("not checked against the original", body)

    def test_section_title_is_escaped(self):
        fr = [frame("f1", "Stähle & Co_50%")]
        self.assertIn(r"Stähle \& Co\_50\%", text_of(build(self.board(card(self.p_unch, frame="f1"), frames=fr))))

    def test_excluded_content_stays_out(self):
        p = IB.make_pin({"kind": "figure", "fig": "atlas", "gef": "perlit"}, thumb=False)
        bd = build(self.board(card(p, frame="f1")), include={"figures": False, "text": True})
        self.assertFalse(any(i["kind"] == "figure" for i in bd["items"]))


class PageTest(unittest.TestCase):
    def test_page_wiring(self):
        html = (STATIC / "index.html").read_text("utf-8")
        for needle in ('id="ibBtn"', '<script src="infoboard.js">', "InfoBoard.decorateEntry", "InfoBoard.decorateList", "InfoBoard.sync()", "META.infoboard"):
            self.assertIn(needle, html)
        self.assertEqual(html.count('id="ibBtn"'), 1)
        self.assertRegex(html, r'<button id="ibBtn"[^>]* hidden')

    def test_no_extra_permanent_panel(self):
        html = (STATIC / "index.html").read_text("utf-8")
        self.assertNotIn('id="ibWin"', html, "the surface is only created when it is opened")

    @unittest.skipUnless(NODE.exists(), "Node not available")
    def test_script_syntax(self):
        r = subprocess.run([str(NODE), "--check", str(STATIC / "infoboard.js")], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(NODE.exists(), "Node not available")
    def test_board_logic_on_a_stub_page(self):
        e = KP.entry("material:" + MAT)
        val = next(s for s in e["statements"] if s.get("prop"))
        st = next(x for s in e["sections"] for x in s["statements"])
        sec = next(s for s in e["sections"] if s["statements"])
        specs = [{"kind": "entry", "id": e["id"]}, {"kind": "entry", "id": "material:" + MAT2}, {"kind": "value", "id": val["id"]}, {"kind": "statement", "id": st["id"]},
                 {"kind": "section", "id": sec["id"]}, {"kind": "compare", "materials": [MAT, MAT2]}]
        def key(s):
            return f"compare:{','.join(s['materials'])}" if s["kind"] == "compare" else f"{s['kind']}:{s['id']}"
        fx = {"mat": MAT, "mat2": MAT2, "entry": e, "figspec": None, "pins": {key(s): IB.make_pin(s, thumb=False) for s in specs}}
        fx["pins"]["figure:atlas:perlit:"] = IB.make_pin({"kind": "figure", "fig": "atlas", "gef": "perlit"})
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "fixture.json"
            f.write_text(json.dumps(fx, ensure_ascii=False), "utf-8")
            r = subprocess.run([str(NODE), str(HERE / "infoboard_dom.js"), str(f)], capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertTrue(r.stdout.strip(), r.stderr[:1500])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["failed"], [])
        self.assertGreater(out["passed"], 50)


class RouteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("FOLIO_SUITE_DIR", None)
        self.envs = ModuleEnvs(Path(self.tmp), "werkstoffe")

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_actions(self):
        doc = IB.route(self.envs, "load", {})
        pin = IB.route(self.envs, "pin", {"spec": {"kind": "statement", "id": "atlas:ferrit.1"}})["pin"]
        self.assertEqual(IB.route(self.envs, "state", {"pins": [pin]})["states"][pin["id"]]["state"], "ok")
        self.assertEqual(IB.route(self.envs, "renew", {"pin": pin})["pin"]["id"], pin["id"])
        self.assertTrue(IB.route(self.envs, "walk", {"ids": [MAT]})["items"])
        self.assertIn("flagged", IB.route(self.envs, "plan", {"board": {"cards": [card(pin)], "frames": []}}))
        self.assertTrue(IB.route(self.envs, "save", {"project": doc["project"], "rev": 0, "doc": doc["doc"]})["ok"])
        with self.assertRaises(LookupError):
            IB.route(self.envs, "gibt-es-nicht", {})


class HttpTest(unittest.TestCase):
    """The routes as the page uses them, on a throwaway module server with its own temporary suite."""

    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        import threading
        from werk import server as S
        cls.S, cls.old = S, getattr(S, "STATE", None)
        cls.tmp = tempfile.mkdtemp()
        cls.env = mock.patch.dict(os.environ)
        cls.env.start()
        os.environ.pop("FOLIO_SUITE_DIR", None)
        S.STATE = S.State(Path(cls.tmp))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.S.STATE = cls.old
        cls.env.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def post(self, path, body):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_page_assets(self):
        import urllib.request
        with urllib.request.urlopen(self.base + "/infoboard.js", timeout=20) as r:
            self.assertIn("javascript", r.headers["Content-Type"])
            self.assertIn(b"InfoBoard", r.read())
        with urllib.request.urlopen(self.base + "/api/meta", timeout=60) as r:
            self.assertTrue(json.loads(r.read())["infoboard"])

    def test_pin_save_export_and_refresh(self):
        _, got = self.post("/api/infoboard/load", {})
        doc = got["doc"]
        _, j = self.post("/api/infoboard/pin", {"spec": {"kind": "statement", "id": "atlas:ferrit.1"}, "lang": "de"})
        b = doc["boards"][0]
        b["frames"] = [frame("f1", "Rahmen")]
        b["cards"] = [card(j["pin"], 20, 60, "f1")]
        code, r = self.post("/api/infoboard/save", {"project": got["project"], "rev": doc["rev"], "doc": doc})
        self.assertEqual((code, r.get("ok")), (200, True))
        _, again = self.post("/api/infoboard/load", {})
        self.assertEqual(again["doc"]["boards"][0]["cards"][0]["id"], j["pin"]["id"])
        code, bd = self.post("/api/bundle", {"sections": [{"tool": "infotafel", "req": {"board": b, "frame": None, "leave_out": []}}], "lang": "de", "include": {}, "title": None})
        self.assertEqual(code, 200, bd.get("error"))
        code, re_bd = self.post("/api/bundle/rebuild", {"source": bd["source"], "lang": "de"})
        self.assertEqual(code, 200, re_bd.get("error"))
        self.assertEqual(tex(re_bd), tex(bd))

    def test_errors_are_answers(self):
        self.assertEqual(self.post("/api/infoboard/pin", {"spec": {"kind": "nonsense"}})[0], 400)
        self.assertEqual(self.post("/api/infoboard/nonsense", {})[0], 404)
        self.assertEqual(self.post("/api/infoboard/save", {"doc": {}})[0], 400)


if __name__ == "__main__":
    unittest.main()
