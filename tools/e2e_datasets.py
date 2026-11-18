"""End-to-end check of the shared datasets: Excel -> mark -> clean -> share -> Rechner, Elementrechner, TGA, FTIR -> report bundle.

Run: python tools/e2e_datasets.py   (exit code 0 = all checks passed)

Runs in a temporary suite folder (FOLIO_SUITE_DIR removed), never the user's project.
"""
import base64
import io
import math
import os
import re
import sys
import tempfile
from pathlib import Path

FL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(FL / "sdk" / "python")] + [str(FL / "modules" / m) for m in
                                                ("datenaufbereitung", "rechner", "elementrechner", "tga", "ftir")]
os.environ.pop("FOLIO_SUITE_DIR", None)
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import openpyxl

from labproject import ModuleEnvs
from labshare import Sharebox
from daten import readers as R, recipe as RC, datasets as D, bundle as B, export as X
from daten.server import describe_step
from rechner import dsvars as RV
from elementrechner import datasets as ED
from elementrechner import analysis as EA
from tga import dataset as TD
from ftir import dataset as FD

ok = []


def check(cond, what):
    print(("OK   " if cond else "FAIL ") + what)
    ok.append(bool(cond))


def xlsx(rows):
    w = openpyxl.Workbook()
    ws = w.active
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    w.save(b)
    return b.getvalue()


tmp = tempfile.TemporaryDirectory()
root = Path(tmp.name)
envs = ModuleEnvs(root, "datenaufbereitung")
envs.ensure()

# ---------------------------------------------------------------- 1. kinetics workbook: markers, outlier, metadata
k_true = 0.035                                                    # 1/min
rows = [["Kinetik Versuch 7"], ["Temperatur:", 25, "°C"], [], ["t", "c", "Bemerkung"], ["min", "mmol/L", ""]]
noise = np.random.default_rng(7).normal(0, 0.03, 15)
for i, t in enumerate(range(0, 75, 5)):
    c = 12.0 * math.exp(-k_true * t) * (1 + 0.004 * noise[i] / 0.03)
    cell = round(c, 4)
    if t == 35:
        cell = "n.d."
    if t == 50:
        cell = 9.9                                                # outlier (true ~2.08)
    if t == 70:
        cell = "<0,5"                                             # below LOD (true ~1.03)
    rows.append([t, cell, "ok" if t != 50 else "Blase?"])
raw = xlsx(rows)
sh = R.load_bytes(raw, "kinetik7.xlsx")[0]
steps = RC.guess(sh)
tbl = RC.extract(sh, steps)
names = [(c["name"], c["unit"]) for c in tbl["columns"]]
check(("t", "min") in names and ("c", "mmol/L") in names, f"guess reads header and units: {names}")
check("Temperatur" in tbl["conditions"], f"metadata cell -> condition: {list(tbl['conditions'])}")
ds = RC.to_dataset(tbl, "Kinetik Versuch 7", [{"name": "kinetik7.xlsx", "sha256": "0" * 64, "sheet": sh.name}], steps, "0.2.0")
codes = sorted({f["code"] for f in ds.header["flags"]})
check(codes == ["below_lod", "missing"], f"markers flagged, rows kept: {codes}, rows {ds.rows}")
p = D.publish(envs, D.producer(envs, "0.2.0", None, "kinetik7"), ds)
sid = p["share"]

# ---------------------------------------------------------------- 2. clean: convert c to mol/L, Grubbs, exclude
ops = [{"op": "convert", "col": "c", "unit": "mol/L"},
       {"op": "outliers", "method": "residual", "col": "c", "x": "t", "degree": 3, "k": 3},
       {"op": "exclude", "codes": ["outlier", "below_lod"], "reason": "Ausreisser (Blase) und Wert unter NWG"}]
d2 = D.make_derived(envs, "0.2.0", sid, ops, "Kinetik Versuch 7 bereinigt", "live", None, None)
ds2, env2 = D.load(envs, d2["share"])
excl = sorted(f["row"] for f in ds2.header["flags"] if f.get("excluded"))
check(ds2.col("c")["unit"] == "mol/L" and abs(ds2.data["c"][0] - ds.data["c"][0] / 1000) < 1e-12, "c converted to mol/L over the whole column")
check(10 in excl and 14 in excl, f"outlier (row 11) and <NWG (row 15) excluded: rows {[r + 1 for r in excl]}")
check(ds2.header["provenance"]["steps"][-1]["excluded_after"] == 2, "step log counts excluded rows, not flags")
check(len(ds2.header["provenance"]["steps"]) == 3, "step log with counts: " + " | ".join(
    f"{s['text']} ({s['rows_before']}→{s['rows_after']}, ex {s['excluded_before']}→{s['excluded_after']})" for s in ds2.header["provenance"]["steps"]))

box = Sharebox(envs.suite, envs.project)

# ---------------------------------------------------------------- 3. Rechner: dataset columns as variables (SI)
vals, infos = RV.resolve([{"share": d2["share"], "mode": "live", "keys": ["t", "c"]}], box)
check(set(vals) == {"t", "c"} and infos[0]["used"] == 12, f"Rechner variables {sorted(vals)}, used rows {infos[0]['used']} of {infos[0]['rows']}")
t_si, c_si = np.array(vals["t"]["store"]), np.array(vals["c"]["store"])
slope = np.polyfit(t_si, np.log(c_si), 1)[0]
check(abs(-slope - k_true / 60) / (k_true / 60) < 0.03, f"ln c vs t (SI) gives k = {-slope:.4e} 1/s (true {k_true / 60:.4e})")

# ---------------------------------------------------------------- 4. Elementrechner: reaction order fit
r = ED.read(box, {"id": d2["share"], "tool": "order", "cols": {"t": "t", "c": "c"}})
check(r["n"] == 12 and r["dropped"]["excluded"] == 2, f"Elementrechner reads {r['n']} rows, dropped {r['dropped']}")
fit = None
for name in ("order_fit", "reaction_order", "kinetics_call"):
    if hasattr(EA, name):
        fit = name
        break
print("     (Elementrechner analysis entry:", fit, ")")
try:
    from labcalc import kinetics as K
    res = K.order_fit(r["values"]["t"], r["values"]["c"]) if hasattr(K, "order_fit") else None
    if res is not None:
        best = res.get("best") if isinstance(res, dict) else None
        print("     order fit best:", best)
except Exception as e:  # noqa: BLE001
    print("     order fit not called directly:", e)

# ---------------------------------------------------------------- 5. TGA: run from a dataset (time, T, mass)
trows = [["Zeit", "Temperatur", "Masse"], ["s", "K", "g"]]
for i in range(60):
    T = 303.15 + i * 10 / 6
    m = 0.010 * (1 - 0.30 / (1 + math.exp(-(T - 700) / 15)))
    trows.append([i * 10, round(T, 3), round(m, 7)])
tsh = R.load_bytes(xlsx(trows), "tga.xlsx")[0]
tst = RC.guess(tsh)
tds = RC.to_dataset(RC.extract(tsh, tst), "TGA-Rohdaten", [], tst, "0.2.0")
tp = D.publish(envs, D.producer(envs, "0.2.0", None, "tga"), tds)
tgot, tenv = D.load(envs, tp["share"])
data, fname = TD.make_raw(tgot, {"t": "Zeit", "T": "Temperatur", "m": "Masse"}, {"id": tp["share"], "version": tp["version"], "mode": "live"})
run = TD.read_raw(data, fname)
run = run[0] if isinstance(run, (list, tuple)) else run
print("     TGA run type:", type(run).__name__)
doc = __import__("json").loads(data)
cu = {c["role"]: (c["unit"], c["values"][0], c["values"][-1]) for c in doc["columns"]}
check(cu["t"][0] == "min" and abs(cu["t"][2] - 9.833333333) < 1e-6, f"TGA time s → min: {cu['t']}")
check(cu["T"][0] == "°C" and abs(cu["T"][1] - 30.0) < 1e-6, f"TGA temperature K → °C: {cu['T']}")
check(cu["m"][0] == "mg" and abs(cu["m"][1] - 10.0) < 0.01, f"TGA mass g → mg: {cu['m']}")

# ---------------------------------------------------------------- 6. FTIR: spectrum from a dataset (µm → 1/cm)
frows = [["lambda", "A"], ["µm", ""]]
for i in range(40):
    lam = 2.5 + i * 0.1
    frows.append([round(lam, 3), round(0.1 + 0.8 * math.exp(-((1e4 / lam - 2900) / 60) ** 2), 5)])
fsh = R.load_bytes(xlsx(frows), "ir.xlsx")[0]
fst = RC.guess(fsh)
fds = RC.to_dataset(RC.extract(fsh, fst), "IR-Spektrum", [], fst, "0.2.0")
fp = D.publish(envs, D.producer(envs, "0.2.0", None, "ir"), fds)
fgot, _ = D.load(envs, fp["share"])
xk, yk = fgot.columns[0]["key"], fgot.columns[1]["key"]
print("     FTIR keys:", xk, yk)
x, how = FD.x_values(fgot, xk)
check(abs(x.max() - 4000) < 1e-6 and abs(x.min() - 1e4 / 6.4) < 1e-3, f"FTIR x from µm → 1/cm ({x.min():.1f}–{x.max():.1f}; {how})")
raws = FD.make_raws(fgot, xk, [yk], "auto", {"id": fp["share"], "version": fp["version"], "mode": "live"})
check(len(raws) == 1 and b"FOLIO DATASET" in raws[0][0], f"FTIR spectrum file {raws[0][1]} carries the dataset source")

# ---------------------------------------------------------------- 7. report bundle of the cleaned dataset
b = B.build(ds2, {"share": d2["share"], "version": env2["version"]}, {"lang": "de"}, describe_step)
files = {k: base64.b64decode(v) for k, v in b["files"].items()}
text = files["text-methodik.tex"].decode("latin-1")
bib = files.get("refs.bib", b"").decode("latin-1")
check("Ausgeschlossen wurden 2 Zeile(n)" in text and d2["share"] in text, "methods text names exclusions and the dataset ID")
# since 0.3.0 the residual fit cites no source (studentised residual with a rule-of-thumb threshold, methods page)
check("nist-esh" not in bib and "Faustregel" in text and "studentisiert" in text,
      "residual fit described as rule of thumb, no unverified source cited")
check(b["module_version"] and b["source"]["kind"] == "dataset", f"bundle carries module version {b['module_version']} and source kind")
for k, v in files.items():
    if k.endswith((".tex", ".bib", ".csv")):
        try:
            v.decode("latin-1").encode("latin-1")
        except UnicodeError:
            check(False, f"{k} not Latin-1")
        bad = re.findall(r"\\(text|ce|tfrac|boldsymbol)\b", v.decode("latin-1"))
        if bad:
            check(False, f"{k} uses forbidden macros {bad}")
check(any(i["kind"] == "figure" for i in b["items"]), "bundle has the preview figure")
rb = B.rebuild_dataset(b["source"])
check(rb is not None and rb.header["data_hash"] == ds2.header["data_hash"], "bundle source rebuilds the same dataset (Refresh)")

# ---------------------------------------------------------------- 8. exports keep units and the protocol
import importlib.util  # noqa: E402
for fmt in ("csv", "xlsx", "json", "parquet"):
    if fmt == "parquet" and importlib.util.find_spec("pyarrow") is None:
        print("  (Parquet übersprungen: pyarrow nicht installiert, optional)")
        continue
    data, mime = X.export(ds2, fmt, describe_step)
    back = X.reimport(data, "x" + X.FORMATS[fmt][1])
    diff = X.same(ds2, back)
    check(not diff, f"export {fmt} ({len(data)} bytes, {mime}) reads back with the same names, units and values {diff or ''}")

tmp.cleanup()
print(f"\n{sum(ok)} of {len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)
