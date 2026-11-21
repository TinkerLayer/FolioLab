// Equation templates of the Rechner page: text form, round trip and box order.
// Run: node modules/rechner/tests/test_templates.js (also started by test_templates.py).
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const page = fs.readFileSync(path.join(__dirname, "..", "rechner", "static", "index.html"), "utf8");
const block = /\/\* TPL-BEGIN \*\/([\s\S]*?)\/\* TPL-END \*\//.exec(page);
assert(block, "TPL block not found in index.html");
const TPL = new Function(`${block[1]}; return TPL;`)();

function filled(t, vals) {
  const n = TPL.make(t);
  for (const [k, v] of Object.entries(vals)) n.s[k] = [v];
  return n;
}
const cases = [
  [filled("int", { f: "x^2", lo: "0", hi: "1" }), "integral(x^2, x, 0, 1)"],
  [filled("diff", { f: "sin(x)" }), "diff(sin(x), x)"],
  [filled("diff2", { f: "x^3", v: "t" }), "diff(x^3, t, 2)"],
  [filled("sum", { f: "k^2", b: "10" }), "sum(k^2, k, 1, 10)"],
  [filled("prod", { f: "k", b: "5" }), "prod(k, k, 1, 5)"],
  [filled("sqrt", { x: "a+b" }), "sqrt(a+b)"],
  [filled("root", { x: "27", n: "3" }), "root(27, 3)"],
  [filled("frac", { num: "a+1", den: "b-1" }), "(a+1)/(b-1)"],
  [filled("frac", { num: "a", den: "2" }), "a/2"],
  [filled("pow", { base: "x+1", exp: "n-1" }), "(x+1)^(n-1)"],
  [filled("pow", { base: "sin(x)", exp: "2" }), "sin(x)^2"],
  [filled("abs", { x: "x-1" }), "abs(x-1)"],
  [filled("mat", { c0_0: "1", c0_1: "2", c1_0: "3", c1_1: "4" }), "[[1, 2], [3, 4]]"],
];
for (const [node, text] of cases) {
  assert.strictEqual(TPL.ser(node), text);
  assert.strictEqual(TPL.serText(text), text, `round trip of ${text}`);
}

// the parsed tree holds the same boxes
const p = TPL.parse("integral(x^2, x, 0, 1)");
assert.strictEqual(p[1].t, "int");
assert.deepStrictEqual([p[1].s.lo[0], p[1].s.hi[0], p[1].s.f[0], p[1].s.v[0]], ["0", "1", "x^2", "x"]);
assert.strictEqual(TPL.parse("[[1, 2], [3, 4]]")[1].r, 2);
assert.strictEqual(TPL.parse("(a+1)/(b-1)")[1].t, "frac");
assert.strictEqual(TPL.parse("(a+1)^(b-1)")[1].t, "pow");
assert.strictEqual(TPL.parse("diff(x^3, x, 2)")[1].t, "diff2");

// text around a template stays, names that only end in a function name are no template
assert.strictEqual(TPL.serText("2*sqrt(x) + 1"), "2*sqrt(x) + 1");
assert.strictEqual(TPL.parse("mysum(1, 2, 3, 4)").length, 1);

// empty boxes are gaps in the text form and read back as empty
const gap = TPL.make("int");
assert.strictEqual(TPL.ser(gap), "integral(□, x, □, □)");
assert.strictEqual(TPL.parse(TPL.ser(gap))[1].s.lo[0], "");

// decimal comma in a box, argument commas stay
assert.strictEqual(TPL.ser(filled("sqrt", { x: "2,5" })), "sqrt(2.5)");
assert.strictEqual(TPL.ser(filled("sqrt", { x: "log(x,2)" })), "sqrt(log(x,2))");

// nesting: a template inside a box, at the caret
const outer = filled("frac", { num: "2x", den: "3" });
const inPath = TPL.insert(outer, "num/0", 1, "sqrt");
assert.strictEqual(inPath, "num/1/x/0");
TPL.at(outer, inPath).parts[TPL.at(outer, inPath).i] = "y";
assert.strictEqual(TPL.ser(outer), "(2sqrt(y)x)/3");
assert.strictEqual(TPL.serText(TPL.ser(outer)), TPL.ser(outer));

// Tab order
assert.deepStrictEqual(TPL.order(TPL.make("int")), ["lo/0", "hi/0", "f/0", "v/0"]);
assert.deepStrictEqual(TPL.order(TPL.make("sum")), ["k/0", "a/0", "b/0", "f/0"]);
assert.deepStrictEqual(TPL.order(TPL.make("mat")), ["c0_0/0", "c0_1/0", "c1_0/0", "c1_1/0"]);
assert.deepStrictEqual(TPL.order(outer), ["num/0", "num/1/x/0", "num/2", "den/0"]);

// matrix grows
const m = TPL.make("mat");
TPL.addRow(m);
TPL.addCol(m);
assert.strictEqual(TPL.ser(m), "[[□, □, □], [□, □, □], [□, □, □]]");

// every box of the drawing carries its path
for (const t of ["int", "diff", "diff2", "sum", "prod", "sqrt", "root", "frac", "pow", "abs", "mat"]) {
  const n = TPL.make(t), html = TPL.html(n);
  for (const q of TPL.order(n)) assert(html.includes(`data-p="${q}"`), `${t}: box ${q}`);
}

// the whole input line as a tree: the text around a template stays word for word
const ln = TPL.lineOf("y = 2*integral(x^2, x, 0, 1) + 1,5");
assert.strictEqual(TPL.ser(ln), "y = 2*integral(x^2, x, 0, 1) + 1,5");
assert.deepStrictEqual(TPL.order(ln).slice(0, 1), ["x/0"]);
assert.strictEqual(TPL.order(ln).slice(-1)[0], "x/2");
const around = TPL.lineAround("a + ", TPL.make("sqrt"), " - b");
assert.strictEqual(TPL.ser(around), "a + sqrt(□) - b");
assert.strictEqual(TPL.firstBox(around.s.x[1], "x/1/"), "x/1/x/0");
assert(TPL.hasTemplate("2*sqrt(x)"));
assert(!TPL.hasTemplate("k = x^2"), "a plain assignment stays text");

// removing a template joins the text left and right of it
assert(TPL.blank(TPL.make("int")));
const rm = TPL.lineAround("a + ", TPL.make("sqrt"), " - b");
assert.deepStrictEqual(TPL.remove(rm, "x/1/"), { path: "x/0", caret: 4 });
assert.strictEqual(TPL.ser(rm), "a +  - b");
const nest = TPL.lineOf("sqrt(abs(y))");
assert(!TPL.blank(nest.s.x[1]));
TPL.remove(nest, "x/1/x/1/");
assert.strictEqual(TPL.ser(nest), "sqrt(□)");

// the symbol keys that used to insert code are drawn templates with boxes and read back drawn
const drawn = [
  ["logb", { x: "8", b: "2" }, "log(8, 2)"], ["cbrt", { x: "27" }, "cbrt(27)"], ["exp", { x: "2x" }, "exp(2x)"],
  ["dat", { f: "x^3", v: "x", at: "2" }, "deriv(x^3, x, 2)"], ["if", { c: "x > 0", a: "1", b: "2" }, "if(x > 0, 1, 2)"],
  ["nsolve", { l: "x^2", r: "2", v: "x", s: "1" }, "nsolve(x^2 == 2, x, 1)"], ["det", { x: "A" }, "det(A)"], ["inv", { x: "A" }, "inv(A)"],
  ["adj", { x: "A" }, "adj(A)"], ["norm", { x: "v" }, "norm(v)"], ["cross", { a: "u", b: "v" }, "cross(u, v)"], ["dot", { a: "u", b: "v" }, "dot(u, v)"],
  ["vec", { c0: "1", c1: "2", c2: "3" }, "[1, 2, 3]"],
];
for (const [t, vals, text] of drawn) {
  const n = filled(t, vals);
  assert.strictEqual(TPL.ser(n), text, `${t}: text form`);
  assert.strictEqual(TPL.serText(text), text, `${t}: round trip`);
  const back = TPL.parse(text);
  assert.strictEqual(back.length, 3, `${t}: reads back as one template`);
  assert.strictEqual(back[1].t, t, `${t}: same template`);
  assert.deepStrictEqual(TPL.order(back[1]).length, TPL.order(n).length, `${t}: same boxes`);
  const empty = TPL.make(t), drawing = TPL.html(empty);
  for (const q of TPL.order(empty)) assert(drawing.includes(`data-p="${q}"`), `${t}: box ${q}`);
  assert(!/[,□]|==|\b(cbrt|deriv|nsolve|cross|inv|norm)\b/.test(drawing.replace(/<[^>]*>/g, "")), `${t}: no code in the drawing`);
  assert(!TPL.ser(empty).includes("undefined"), `${t}: empty text form`);
  assert.strictEqual(TPL.firstBox(empty, "") && TPL.order(empty).includes(TPL.firstBox(empty, "")), true, `${t}: first box exists`);
}
assert.strictEqual(TPL.ser(TPL.make("nsolve")), "nsolve(□ == □, x, 1)");
assert.strictEqual(TPL.ser(TPL.make("dat")), "deriv(□, x, □)");
assert.strictEqual(TPL.ser(TPL.make("vec")), "[□, □, □]");
assert.strictEqual(TPL.parse(TPL.ser(TPL.make("nsolve")))[1].s.l[0], "");

// plain function keys draw one box; the text stays the ordinary function call
const sinKey = TPL.make("fn:sin");
sinKey.s.x = ["2x"];
assert.strictEqual(TPL.ser(sinKey), "sin(2x)");
assert(TPL.html(TPL.make("fn:log10")).includes(">lg<"));
assert.strictEqual(TPL.ser(TPL.make("fn:log10")), "log10(□)");
assert(!TPL.hasTemplate("y = sin(x) + ln(x)"), "plain functions stay text in a line");
assert.strictEqual(TPL.ser(filled("e10", { exp: "3" })), "·10^3");

// forms that are not the template stay text
for (const s of ["log(x)", "norm(v, 1)", "deriv(f, x, 1, 2)", "nsolve(x^2 - 2, x, 1)", "A[1, 2]", "t = [1; 2; 5]", "[1, 2, 3, 4, 5, 6, 7]", "mydet(A)"])
  assert(!TPL.hasTemplate(s), `stays text: ${s}`);
assert.strictEqual(TPL.parse("2*[1, 2]")[1].t, "vec");

// nesting: a new template in a box of a new template, Tab order goes through both
const ifn = TPL.make("if");
const inIf = TPL.insert(ifn, "a/0", 0, "cbrt");
TPL.at(ifn, inIf).parts[TPL.at(ifn, inIf).i] = "8";
ifn.s.c = ["x > 0"];
ifn.s.b = ["0"];
assert.strictEqual(TPL.ser(ifn), "if(x > 0, cbrt(8), 0)");
assert.strictEqual(TPL.serText(TPL.ser(ifn)), TPL.ser(ifn));
assert.strictEqual(TPL.parse(TPL.ser(ifn))[1].s.a[1].t, "cbrt");
assert(TPL.order(ifn).includes(inIf));

// the vector grows with its button
const vg = TPL.make("vec");
TPL.addRow(vg);
assert.strictEqual(TPL.ser(vg), "[□, □, □, □]");
assert.strictEqual(TPL.order(vg).length, 4);
assert(TPL.html(vg).includes('data-tadd="r"'));

// no key of the symbol window inserts a function call as text any more
const keys = /const SYM_GROUPS = \[([\s\S]*?)\n\];/.exec(page)[1];
assert(!/"[^"]*\b[a-z0-9]+\(□/.test(keys), "a symbol key still inserts code");
const gapKeys = [...keys.matchAll(/\["([^"]*)", "([^"]*□[^"]*)"/g)].map(m => m[1]).filter(l => l !== "□ = □");
assert.deepStrictEqual(gapKeys.sort(), ["( )", "→"].sort(), "only ( ) and → may still insert text with a gap");
for (const t of ["eq", "sys", "cond", "fdef"]) assert(keys.includes(`"tpl:${t}"`), `key for ${t}`);

// whole-line statements: same text, one drawn node, boxes in order, reopen drawn
const lineNode = (s) => TPL.lineOf(s).s.x;
const statements = [
  ["x^2 - 3 = 0", ["eq"]], ["sin(x) = 0.5", ["eq"]], ["inv(A) = Q", ["eq"]], ["50/3 = u", ["eq"]],
  ["x + y = 3; x - y = 1", ["sys"]], ["x = 1; y = 2; z = 3", ["sys"]],
  ["x^2 = 4, x > 0", ["eq", "cond"]], ["x^2 = 4, x >= 0, x <= 5", ["eq", "cond", "cond"]], ["y = 2x - 1, y < 3", ["eq", "cond"]],
  ["f(x) = x^2 - 2", ["fdef"]], ["g(x, y) = x*y", ["fdef"]], ["Fläche(r) = pi*r^2", ["fdef"]],
];
for (const [s, kinds] of statements) {
  const parts = lineNode(s);
  assert.deepStrictEqual(parts.filter(p => typeof p !== "string").map(p => p.t), kinds, `${s}: nodes`);
  assert.strictEqual(TPL.ser(TPL.lineOf(s)), s, `${s}: same text`);
  assert.strictEqual(TPL.serText(s), s, `${s}: round trip`);
  assert(TPL.hasTemplate(s), `${s}: reopens drawn`);
  const root = TPL.lineOf(s), drawing = TPL.html(root);
  for (const q of TPL.order(root)) assert(drawing.includes(`data-p="${q}"`), `${s}: box ${q}`);
}
for (const s of ["y = 2", "y = sin(x) + ln(x)", "a = 9,81 m/s^2", "x = 0..10", "t = [1; 2; 5]", "x == 2", "x >= 2", "a != b", "E_kin -> kJ", "x =", "= 3",
  "x = f(t) = t^5", 'rho_mat("a=b")'])
  assert(!TPL.hasTemplate(s), `stays text: ${s}`);
assert.strictEqual(TPL.ser(TPL.lineOf("x^2 = 2,5")), "x^2 = 2.5", "a decimal comma is no condition");
assert.strictEqual(lineNode("x^2 + y = 4, x").filter(p => typeof p !== "string").length, 1, "a sought name is no condition");
assert.strictEqual(lineNode("f(x) = x^2")[1].s.f[0], "f");
assert.strictEqual(lineNode("f(x) = sqrt(x)")[1].s.b[1].t, "sqrt", "templates nest in the body");
assert.strictEqual(lineNode("sqrt(x) = 2")[1].s.l[1].t, "sqrt", "templates nest in a side");

// the keys insert the same text as before
assert.strictEqual(TPL.ser(TPL.make("eq")), "□ = □");
assert.strictEqual(TPL.ser(TPL.make("sys")), "□ = □; □ = □");
assert.strictEqual(TPL.ser(TPL.make("cond")), ", □ > 0");
assert.strictEqual(TPL.ser(TPL.make("fdef")), "f(x) = □");
assert(TPL.hasTemplate("□ = □") && TPL.hasTemplate("x = □"), "a draft with open boxes stays drawn");
assert.strictEqual(TPL.firstBox(TPL.make("fdef")), "b/0", "the body comes first");
assert.deepStrictEqual(TPL.order(TPL.make("sys")), ["l0/0", "r0/0", "l1/0", "r1/0"]);

// system: a brace with one row per equation, rows can be added, an empty new row does not count yet
const sysN = TPL.lineOf("x + y = 3; x - y = 1").s.x[1];
assert.strictEqual((TPL.html(sysN).match(/<span class="cases">/g) || []).length, 1);
assert(TPL.html(sysN).includes('data-tadd="r"'));
TPL.addRow(sysN);
assert.strictEqual(TPL.ser(sysN), "x + y = 3; x - y = 1", "empty row is not written");
assert.strictEqual(TPL.order(sysN).length, 6);
sysN.s.l2 = ["z"]; sysN.s.r2 = ["2"];
assert.strictEqual(TPL.ser(sysN), "x + y = 3; x - y = 1; z = 2");
assert.strictEqual(TPL.lineOf(TPL.ser(sysN)).s.x[1].n, 3, "reopens with three rows");

// condition: the comparison button goes through > >= < <= and the text follows
const cn = filled("cond", { l: "x", r: "2" });
const seen = [TPL.ser(cn)];
for (let k = 0; k < 4; k++) { TPL.nextOp(cn); seen.push(TPL.ser(cn)); }
assert.deepStrictEqual(seen, [", x > 2", ", x >= 2", ", x < 2", ", x <= 2", ", x > 2"]);
assert(TPL.html(cn).includes("data-tcmp"));
assert(!TPL.order(cn).some(q => q.startsWith("op")), "the comparison is no box in the Tab order");

// nesting: a template inside an equation of a system
const nestSys = TPL.make("sys");
const inSys = TPL.insert(nestSys, "l0/0", 0, "sqrt");
TPL.at(nestSys, inSys).parts[TPL.at(nestSys, inSys).i] = "x";
nestSys.s.r0 = ["2"]; nestSys.s.l1 = ["y"]; nestSys.s.r1 = ["1"];
assert.strictEqual(TPL.ser(nestSys), "sqrt(x) = 2; y = 1");
assert.strictEqual(TPL.lineOf(TPL.ser(nestSys)).s.x[1].s.l0[1].t, "sqrt");

// stored complex cells: recognised and shown read-only in the Matrices tab
const cplxSrc = /const isCplx = [\s\S]*?(?=function valNames)/.exec(page)[0];
const fmtSrc = /function fmtNum\(v\) \{[\s\S]*?\n\}/.exec(page)[0];
const CX = new Function(`${fmtSrc}\n${cplxSrc}; return { isCplx, matIsCplx, cellText };`)();
assert(CX.matIsCplx([{ re: 0, im: 1 }, 2]) && CX.matIsCplx([[1, { re: 1, im: -1 }]]));
assert(!CX.matIsCplx([1, 2]) && !CX.matIsCplx([[1, 2], [3, 4]]) && !CX.matIsCplx(3));
assert.strictEqual(CX.cellText({ re: 0, im: 1 }), "1i");
assert.strictEqual(CX.cellText({ re: 0, im: -1 }), "−1i");
assert.strictEqual(CX.cellText({ re: 1.5, im: -2 }), "1.5 − 2i");
assert.strictEqual(CX.cellText({ re: 1, im: 2 }), "1 + 2i");
assert.strictEqual(CX.cellText({ re: null, im: 2 }), "NaN");
assert.strictEqual(CX.cellText(2.5), "2.5");
for (const lang of ["Komplex: nur Anzeige", "Complex: read-only"]) assert(page.includes(lang), lang);

// values offered to other environments: lines, card results and solved quantities
const catSrc = page.slice(page.indexOf("const unitPlainJs"), page.indexOf("async function rcApplyEnvValues"));
const env = { id: "e", name: "Blatt 1", items: [{ id: "l", type: "calc", src: "u = 2" }, { id: "s", type: "calc", src: "2z = 6 m" }, { id: "k", type: "card", eq: "dyn_newton" }] };
const res = {
  lines: { l: { kind: "assign", name: "u", result: { type: "scalar", value: 2 }, unit: "" },
    s: { kind: "solve", sets: [{ name: "z", store: 3, unit: "m" }] } },
  cards: [{ id: "k", status: "ok", result: { sym: "F", value: 6, unit: "N", kind: "force" } }],
};
const catalogue = new Function("S", "envRes", "EQ", "normName", `${catSrc}; return rcCatalogue;`)(
  { values: [], envs: [env], ws: null }, () => res, { dyn_newton: { de: "Newton" } }, (x) => x)();
const bySym = Object.fromEntries(catalogue.map(x => [x.sym, x]));
assert.strictEqual(bySym.u.value, 2);
assert.deepStrictEqual([bySym.F.value, bySym.F.unit, bySym.F.kind], [6, "N", "force"]);
assert.deepStrictEqual([bySym.z.value, bySym.z.unit], [3, "m"]);
console.log("templates OK");
