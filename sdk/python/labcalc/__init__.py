"""Gemeinsames Rechnen für alle Folio-Lab-Module.

- ``expr``: Ausdrücke lesen und sicher auswerten (eingeschränkter Python-AST, kein ``eval``), Matrizen, Einheiten.
- ``units``: Einheiten, Grössenarten und Konstanten (mit Quellen).
- ``render``: Ausdrücke als LaTeX und HTML.
- ``formulas``: eigene Gleichungen eines Moduls (Name = Ausdruck über die Ergebnisse einer Messung), für Anzeige und
  Bericht.

Ursprünglich Teil des Rechners (``modules/rechner``); dort bleiben ``rechner.expr`` usw. als Verweise bestehen.
"""
