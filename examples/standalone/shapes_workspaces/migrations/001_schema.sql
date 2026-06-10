-- Multi-tenant project tracker. `workspace_id` is the tenant column that every
-- Shape scopes on, so no query can read across tenants by construction.

CREATE TABLE workspaces (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE projects (
    id           INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL,
    name         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE tasks (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    title        TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 0,
    done         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE comments (
    id           INTEGER PRIMARY KEY,
    task_id      INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    author       TEXT NOT NULL,
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
