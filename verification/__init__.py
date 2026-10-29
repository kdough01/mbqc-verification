"""verification — checks, sorted by the question each answers.

    faithfulness/   does the statement mean what we intend?
    truth/          is the statement true?
    graph/          properties of the DAG as a whole (computed by dagtool)

Every check subclasses verification.base.Check and registers itself; its kind's
ceiling is in verification/kinds.py.
"""
