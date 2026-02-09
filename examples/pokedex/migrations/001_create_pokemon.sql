CREATE TABLE pokemon (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    types      TEXT    NOT NULL,
    hp         INTEGER NOT NULL,
    attack     INTEGER NOT NULL,
    defense    INTEGER NOT NULL,
    speed      INTEGER NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    legendary  INTEGER NOT NULL DEFAULT 0
)
