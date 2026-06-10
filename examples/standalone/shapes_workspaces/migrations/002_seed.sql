-- Two tenants. Workspace 1 (Acme) is "you". Workspace 2 (Globex) is a different
-- tenant whose data must NEVER appear in your views — its "TOP SECRET" project
-- and "build the laser" task are the canaries the tenant-isolation test checks.

INSERT INTO workspaces (id, name) VALUES (1, 'Acme Inc');
INSERT INTO workspaces (id, name) VALUES (2, 'Globex Corp');

-- Workspace 1 projects
INSERT INTO projects (id, workspace_id, name, status) VALUES (1, 1, 'Website Redesign', 'active');
INSERT INTO projects (id, workspace_id, name, status) VALUES (2, 1, 'Mobile App', 'planning');
-- Workspace 2 project (the cross-tenant canary)
INSERT INTO projects (id, workspace_id, name, status) VALUES (3, 2, 'TOP SECRET — Globex', 'active');

-- Workspace 1 tasks
INSERT INTO tasks (id, project_id, workspace_id, title, priority, done, created_at) VALUES
    (1, 1, 1, 'Wireframes',        3, 1, '2026-01-01'),
    (2, 1, 1, 'Visual design',     2, 0, '2026-01-03'),
    (3, 1, 1, 'Implement nav',     1, 0, '2026-01-05'),
    (4, 2, 1, 'Push notifications',2, 0, '2026-01-02'),
    (5, 2, 1, 'Offline mode',      1, 0, '2026-01-04');
-- Workspace 2 task (canary)
INSERT INTO tasks (id, project_id, workspace_id, title, priority, done, created_at) VALUES
    (6, 3, 2, 'Build the laser',   5, 0, '2026-01-06');

-- Workspace 1 comments (task 1 has three, to exercise the top-3 per-task window)
INSERT INTO comments (id, task_id, workspace_id, author, body, created_at) VALUES
    (1, 1, 1, 'alice', 'First wireframe looks good',  '2026-01-01'),
    (2, 1, 1, 'bob',   'Ship it',                     '2026-01-02'),
    (3, 1, 1, 'carol', 'One more accessibility pass',  '2026-01-03'),
    (4, 2, 1, 'alice', 'Love the new palette',        '2026-01-03'),
    (5, 4, 1, 'dave',  'Which push provider?',        '2026-01-02');
-- Workspace 2 comment (canary)
INSERT INTO comments (id, task_id, workspace_id, author, body, created_at) VALUES
    (6, 6, 2, 'henchman', 'Sharks acquired',          '2026-01-06');
