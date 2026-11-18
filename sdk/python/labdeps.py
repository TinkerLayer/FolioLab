"""Lokale Abhängigkeiten innerhalb einer Umgebung (A4): Reihenfolge, Zyklen, veraltete Folgewerte.

Ein Graph ist {knoten: {knoten, von denen er abhängt}}. Knoten ohne eigenen Eintrag gelten als Eingaben.
"""
from __future__ import annotations


class CycleError(ValueError):
    def __init__(self, cycle: list):
        self.cycle = cycle
        super().__init__("Zirkelbezug: " + " → ".join(map(str, cycle)))


def find_cycle(graph: dict) -> list | None:
    """Ein Zyklus als Knotenliste (erster Knoten am Ende wiederholt) oder None."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    stack: list = []

    def visit(n):
        color[n] = GREY
        stack.append(n)
        for d in sorted(graph.get(n, ()), key=str):
            if d not in graph:
                continue
            if color[d] == GREY:
                return stack[stack.index(d):] + [d]
            if color[d] == WHITE:
                c = visit(d)
                if c:
                    return c
        stack.pop()
        color[n] = BLACK
        return None

    for n in sorted(graph, key=str):
        if color[n] == WHITE:
            c = visit(n)
            if c:
                return c
    return None


def order(graph: dict) -> list:
    """Topologische Reihenfolge (Abhängigkeiten zuerst); CycleError bei einem Zirkelbezug."""
    c = find_cycle(graph)
    if c:
        raise CycleError(c)
    done, out = set(), []

    def visit(n):
        if n in done:
            return
        done.add(n)
        for d in sorted(graph.get(n, ()), key=str):
            if d in graph:
                visit(d)
        out.append(n)

    for n in sorted(graph, key=str):
        visit(n)
    return out


def in_cycles(graph: dict) -> set:
    """Alle Knoten, die auf irgendeinem Zyklus liegen (stark zusammenhängende Teile mit > 1 Knoten oder Selbstbezug)."""
    index, low, on, st, res, i = {}, {}, set(), [], set(), [0]

    def strong(v):
        index[v] = low[v] = i[0]
        i[0] += 1
        st.append(v)
        on.add(v)
        for w in graph.get(v, ()):
            if w not in graph:
                continue
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = st.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in graph.get(v, ()):
                res.update(comp)

    for v in graph:
        if v not in index:
            strong(v)
    return res


def downstream(graph: dict, changed) -> set:
    """Knoten, die direkt oder indirekt von `changed` abhängen (ohne `changed` selbst) – diese sind veraltet."""
    rev: dict = {}
    for n, deps in graph.items():
        for d in deps:
            rev.setdefault(d, set()).add(n)
    todo, seen = list(changed if isinstance(changed, (list, set, tuple)) else [changed]), set()
    while todo:
        for n in rev.get(todo.pop(), ()):
            if n not in seen:
                seen.add(n)
                todo.append(n)
    return seen - set(changed if isinstance(changed, (list, set, tuple)) else [changed])
