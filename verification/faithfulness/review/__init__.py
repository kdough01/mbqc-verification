"""Human statement review.

Reviews are records, not code: `dagtool review <id> --reviewer NAME --decision approve`
shows the statement and the definitions it rests on, then appends a record to
dag/reviews/<id>.yaml pinned to the statement hash. Editing the statement voids it.
The reviewer checks the statement and definitions, never the proof.
"""
