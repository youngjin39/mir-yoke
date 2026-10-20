"""Render lifecycle continuity context."""

MESSAGE = (
    "Mir lifecycle continuity: preserve the active task intent and verify state before continuing."
    " Default work method: 1 Method/intent -> 2 Design -> 3 TDD -> 4 Eval -> 5 Develop -> "
    "6 Repeat 3-5 until tests pass -> 7 Finish; done only when every request-matrix cell has "
    "evidence checked now, otherwise report N/M and open cells (details: runtime-continuity "
    "skill, references/default-work-method.md)."
    " Handoffs/briefs for another agent copy only owner-granted authority "
    "(never add edits, tests, commands or writes) and carry: "
    "qualified target; lifecycle/temporal/epistemic/verification status; "
    "pins = paste the output of `python3 scripts/mir_ontology.py mapping --handoff "
    "<source paths>`; "
    "evidence provenance+time; unknowns; may/may-not authority; "
    "self-check: missing fields/pins=unknowns."
)


def main() -> None:
    print(MESSAGE)


if __name__ == "__main__":
    main()
