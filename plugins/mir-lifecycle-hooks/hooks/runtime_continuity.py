"""Render lifecycle continuity context."""

MESSAGE = (
    "Mir lifecycle continuity: preserve the active task intent and verify state before"
    " continuing. Default work method: 1 Method/intent -> 2 Design (+scenarios) -> 3 TDD -> 4 Eval"
    " -> 5 Develop -> 6 Repeat 3-5 until tests pass -> 7 Finish; done only when every"
    " request-matrix cell has evidence checked now, otherwise report N/M and open cells (details:"
    " runtime-continuity skill, references/default-work-method.md). Handoffs: qualified target;"
    " four status axes; full pins; evidence provenance+time; unknowns; owner may/may-not only."
    " If commands allowed, paste `python3 scripts/mir_ontology.py mapping --handoff <source"
    " paths>` unchanged; else inventory unavailable pins. Recipients label each pin"
    " verified-in-repo or parent-supplied. Self-check each gap; scope the whole envelope. See"
    " ontology Handoff."
)


def main() -> None:
    print(MESSAGE)


if __name__ == "__main__":
    main()
