# Epic: Play-by-Post Forum — MVP on Chirp

**Status**: Open product proof; refresh Sprint 0 before implementation
**Updated**: 2026-05-09 - framework blockers called out in this plan have largely shipped, including pagination, reactive presence/audience filtering, and contract extensions. Rebase this plan around `examples/chirpui/forum_shell` and current shipped APIs. The next step is product design refresh plus Sprint 1-2 implementation; Sprint 3 realtime must define replayable event ids, `Last-Event-ID` behavior, and presence/heartbeat semantics before UI polish.
**Created**: 2026-04-12
**Target**: Standalone product (first production app on Chirp)
**Estimated Effort**: 80–120h (MVP through Sprint 4)
**Dependencies**: None — all required Chirp features are shipped (0.4.0)
**Source**: Codebase audit of Chirp framework capabilities vs. forum product requirements; user's stated dream project (PBP forum inspired by JCink)

---

## Why This Matters

Chirp has no production-grade downstream product. Every framework feature was validated by
examples (49 total), but examples are synthetic — they test the API, not the architecture
under real-world stress. A play-by-post forum is the ideal first product because it
exercises every Chirp strength simultaneously:

1. **Fragment rendering** — thread lists, post lists, and reply forms are natural fragment
   targets; htmx navigation between boards/threads/posts is the core UX loop
2. **SSE real-time** — live thread updates when another player posts (the heartbeat of PBP)
3. **OOB swaps** — unread counts, online status, notification badges update across the shell
4. **App shell + mount_pages** — forums have deep nested routing (board → category → thread → post)
   with context cascade (current user, permissions, breadcrumbs)
5. **Markdown rendering** — patitas integration for post content with syntax highlighting
6. **Sessions + auth** — persistent login, character switching, permission-based access

### Consequences of Not Building This

1. **Framework gaps stay hidden** — pagination, search, email, registration are all missing.
   Without a real product, these gaps don't surface until someone else builds on Chirp and
   hits them.
2. **No proof of architecture** — the app shell + mount_pages + SSE + OOB stack has never
   been composed into a multi-page, multi-user product. Integration bugs will exist.
3. **No adoption story** — "built a forum on Chirp" is more compelling than "built 49 examples."
4. **JCink ages further** — the PBP community deserves a modern platform. Every month of
   delay is another month on Flash-era infrastructure.

### Evidence Table

| Layer | Finding | Proposal Impact |
|-------|---------|-----------------|
| Auth | Login/logout + sessions + permissions exist; no registration, password reset, or email | FIXES — Sprint 1 builds registration + password reset |
| Data | Async SQL + migrations exist; no pagination, no full-text search | FIXES — Sprint 2 builds pagination; Sprint 4 adds search |
| Real-time | SSE + ReactiveBus exist; no per-room scoping, no presence | FIXES — Sprint 3 scopes SSE to threads; Sprint 5 adds presence |
| Templates | Fragment rendering, OOB, app shell all work; never composed at depth >3 routes | FIXES — Sprint 2 composes board → category → thread → post |
| Content | Markdown via patitas works; no rich editor, no file upload validation | MITIGATES — Sprint 2 uses markdown; rich editor deferred |
| Caching | Memory + Redis backends work; no cache invalidation on data change | MITIGATES — Sprint 4 adds manual invalidation patterns |
| CLI | `chirp new` scaffolds projects; no forum-specific generators | UNRELATED — not in scope |

### Invariants

These must remain true throughout or we stop and reassess:

1. **Chirp stays unforked**: All forum code lives in the product, not in framework patches.
   If a framework gap blocks progress, file it upstream and build a workaround. This validates
   Chirp's extension model.
2. **Every sprint is playable**: Each sprint produces a runnable app where users can do
   something meaningful (even if limited). No "infrastructure-only" sprints after Sprint 0.
3. **Tests cover the contract boundary**: Every route has at least one test exercising the
   full request → template → fragment path. SSE endpoints have integration tests.
4. **No JavaScript frameworks**: All interactivity via htmx + Alpine.js (Chirp-injected) +
   CSS. This is a Chirp showcase, not a React app with a Python backend.

---

## Target Architecture

```
pangyo/                          # Product root (named after the forum)
  app.py                         # App setup, middleware stack, API routes
  config.py                      # ProductConfig (extends AppConfig)
  store/                         # Data access layer
    db.py                        # Database setup + get_db()
    users.py                     # User CRUD, registration, password reset
    boards.py                    # Board/category queries
    threads.py                   # Thread CRUD + pagination
    posts.py                     # Post CRUD + pagination
    characters.py                # Character profiles
    notifications.py             # Notification queries
  migrations/
    001_create_users.sql
    002_create_boards.sql
    003_create_threads_posts.sql
    004_create_characters.sql
    005_create_notifications.sql
  pages/
    _layout.html                 # App shell (chirpui): topbar, sidebar, main
    _context.py                  # Root context: current_user, unread_count, boards
    _meta.py                     # Site-wide metadata
    page.py                      # GET / → redirect to /boards or dashboard
    login/
      page.py                    # GET/POST /login
      page.html
    register/
      page.py                    # GET/POST /register
      page.html
    boards/
      page.py                    # GET /boards (board index)
      page.html
      _context.py                # Board list context
      {board_slug}/
        page.py                  # GET /boards/{slug} (thread list)
        page.html
        _context.py              # Board context + thread pagination
        _meta.py                 # Board name in breadcrumbs
        new/
          page.py                # GET/POST /boards/{slug}/new (new thread)
          page.html
        {thread_id}/
          page.py                # GET /boards/{slug}/{id} (post list)
          page.html
          _context.py            # Thread context + post pagination
          _meta.py               # Thread title in breadcrumbs
    profile/
      {username}/
        page.py                  # GET /profile/{username}
        page.html
    settings/
      page.py                    # GET/POST /settings (user settings)
      page.html
  templates/
    components/
      _post.html                 # Post card (avatar, content, actions)
      _thread_row.html           # Thread list row
      _pagination.html           # Reusable pagination
      _breadcrumbs.html          # Breadcrumb trail
      _notification.html         # Notification item
      _character_badge.html      # Character name + avatar
    email/
      verify.html                # Email verification
      reset.html                 # Password reset
  static/
    forum.css                    # Forum-specific styles
    themes/                      # User-selectable themes
      default.css
      dark.css
  tests/
    conftest.py                  # DB fixtures, test users, seeded boards
    test_auth.py                 # Registration, login, logout, password reset
    test_boards.py               # Board listing, permissions
    test_threads.py              # Thread CRUD, pagination, fragments
    test_posts.py                # Post CRUD, markdown rendering, OOB
    test_realtime.py             # SSE thread updates, notifications
    test_characters.py           # Character creation, switching
```

### Data Model (PostgreSQL)

```sql
-- users: auth + profile
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(32) UNIQUE NOT NULL,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  VARCHAR(64),
    avatar_url    TEXT,
    role          VARCHAR(20) DEFAULT 'member',  -- admin, moderator, member
    is_verified   BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT now(),
    last_seen_at  TIMESTAMPTZ
);

-- boards: top-level forum sections
CREATE TABLE boards (
    id          SERIAL PRIMARY KEY,
    slug        VARCHAR(64) UNIQUE NOT NULL,
    name        VARCHAR(128) NOT NULL,
    description TEXT,
    sort_order  INTEGER DEFAULT 0,
    category    VARCHAR(64),           -- grouping label
    permissions JSONB DEFAULT '{}'     -- {"post": ["member"], "view": ["*"]}
);

-- threads: conversations within boards
CREATE TABLE threads (
    id          SERIAL PRIMARY KEY,
    board_id    INTEGER REFERENCES boards(id),
    author_id   INTEGER REFERENCES users(id),
    title       VARCHAR(256) NOT NULL,
    is_pinned   BOOLEAN DEFAULT FALSE,
    is_locked   BOOLEAN DEFAULT FALSE,
    post_count  INTEGER DEFAULT 0,
    last_post_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- posts: individual messages
CREATE TABLE posts (
    id          SERIAL PRIMARY KEY,
    thread_id   INTEGER REFERENCES threads(id),
    author_id   INTEGER REFERENCES users(id),
    character_id INTEGER REFERENCES characters(id),  -- nullable; post-as-character
    content     TEXT NOT NULL,                        -- markdown source
    content_html TEXT NOT NULL,                       -- rendered HTML (cached)
    is_edited   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ
);

-- characters: PBP-specific — users can have multiple characters
CREATE TABLE characters (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    name        VARCHAR(128) NOT NULL,
    avatar_url  TEXT,
    bio         TEXT,
    sheet       JSONB DEFAULT '{}',    -- freeform character sheet data
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- notifications: per-user notification feed
CREATE TABLE notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    type        VARCHAR(32) NOT NULL,  -- 'reply', 'mention', 'mod_action'
    payload     JSONB NOT NULL,        -- {"thread_id": 1, "post_id": 42, "message": "..."}
    is_read     BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- thread_reads: track last-read post per user per thread (for unread indicators)
CREATE TABLE thread_reads (
    user_id     INTEGER REFERENCES users(id),
    thread_id   INTEGER REFERENCES threads(id),
    last_post_id INTEGER REFERENCES posts(id),
    read_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, thread_id)
);
```

### Key Routing Decisions

- **mount_pages** for all browseable pages (boards, threads, profiles, settings)
- **@app.route** for API-style mutations (POST /posts, DELETE /posts/{id}, POST /login, etc.)
- **SSE at `/threads/{id}/events`** scoped per-thread via ReactiveBus
- **Fragments**: thread_row, post_card, notification_item, pagination, unread_badge

---

## Sprint Structure

| Sprint | Focus | Effort | Risk | Ships Independently? |
|--------|-------|--------|------|---------------------|
| 0 | Design: schema, routing tree, auth flow, pagination helper | 8–12h | Low | Yes (RFC + schema only) |
| 1 | Auth: registration, login, sessions, password reset | 16–20h | Medium | Yes (login/register works) |
| 2 | Core forum: boards, threads, posts with markdown + pagination | 20–28h | Medium | Yes (read-only forum works) |
| 3 | Real-time: SSE per-thread, live post arrival, unread tracking | 16–20h | High | Yes (live threads work) |
| 4 | Characters + polish: character profiles, post-as-character, theming | 16–24h | Medium | Yes (PBP-specific features) |
| 5 | Moderation + search (stretch) | 12–16h | Low | Yes (admin tools) |

---

## Sprint 0: Design & Validate

**Goal**: Solve the three hardest problems on paper before writing application code.

### Task 0.1 — Pagination Helper Design

Chirp has no pagination. Design a reusable `Paginator` that works with Chirp's `Database.fetch_all()` and generates htmx-friendly page links.

**Design questions**:
- Offset-based vs cursor-based? (Offset for threads — stable sort by last_post_at desc.
  Cursor for posts — append-only, cursor by post ID.)
- Where does pagination live? `store/pagination.py` as a generic helper, or per-query?
- Template component: `_pagination.html` with `hx-get` + `hx-target` for fragment swaps.

**Acceptance**: Design doc with `Paginator` API, SQL patterns for both modes, and template component markup.

### Task 0.2 — Auth Flow Design

Chirp has login/logout but no registration or password reset. Design the full flow:

- Registration: form → validate → hash password → insert user → send verification email → redirect to login
- Email verification: token in URL → verify → activate account
- Password reset: form → generate token → send email → reset form → update hash
- Email sending: choose library (aiosmtplib) and design async send helper

**Acceptance**: Sequence diagrams for registration, verification, and reset flows. Email template mockups.

### Task 0.3 — SSE Scoping Design

Current ReactiveBus broadcasts globally. A forum needs per-thread SSE scoping:

- One SSE endpoint per thread (`/threads/{id}/events`)
- ReactiveBus scope key = `thread:{id}`
- Events: new_post, post_edited, post_deleted, typing_indicator (stretch)
- Reconnection: htmx SSE reconnects automatically; server sends missed posts via `Last-Event-ID`

**Acceptance**: Design doc with event types, scoping strategy, and reconnection protocol.

**Files**: `plan/drafted/epic-pbp-forum-mvp.md` (this document, updated with designs)
**Acceptance**: All three design tasks completed and reviewed. No code written yet.

---

## Sprint 1: Authentication & User Management

**Goal**: Users can register, verify email, log in, log out, and reset their password.

### Task 1.1 — Project scaffold

Create the product directory, `app.py`, `config.py`, database setup, and migration infrastructure.

**Files**: `app.py`, `config.py`, `store/db.py`, `migrations/001_create_users.sql`
**Acceptance**: `chirp run` starts the app. `GET /` returns a response. Database creates users table.

### Task 1.2 — Registration flow

Registration form with username, email, password, password confirmation. Server-side validation (unique username/email, password strength). Insert user with hashed password.

**Files**: `pages/register/page.py`, `pages/register/page.html`, `store/users.py`
**Acceptance**: `POST /register` with valid data creates a user. `POST /register` with duplicate email returns 422 with error fragment. `uv run pytest tests/test_auth.py::TestRegistration` passes.

### Task 1.3 — Login + session

Login form, session creation, redirect to boards. Logout clears session.

**Files**: `pages/login/page.py`, `pages/login/page.html`
**Acceptance**: Login with valid credentials sets session cookie. Login with invalid credentials returns error fragment. Logout clears session. Protected pages redirect to `/login`.

### Task 1.4 — Password reset (email optional)

Token-based password reset. If email sending is not yet wired, the reset token can be logged to console in debug mode.

**Files**: `store/users.py` (token generation), reset page handlers
**Acceptance**: Reset request generates a signed token. Token URL renders reset form. New password is hashed and stored. Used token cannot be reused.

### Task 1.5 — App shell layout

Set up the chirpui app shell with topbar (brand, user menu), sidebar (board navigation placeholder), and main content area with hx-boost.

**Files**: `pages/_layout.html`, `pages/_context.py`, `pages/_meta.py`
**Acceptance**: All pages render inside the app shell. Navigation between pages uses htmx boost (no full page reload). Unauthenticated users see login/register links.

---

## Sprint 2: Core Forum (Boards, Threads, Posts)

**Goal**: Users can browse boards, read threads, create threads, and post replies with markdown.

### Task 2.1 — Board listing

Board index page showing categories with boards. Each board shows name, description, thread count, last post info.

**Files**: `pages/boards/page.py`, `pages/boards/page.html`, `store/boards.py`, `migrations/002_create_boards.sql`
**Acceptance**: `GET /boards` renders board list. Boards are grouped by category. Thread count and last post info are accurate. Fragment request returns board list only (no shell).

### Task 2.2 — Thread listing with pagination

Thread list for a board with pinned threads on top, sorted by last_post_at desc. Pagination component.

**Files**: `pages/boards/{board_slug}/page.py`, `pages/boards/{board_slug}/page.html`, `store/threads.py`, `store/pagination.py`, `templates/components/_pagination.html`, `migrations/003_create_threads_posts.sql`
**Acceptance**: `GET /boards/{slug}` renders paginated thread list. `GET /boards/{slug}?page=2` renders page 2. Pagination links use `hx-get` for fragment swaps. `rg 'OFFSET' store/threads.py` confirms SQL pagination.

### Task 2.3 — Thread view with posts

Post list for a thread. Each post shows author, character (if any), avatar, markdown content, timestamp. Cursor-based pagination (load more).

**Files**: `pages/boards/{board_slug}/{thread_id}/page.py`, `pages/boards/{board_slug}/{thread_id}/page.html`, `store/posts.py`, `templates/components/_post.html`
**Acceptance**: `GET /boards/{slug}/{id}` renders post list. Markdown is rendered to HTML via patitas. Posts display author info and timestamps. "Load more" button fetches next page as fragment.

### Task 2.4 — Create thread + reply

New thread form (title + first post content). Reply form at the bottom of thread view. Both use markdown textarea with preview.

**Files**: `pages/boards/{board_slug}/new/page.py`, `pages/boards/{board_slug}/new/page.html`, API route for POST /posts
**Acceptance**: `POST` new thread creates thread + first post, redirects to thread. `POST` reply adds post, returns OOB fragment (new post + updated post count). Empty content returns 422 with error fragment.

### Task 2.5 — Breadcrumbs + context cascade

Each level provides breadcrumb context: Home → Board Name → Thread Title. Sidebar shows board list with active state.

**Files**: `_context.py` at each routing level, `_meta.py` at each level
**Acceptance**: Breadcrumbs render correctly at every depth. Sidebar highlights current board. Context cascade verified: board context available in thread pages.

---

## Sprint 3: Real-Time & Notifications

**Goal**: New posts appear live in open threads. Users see unread indicators and notification badges.

### Task 3.1 — Per-thread SSE

SSE endpoint scoped to a thread. When a user posts a reply, all connected clients receive the new post as a rendered fragment.

**Files**: API route `/threads/{id}/events`, ReactiveBus integration in post creation
**Acceptance**: Open thread in two browser tabs. Post reply in tab A. Post appears in tab B within 2 seconds without refresh. `uv run pytest tests/test_realtime.py` passes.

### Task 3.2 — Unread tracking

Track last-read post per user per thread. Thread list shows unread indicator. Viewing a thread updates the read marker.

**Files**: `store/notifications.py`, `migrations/005_create_notifications.sql` (includes thread_reads)
**Acceptance**: Thread list shows "unread" badge for threads with new posts. Visiting thread clears the badge. `SELECT` from thread_reads confirms read marker updates.

### Task 3.3 — Notification system

Notifications for: reply to your thread, reply to a thread you posted in, @mention in a post. Notification bell in topbar with unread count (OOB-updated).

**Files**: `store/notifications.py`, `templates/components/_notification.html`, OOB fragment in shell
**Acceptance**: Posting a reply creates notifications for thread participants. Notification count in topbar updates via OOB. Clicking notification navigates to the post.

### Task 3.4 — Typing indicator (stretch)

When a user is composing a reply, other users in the thread see "[username] is typing..." as a transient SSE event.

**Acceptance**: Typing indicator appears within 500ms. Disappears after 3 seconds of inactivity. No database writes (SSE-only, ephemeral).

---

## Sprint 4: Characters & PBP Features

**Goal**: Users can create characters, post as characters, and customize their experience.

### Task 4.1 — Character CRUD

Create/edit/delete characters. Each character has a name, avatar, bio, and freeform sheet (JSONB).

**Files**: `store/characters.py`, `pages/settings/characters/` (CRUD pages), `migrations/004_create_characters.sql`
**Acceptance**: User can create a character. Character appears in profile. Character can be edited/archived. `uv run pytest tests/test_characters.py` passes.

### Task 4.2 — Post-as-character

Reply form includes character selector (dropdown of user's active characters). Posts display character name and avatar instead of (or alongside) username.

**Files**: `templates/components/_post.html` (character display), reply form update
**Acceptance**: Reply with character selected shows character badge on post. Reply without character shows username. Character association is stored in posts table.

### Task 4.3 — User profiles

Public profile page showing user info, character gallery, recent posts, and post count.

**Files**: `pages/profile/{username}/page.py`, `pages/profile/{username}/page.html`
**Acceptance**: `GET /profile/{username}` shows user info and characters. Recent posts are paginated. Non-existent username returns 404.

### Task 4.4 — Theming

CSS custom properties for theme switching. Two built-in themes (light + dark). Theme preference stored in user settings and applied via `data-theme` attribute.

**Files**: `static/themes/default.css`, `static/themes/dark.css`, `pages/settings/page.py`
**Acceptance**: User can switch themes in settings. Theme persists across sessions. No FOUC on page load.

---

## Sprint 5: Moderation & Search (Stretch)

**Goal**: Moderators can manage content. Users can search threads and posts.

### Task 5.1 — Moderation tools

Pin/lock threads. Delete/edit posts (mod override). Ban users. Mod action audit log.

### Task 5.2 — Full-text search

PostgreSQL `tsvector` + `tsquery` for post content search. Search results page with highlighted matches and pagination.

### Task 5.3 — Rate limiting

Per-user rate limiting on post creation (prevent spam). Uses Chirp's existing rate limiting middleware with per-route configuration.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Pagination helper design doesn't generalize | Medium | High | Sprint 0 designs both offset and cursor modes before code. Test with threads (offset) and posts (cursor) in Sprint 2. |
| SSE per-thread scoping hits ReactiveBus limits | Low | High | Sprint 0 designs scoping. Sprint 3 implements. Chat example already proves the pattern at small scale. |
| Email sending blocks registration flow | Medium | Medium | Sprint 1 Task 1.4 makes email optional in debug mode (log token to console). Email integration is not on the critical path. |
| mount_pages at 4 levels of nesting hits framework bugs | Medium | High | Invariant 1 — no framework forks. If bugs appear, file upstream and work around. pages_shell example validates 3 levels already. |
| Markdown rendering is too slow for large threads | Low | Medium | Sprint 2 pre-renders HTML on post creation (content_html column). Rendering happens once at write time, not on every read. |
| Schema migrations become unwieldy | Low | Low | Forward-only migrations with Chirp's built-in runner. Keep migrations small and atomic. |

---

## Success Metrics

| Metric | Current | After Sprint 2 | After Sprint 4 |
|--------|---------|----------------|----------------|
| Pages in app | 0 | 8 (login, register, boards, board, thread, new thread, profile, settings) | 12+ (add character CRUD, password reset) |
| Database tables | 0 | 4 (users, boards, threads, posts) | 7 (add characters, notifications, thread_reads) |
| Test count | 0 | 30+ (auth + forum CRUD) | 60+ (add realtime, characters, theming) |
| Framework gaps found | 0 | 1–3 (pagination, registration patterns) | 3–6 (SSE scoping, notification patterns) |
| Can a user play PBP? | No | Read-only (browse + post) | Yes (characters, live updates, theming) |

---

## Relationship to Existing Work

- **chirp-ui components** — The forum will use chirpui app shell, cards, forms, and badges. It exercises the component collection in a real product context. Any chirpui gaps become PRs upstream.
- **Accessibility contracts (epic, complete)** — Forum templates will be validated by the a11y contract rules shipped in 0.4.0. This is the first product-scale test of those rules.
- **Contract extensions RFC (phases 1-3)** — Dead template detection, SSE fragment validation, and form field validation will all fire on the forum's templates. First real-world validation of these rules.
- **Kanban shell example (complete)** — The kanban_shell demonstrated mount_pages + chirpui + SSE + OOB at example scale. The forum takes the same stack to product scale.

---

## Changelog

- 2026-04-12: Initial draft based on framework audit and codebase exploration.
