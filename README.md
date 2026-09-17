# CodeLearn (Python / Django Edition)

Interactive Programming Learning & Academic Management System — rebuilt on
**Django** instead of Laravel, with the performance/recommendation
algorithm upgraded from a hardcoded rule to a small **machine-learning
pipeline** (easier to document formally: features, training, metrics).

This is a working proof-of-concept: run `python manage.py demo_pipeline`
to see all three algorithms execute against seeded data.

---

## 1. What changed vs. the original spec

| Area | Original spec | This build |
|---|---|---|
| Backend | Laravel (PHP) | **Django (Python)** |
| Frontend | Blade + Tailwind | Django templates + Tailwind (Phase 3) |
| Weak-topic detection | Hardcoded `score < 50` rule | **Algorithm 2**: trained Logistic Regression / Naive Bayes classifier |
| Recommendation | Flat Beginner/Intermediate/Advanced bucket | **Algorithm 3**: K-Nearest Neighbors peer-based recommender |
| Code evaluation | Isolated container, rule-based | Unchanged in concept (**Algorithm 1**) — still deterministic, still isolated |

Three algorithms now exist instead of two, which maps cleanly onto a
report structure (one section each, with its own math/diagram):

```
Student submits code
        │
        ▼
Algorithm 1 — Automated Code Evaluation   (deterministic, sandboxed)
        │
        ▼
Feature Engineering  (quiz/assignment/coding/attendance → feature vector)
        │
        ▼
Algorithm 2 — Weak-Topic Classifier        (Logistic Regression / Naive Bayes)
        │
        ▼
Algorithm 3 — Peer Recommendation (KNN)    (finds similar students, recommends what worked)
```

---

## 2. Project structure

```
codelearn/
├── accounts/          # Custom User model + Teacher/Student/Parent profiles, role-based
├── academics/         # SchoolClass, Subject, Course, Topic, Lesson, Enrollment
├── assignments/       # Assignment, TestCase, Submission, TestCaseResult
├── quizzes/           # Quiz, Question, AnswerOption, QuizAttempt, StudentAnswer
├── attendance/        # AttendanceRecord + percentage calculation
├── campus/            # Views/templates for all 4 role dashboards + sub-pages
├── code_runner/
│   ├── sandbox.py     # Local execution OR forwards to code-runner service (CODE_RUNNER_URL)
│   └── evaluator.py   # Algorithm 1: runs test cases, scores submissions
├── code_runner_service/   # Standalone Flask microservice for the isolated code-runner container
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── ml_engine/
│   ├── models.py      # StudentTopicFeature, Recommendation
│   ├── services/
│   │   ├── feature_engineering.py   # raw activity -> feature vector
│   │   ├── weak_topic_classifier.py # Algorithm 2 (LogisticRegression / GaussianNB)
│   │   └── knn_recommender.py       # Algorithm 3 (K-Nearest Neighbors)
│   └── management/commands/
│       └── demo_pipeline.py         # seeds data + runs the full pipeline end-to-end
├── static/css/codelearn.css   # Design system used by all templates
├── docker/entrypoint.sh       # Web container startup: wait-for-db, migrate, collectstatic
├── nginx/nginx.conf           # Reverse proxy config
├── codelearn/          # Django project settings/urls
├── Dockerfile          # Web app image
├── podman-compose.yml  # Full deployment: db + code-runner + web + nginx
├── .env.example
├── requirements.txt
└── manage.py
```

---

## 3. Algorithm 1 — Automated Code Evaluation

Deterministic; no ML. Student code runs in `code_runner/sandbox.py`
(subprocess with CPU/memory/timeout limits locally, or forwarded to the
isolated `code-runner` container in production — see §13), then
`code_runner/evaluator.py` compares actual vs. expected output per test
case and computes a weighted score:

```
score = ( Σ weight of passed test cases / Σ weight of all test cases ) × 100
```

## 4. Algorithm 2 — Weak-Topic Classifier

**Input (feature vector, per student per topic):**
`[quiz_score, assignment_score, coding_score, avg_attempts_before_pass,
avg_submission_time_seconds, attendance_rate]`

**Model:** `sklearn.linear_model.LogisticRegression` (alt: `GaussianNB`)
**Output:** `weak_probability ∈ [0, 1]`, thresholded at 0.5 → `is_weak`

Labels are bootstrapped early on using the original weighted-score rule
(`quiz×0.3 + assignment×0.3 + coding×0.4 < 50`), then can be retrained on
real outcome data (e.g. did the student later pass the topic) as it
accumulates — this is the documentable justification for using a trained
model instead of a fixed threshold.

Evaluated with train/test split + accuracy, precision, recall, F1
(see `weak_topic_classifier.train()`).

## 5. Algorithm 3 — Peer Recommendation (KNN)

For a student flagged weak in a topic:
1. Standardize all students' feature vectors for that topic (z-score).
2. `sklearn.neighbors.NearestNeighbors` finds the *k* closest peers
   (Euclidean distance in standardized space).
3. Check how many of those peers are now *not* weak (`is_weak=False`).
4. Recommend the topic's lesson, with `confidence = improved_neighbors / k`.

---

## 6. Running it

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py demo_pipeline     # seeds data, runs Algorithms 1–3, prints results
python manage.py createsuperuser   # to browse data via /admin
python manage.py runserver
```

Requires `gcc` (for C submissions) and a JDK (`javac`) for Java
submissions to work locally; Python submissions need no extra tooling.

---

## 7. Still to build

- Scheduled retraining of Algorithm 2 (management command / Celery task,
  triggered periodically instead of via `demo_pipeline`)
- Persisting trained models (joblib) instead of retraining per request
- Quiz-taking UI for students (quiz data model exists; no page yet)
- TLS termination in front of nginx for production
- CI (lint + migration check + a smoke test hitting each dashboard)

## 8. License

Educational / academic project.

---

## 9. Dashboards (new)

Role-based dashboards are now live at `/dashboard/` (redirects from `/`),
backed by real queries against the models above — not mockups.

- `campus/` — the views/templates app. `campus/views.py` routes each
  signed-in user to their role's dashboard and pulls live stats
  (enrollment counts, submission status, attendance %, weak-topic flags,
  KNN recommendations, etc).
- `static/css/codelearn.css` — the design system (palette, type scale,
  card/badge/table components) used by every template.
- Auth uses Django's built-in `LoginView`/`LogoutView` — `campus/login.html`.

Try it:

```bash
python manage.py migrate
python manage.py demo_pipeline      # seed data + run Algorithms 1-3
python manage.py runserver
```

Then visit `http://127.0.0.1:8000/login/` and sign in (password `pass1234`
for every demo account):

| Role | Usernames |
|---|---|
| Admin | `admin1` |
| Teacher | `teacher1`, `teacher2` |
| Student | `student0` .. `student23` |
| Parent | `parent1` .. `parent6` |

---

## 10. Sidebar sub-pages (new)

Every sidebar link now points to a real, working page instead of the
dashboard placeholder — all backed by live queries.

| Role | Pages |
|---|---|
| Admin | `/students/`, `/teachers/`, `/courses/`, `/reports/` |
| Teacher | `/courses/`, `/assignments/` (+ detail/review per assignment), `/attendance/` (mark today's attendance per course), `/submissions/` (+ detail with per-test-case results) |
| Student | `/courses/`, `/assignments/` (+ detail with sample test cases and submission history), `/progress/` (full per-topic feature breakdown), `/attendance/` |
| Parent | `/children/` (summary cards per child), `/attendance/`, `/progress/` — both scoped to the selected child via `?child=<id>` |

Notable pieces:
- **Attendance marking** (`/attendance/mark/`, teacher-only, POST) writes
  real `AttendanceRecord` rows via `update_or_create`, so re-marking the
  same day is idempotent.
- **Submission detail** (`/submissions/<id>/`) shows the exact submitted
  source code and a per-test-case pass/fail table — shared by both the
  teacher review view and the student's own submission history.
- Django's `reverse()` is used for all nav links (see `campus/views.py:_nav_for`),
  so the sidebar can't silently point at a dead URL.

---

## 11. Code editor / submission page (new)

Students can now write and submit code directly from the browser —
`/assignments/<id>/submit/` — instead of submissions only being created
via the seed script.

- `campus/templates/campus/assignment_submit.html` — a styled textarea
  editor (tab-key inserts spaces, monospace, dark "code" panel matching
  the design system) pre-filled with starter code per language, or the
  student's last attempt if they're resubmitting.
- `campus/views.py:assignment_submit` — on POST, creates a real
  `Submission` row and calls `code_runner.evaluator.evaluate_submission()`
  synchronously (the same function the seed script uses), so the
  submitted code runs through the actual sandboxed evaluator against
  the assignment's test cases, then redirects to the submission detail
  page showing the real pass/fail result.
- Linked from both the assignment detail page ("Write & submit code")
  and the assignment list ("Submit" / "Resubmit").

Note: evaluation runs synchronously in the request/response cycle for
simplicity. For a production deployment with longer-running or
concurrent submissions, move `evaluate_submission()` into a background
task queue (e.g. Celery) and poll/redirect once grading completes.

---

## 12. Richer demo data (new)

`python manage.py demo_pipeline` now seeds a much more realistic dataset
in one run:

- **Admin** (`admin1`), **2 teachers** (`teacher1`, `teacher2`), **6 parents**
  (`parent1`..`parent6`, each linked to one of the first 6 students), and
  **24 students** with real first/last names — all passwords `pass1234`.
- **2 courses** (Python Programming, C Programming) across **3 topics**
  (Loops, Functions, Arrays) with **4 graded assignments** (2 per Python
  topic, so `coding_score` has real granularity — 0/50/100 — instead of
  a single pass/fail draw producing only 0 or 100).
- Each student gets a smooth, randomly distributed **ability score**
  (Gaussian, not a coin flip), and each feature (coding, quiz, attendance)
  draws **independent noise** around that ability — see `_jitter()` in
  `demo_pipeline.py` — so features aren't perfectly correlated and the
  classifier/KNN neighborhoods have realistic overlap near the decision
  boundary instead of two trivially-separable clusters.
- `weak_topic_classifier.train()` now takes a `label_noise` parameter
  (default 0.15) that adds controlled randomness to the bootstrapped
  training labels, because training a linear model directly against a
  label that's a deterministic linear function of the same input
  features would otherwise report a meaningless ~100% accuracy. With
  this demo data you should see accuracy in the 70-90% range and Algorithm
  3 (KNN) producing a real spread of confidence values (0.0-1.0) instead
  of all zeros.
- Run `python manage.py demo_pipeline --reset` to wipe and reseed all
  demo accounts and data safely.

---

## 14. Admin: add users (new)

Admins can now create any of the four account types directly from the
UI — `/users/add/`, also linked from the Students and Teachers list
pages — instead of only through `manage.py shell` or the raw Django
admin.

- `campus/forms.py:UserCreateForm` — one form covering common fields
  (username, name, email, phone, password) plus per-role fields
  (Teacher: employee ID/department; Student: roll number/class; Parent:
  occupation/children), validated together server-side regardless of
  which fields the client's JS happened to show.
- Leaving the password field blank auto-generates one
  (`generate_temp_password()`) and shows it once in a success banner —
  "share this with them securely; they can change it after signing in."
  Setting a password explicitly shows no password in the message.
- Duplicate usernames and missing role-required fields (e.g. no
  employee ID for a teacher) are rejected with inline form errors, not
  a 500 or a silent no-op.

---

## 15. Change password (new)

Any logged-in user (all four roles) can change their own password at
`/account/password/`, linked from the sidebar footer next to "Sign out".

- Uses Django's built-in `PasswordChangeForm` — validates the current
  password, enforces password strength rules, and requires the new
  password to be entered twice.
- `update_session_auth_hash()` keeps the user signed in after a
  successful change (Django would otherwise invalidate their session
  hash and force a re-login).
- Useful right after an admin creates an account with an auto-generated
  temporary password (§14) — the new user can sign in once, then come
  here to set their own.

**Note on "Sign out":** Django 5+ only accepts POST requests for
logout — a plain link (`<a href="/logout/">`) sends a GET and is
rejected. Both `base.html` and `no_role.html` use a small one-button
`<form method="post">` instead.

---

## 16. Messaging (new)

A `messaging` app providing direct and group chat between roles —
`/messages/` (inbox), linked from every role's sidebar.

- **Role-aware recipients** (`messaging/permissions.py:allowed_recipients`)
  — nobody can message just anyone:
  - **Admin** → anyone
  - **Teacher** → students/parents enrolled in their own courses, other
    teachers, admins
  - **Student** → teachers of courses they're enrolled in, admins
  - **Parent** → teachers of their children's courses, admins
- **1:1 threads auto-dedupe** — starting a new conversation with someone
  you already have a direct thread with reuses it instead of creating a
  duplicate.
- **Group chats** — picking more than one recipient creates a named
  group (e.g. a teacher messaging every parent in a class at once).
- **Unread badges** — `ConversationParticipant.last_read_at` is
  updated whenever a user opens a thread; the inbox shows an
  "N new" badge per conversation until then.
- No WebSockets/Channels — this is a classic page-reload chat (send →
  redirect back to the thread), which keeps the deployment simple (no
  Redis dependency). Good enough for a school-project message board;
  swapping in Django Channels for live updates would be a natural
  Phase 4 upgrade.
- A red badge on the "Messages" sidebar item (`campus/views.py:_nav_for`)
  shows the total unread count across all conversations, and clears as
  soon as the user opens any thread with unread messages in it.
- **Messenger/Instagram-style UI**: a split-pane layout
  (`messaging/templates/messaging/_conversation_list.html` on the left,
  a chat thread on the right) with colored circular avatars (initials
  derived from each user's name — `messaging/avatars.py`), rounded chat
  bubbles (blue gradient for your own messages, gray for others), and a
  pill-shaped message composer with a round send button.
- **Mobile behavior**: below 900px, the list and thread are no longer
  cramped side-by-side — only one shows at a time (list on `/messages/`,
  thread on `/messages/<id>/`), with a "‹" back button in the thread
  header, matching how Messenger/Instagram behave on a phone.
- **"New message" screen** also restyled to match — colored avatar
  circles per contact and tap-to-select checkmarks (a real `<input
  type="checkbox">` under the hood, visually hidden and replaced with a
  CSS-only circle via the `~` sibling selector — no JS needed for the
  checkmark itself) instead of a plain checkbox list.

---

## 18. Settings page + dark mode (new)

`/account/settings/`, linked from a single "⚙ Settings" item in the
sidebar footer (replacing the old separate "Change password" / "Sign
out" links — both now live inside Settings instead).

- **Profile** — edit name, email, phone (`campus/forms.py:ProfileUpdateForm`).
- **Appearance** — Light / Dark / System, saved instantly per-user
  (`User.theme_preference` — a real DB column, not just a browser
  cookie, so it follows you across devices). Selecting an option
  auto-submits via `onchange="this.form.submit()"`.
- **Notifications** — an `email_notifications` toggle switch, stored on
  the User model. UI-only for now — there's no email backend wired up
  in this project yet, so it doesn't actually send anything; the
  groundwork (the field + the toggle) is there for whenever that's added.
- **Change password** and **Sign out** are now both inside this page.

**How dark mode actually works** (`static/css/codelearn.css` +
`campus/templates/campus/base.html`):
- All colors are CSS custom properties (`--paper`, `--surface`,
  `--text`, etc.) defined once in `:root` and overridden in a single
  `[data-theme="dark"]` block — no separate dark stylesheet, no
  duplicated rules.
- `<html data-theme="...">` is set server-side from
  `request.user.theme_preference` when it's explicitly LIGHT or DARK.
- When it's SYSTEM (the default, and also what unauthenticated visitors
  on the login page get), a tiny inline `<script>` in `<head>` — before
  the stylesheet paints — checks `prefers-color-scheme` and sets the
  attribute client-side, so there's no flash of the wrong theme.

---

## 19. Chat search (new)

A live search box above the conversation list
(`messaging/templates/messaging/_conversation_list.html`) filters chats
by contact/group name as you type — client-side, no page reload or
server round-trip, since the list is already fully rendered. Shows a
"No chats match your search" message when nothing matches.

### Fixing "I updated the CSS but the old version still shows"

This came up twice during development — stale cached static files after
a CSS change. The permanent fix is in `codelearn/settings.py`:

```python
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else
            "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
        ),
    },
}
```

`ManifestStaticFilesStorage` renames every static file to include a
content hash (e.g. `codelearn.1a3f4b16.css`) at `collectstatic` time.
Since the *filename itself* changes whenever the content changes, a
browser (or nginx, or an old Podman volume) can never serve a stale
cached copy under the new URL — there's nothing to invalidate.

**Correction from an earlier version of this doc:** it previously
claimed local `runserver` "gracefully falls back" to a plain URL
without running `collectstatic` first. That was wrong — tested properly
via `manage.py test` (§26), `ManifestStaticFilesStorage` raises a hard
`ValueError` if no manifest exists yet, full stop, regardless of
`DEBUG`. The actual fix: the storage backend is now selected based on
`DEBUG` — plain `StaticFilesStorage` (no manifest, no collectstatic
required) for local dev/tests, and the hashed manifest storage only in
production, where the Docker entrypoint always runs `collectstatic`
before starting gunicorn anyway.


---

## 17. Testing multiple accounts at once

To see e.g. a teacher and a student interacting (messaging, submitting
an assignment, checking a dashboard) at the same time, Django's session
cookie is what identifies "who's logged in" — so you need separate
cookie jars per account. Easiest options:

- **Different browsers**: Chrome for `teacher1`, Firefox for `student0`.
- **One browser, multiple profiles**: Chrome/Edge "Add profile", or
  Firefox's Multi-Account Containers extension — each gets its own
  cookie jar.
- **Incognito/private windows**: a normal window + an incognito window
  count as two separate sessions in most browsers (note: two incognito
  windows in the same browser session usually *share* cookies with each
  other, so use at most one incognito window alongside your normal one).
- **curl/requests scripts** (what I used to test above): each
  `requests.Session()` is its own independent login — useful for
  automated testing, not for clicking around by hand.





---

## 13. Podman Compose deployment (new)

Matches the original poster architecture — Browser → Web App Container ↔
Database Container, with a separate isolated Code Runner Container —
now implemented for real instead of just described.

```
Browser ──▶ nginx :8080 ──▶ web (Django/gunicorn) ──▶ db (MySQL 8)
                                     │
                                     └──▶ code-runner (isolated, internal-only network)
```

**Services** (`podman-compose.yml`):

| Service | Image | Notes |
|---|---|---|
| `db` | `mysql:8.4` | Persistent volume, healthcheck gates `web` startup |
| `code-runner` | built from `code_runner_service/` | The **only** container that ever executes untrusted student code |
| `web` | built from the repo root `Dockerfile` | Django + gunicorn, runs migrations/collectstatic on boot via `docker/entrypoint.sh` |
| `nginx` | `nginx:1.27-alpine` | Reverse proxy + serves `/static/` and `/media/` directly |

**Code-runner isolation**, applied at the compose level rather than
relying on application code alone:
- `runner_internal` network is `internal: true` — no route to the
  outside world, and only the `web` service is also attached to it, so
  nothing else on the host or in `db`/`nginx` can reach it either.
- `read_only: true` rootfs + a small `tmpfs` mount for compiler scratch
  space (test binaries, `.class` files) — nothing persists between runs.
- `cap_drop: [ALL]`, `no-new-privileges`, non-root user (see
  `code_runner_service/Dockerfile`), and `mem_limit`/`cpus` caps so a
  runaway or malicious submission can't starve the host.

**How the app talks to it:** `code_runner/sandbox.py` picks between two
identical-API execution paths based on the `CODE_RUNNER_URL` environment
variable:
- **unset** (local dev, `demo_pipeline`) → runs directly in-process via
  `subprocess` + `resource` limits, no containers needed.
- **set** (as it is in `podman-compose.yml`, to `http://code-runner:6000`)
  → forwards the exact same request over HTTP to the isolated container
  instead. `code_runner/evaluator.py` (Algorithm 1) doesn't know or care
  which mode is active.

**Running it:**

```bash
cp .env.example .env
# edit .env: set DJANGO_SECRET_KEY, DB_PASSWORD, DB_ROOT_PASSWORD to real values

podman-compose up --build
# or: docker compose up --build (file is compatible with both)
```

Then visit `http://localhost:8080`. First boot runs migrations
automatically; seed demo data with:

```bash
podman-compose exec web python manage.py demo_pipeline
podman-compose exec web python manage.py createsuperuser   # optional, in addition to demo admin1
```

**Not yet included:** TLS termination (put a real cert on nginx or put
this behind a load balancer that terminates TLS), and a process to
periodically retrain Algorithm 2 (see the "still to build" list above —
a Celery beat schedule or a cron-triggered management command would
both work).

---

## 20. Small polish: profile pictures, favicon, custom error pages (new)

- **Profile picture upload** — `User.profile_picture` (the field
  already existed in the model) now has a real upload UI in Settings →
  Profile, with a live preview. Falls back to the same colored-initials
  avatar used everywhere else in the chat UI when no picture is set.
  `MEDIA_URL`/`MEDIA_ROOT` are configured in `settings.py`; served by
  Django itself in local dev (`codelearn/urls.py`, only when `DEBUG`) and
  by nginx's `/media/` location in production — no code change needed
  between the two.
- **Favicon** — `static/favicon.svg`, a simple inline `</>` mark
  matching the sidebar brand icon. Linked from every standalone page
  (`base.html`, `login.html`, `no_role.html`, and the new error pages).
- **Custom 404 / 500 pages** — `templates/404.html` and
  `templates/500.html` at the project root (added `BASE_DIR / 'templates'`
  to `TEMPLATES[0]['DIRS']` so Django finds them). Both are deliberately
  **standalone** — they don't extend `campus/base.html` — because
  Django renders `500.html` with no request/context at all, so anything
  depending on `request.user` or `nav_items` would break exactly when
  you need the error page to work.
  **Note:** these only appear when `DJANGO_DEBUG=false` — with `DEBUG=True`
  (the default for local `runserver`), Django shows its own detailed
  debug page instead, regardless of custom templates. To see them
  locally: `DJANGO_DEBUG=false DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 python manage.py runserver`.

---

## 21. Show-password toggle, pagination, and admin search (new)

- **Show/hide password** — a 👁/🙈 button next to password fields on
  login and change-password (`.password-field-wrap` /
  `.password-toggle-btn` in `codelearn.css`, toggled by a small
  `togglePassword()` JS function). Not added to the admin "Add user"
  password field, which is intentionally plain text already so the
  admin can read/copy the password they're setting.
- **Pagination** — `campus/views.py:_paginate()` is a small reusable
  helper wrapping Django's `Paginator`, used on Students, Teachers, and
  Submissions (15/15/20 per page). `campus/templates/campus/_pagination.html`
  is a shared Prev/Next partial that preserves any active search/filter
  query params across page links.
- **Search/filter on admin lists**:
  - **Students** (`/students/?q=`) — matches name, username, or roll number.
  - **Teachers** (`/teachers/?q=`) — matches name, username, employee ID, or department.
  - **Submissions** (`/submissions/?q=&status=`) — matches student name
    or assignment title, plus an exact status filter dropdown
    (auto-submits on change).
  All three are server-side (a real filtered/paginated queryset, not a
  client-side JS filter over already-loaded rows), so they scale
  correctly as the dataset grows — unlike the messaging search (§19),
  which is intentionally client-side since that list is small and
  already fully loaded.

---

## 22. CSV export, mark-all-as-read, and server timezone (new)

- **CSV export**:
  - `/students/export/` — respects the current `?q=` search, so
    exporting after a search only exports matching rows.
  - `/reports/export/` — one file with both report tables (students by
    class, submissions by status) separated by a blank line.
  - `/attendance/export/?course=<id>` — a teacher's roster + attendance
    % for one course.
  All three use a shared `_csv_response()` helper in `campus/views.py`
  (just `csv.writer` over an `HttpResponse` with a `Content-Disposition`
  header — no extra dependency needed).
- **Mark all as read** — a button in the Messages topbar (only shown
  when something's actually unread) that updates every
  `ConversationParticipant.last_read_at` for the current user in one
  query, clearing the nav badge (§17) immediately.
- **Server timezone** — `TIME_ZONE` is now `Asia/Kathmandu` by default
  (configurable via `DJANGO_TIME_ZONE` in `.env`) instead of `UTC`, so
  displayed dates/times match the deployment's local time. This is a
  single server-wide setting, not a per-user preference — if the school
  ever has users across different timezones, a `User.timezone` field
  (same pattern as `theme_preference`) plus Django's
  `django.utils.timezone.activate()` in a small middleware would be the
  natural next step.

---

## 23. Remember-me login, bulk CSV import, and quiz-taking (new)

- **Remember me** — a checkbox on login (`campus/views.py:RememberMeLoginView`,
  a thin subclass of Django's `LoginView`). Checked → session persists
  30 days (`REMEMBER_ME_DAYS`). Unchecked → session ends when the
  browser closes, via `request.session.set_expiry(0)`.
- **Bulk CSV import** — `/users/import/`, linked from the "Add user"
  page. Admins upload a CSV to create many accounts at once; a
  downloadable template (`/users/import/template/`) documents the
  expected columns. Each row is validated and reported independently
  (`_create_account_from_row()` in `campus/views.py`) — one bad row
  (duplicate username, missing required field) doesn't block the rest
  of the file, and the results table shows exactly which rows succeeded
  and why any failed.
- **Quiz-taking page for students** — the quiz data model
  (`Quiz`/`Question`/`AnswerOption`/`QuizAttempt`/`StudentAnswer`)
  existed from the start but had no UI. Now: `/quizzes/` (list, with
  score shown once attempted), `/quizzes/<id>/take/` (one form with all
  questions — MCQ as radio buttons, Output Prediction/Debugging as text
  input, graded server-side on submit), `/quizzes/attempts/<id>/`
  (result breakdown, revealing the correct answer only for questions
  gotten wrong). One attempt per quiz — revisiting `/take/` after
  submitting redirects straight to the existing result. Submitting a
  quiz triggers the same `build_feature_vector()` call assignments do,
  so a real quiz attempt immediately feeds Algorithms 2 and 3.

**Bug fix found while building this:** `feature_engineering.py`'s
`quiz_score` was averaging `QuizAttempt.score` directly as if it were
always already a 0–100 percentage — true for the seeded demo data
(`total_marks=100`), but wrong for a real quiz with a different total
(e.g. 7 marks across 4 questions), where a perfect score would've been
recorded as a `quiz_score` of `7` instead of `100`. Fixed to average
each attempt's `.percentage` property instead of the raw `score`.

---

## 24. Notification center, report card PDF, and certificates (new)

### Notification center

A new `notifications` app — `Notification(user, category, message,
link, is_read, created_at)`. Deliberately **event-driven**, not a
scheduler-based reminder system (this project has no Celery/cron), so
notifications fire at the moment something real happens:

- A submission is graded → `code_runner/evaluator.py` calls `notify()`.
- The classifier newly flags a topic weak (not already flagged, so a
  retrain doesn't re-notify) → `weak_topic_classifier.py`.
- A new message arrives → `messaging/views.py:_send_message()`, the
  single choke point all three message-creation call sites now route
  through, so this couldn't be missed on one of them.

A 🔔 bell icon with an unread-count badge sits in the topbar on every
page (`campus/context_processors.py:unread_notification_count` — a
context processor, not per-view context, since the bell needs to show
up site-wide without touching every single view). `/notifications/`
lists them; clicking one marks it read and redirects to its `link`;
"Mark all as read" clears everything in one query — same pattern as
the messaging inbox (§22).

### Report card (PDF)

`/students/<id>/report-card.pdf` — built with `reportlab` (Platypus),
per the project's `pdf` skill guidance. Shows overall average score,
overall attendance, and a per-topic table (quiz/assignment/coding
scores + weak/on-track status). Access is gated by
`_can_view_student_records()`: admin/teacher can view anyone's, a
student their own, a parent their own children's. Linked from the
admin Students list, the student's own Progress page, and the parent's
Academic Performance page.

### Certificate of completion (PDF)

`/students/<id>/certificate/<course_id>.pdf` — a single decorative
landscape page built with `reportlab`'s low-level `canvas` API (double
border, serif certificate typography). Gated by
`_course_completion_percent()`, a **documented, simple** metric: the
average `coding_score` across all the course's topics, compared
against `COMPLETION_THRESHOLD = 60.0`. Below the threshold, generation
is refused with a message stating the student's actual current
percentage — not a silent failure. This metric is intentionally basic;
a real deployment would likely want a school-specific completion
policy (e.g. requiring every assignment passed, not just an average)
swapped in here. Linked from the student's own Courses page.

---

## 25. Plagiarism detection, discussion forums, and calendar (new)

### Algorithm 4 — Code Similarity Detection

`code_runner/plagiarism.py`. For a given assignment, compares every
student's most recent submission against every other's: strips
comments, tokenizes the remaining source (identifiers/keywords/
punctuation), then scores similarity with `difflib.SequenceMatcher`
over the token streams. This survives cosmetic disguises (renamed
variables, reformatted whitespace, different comments) while staying
dependency-free (no AST library needed for this scope). Pairs scoring
≥75% are shown to the teacher, ranked highest first, with both
submissions' full source side by side — `/assignments/<id>/plagiarism/`,
linked from the teacher's assignment detail page. This is explicitly
framed as a **review aid, not a verdict**: two students independently
solving a genuinely trivial problem will legitimately produce
near-identical short solutions.

### Discussion forum per topic

A new `ForumPost` model on `academics` (topic, author, optional
`parent` for one level of replies — flat, not deeply nested).
`/courses/<id>/topics/` lists a course's topics with lesson and post
counts; `/topics/<id>/forum/` is the actual Q&A board — post a
question, anyone with access to that course (enrolled student, the
teaching teacher, admin, or a parent of an enrolled student) can reply.
Access is gated by a new shared `_user_can_access_course()` helper.

### Calendar view

`/calendar/` — a real month-grid calendar (`calendar.Calendar` from the
Python standard library generates the day grid; no new dependency),
showing assignment deadlines and quiz due dates as colored pills on
each day, plus a chronological list below the grid. Prev/Month
navigation via `?year=&month=`. Role-aware: students and teachers see
their own courses' events; parents see a selected child's (with the
same child-switcher pattern used elsewhere); admins see everything.

**Model change**: added `Quiz.due_date` (nullable — existing quizzes
without one just don't appear on the calendar) since the model
previously had no due-date concept at all, only `time_limit_minutes`
(how long the quiz takes once started, not when it's due).

---

## 26. Persisted models, scheduled retraining, TLS, and CI (new)

### Persisted ML models

`ml_engine/services/weak_topic_classifier.py` now saves the fitted
model to disk with `joblib` after training (`ml_models/weak_topic_classifier.joblib`,
plus a `.meta.json` sidecar with the training report and timestamp).
`predict_single()` loads this automatically when no model is passed
explicitly — the intended path for scoring one new feature row (e.g.
right after a submission) without paying the cost of retraining the
whole classifier. `ml_models/` is a dedicated named volume in
`podman-compose.yml` so it survives container rebuilds.

### Scheduled classifier retraining

A new management command, `python manage.py retrain_models`, is the
production counterpart to `demo_pipeline`'s training steps (rebuild
features → retrain Algorithm 2 → refresh Algorithm 3 recommendations)
without the demo data seeding. A new `scheduler` service in
`podman-compose.yml` — the same web image, just looping this command
via `docker/scheduler_loop.sh` instead of running gunicorn — runs it
every `RETRAIN_INTERVAL_SECONDS` (default: once a day, configurable in
`.env`). No Celery/Redis needed for one periodic job; if more scheduled
jobs get added later, that would be the natural next upgrade.

### TLS / HTTPS

`nginx/nginx.tls.conf` — an HTTPS-terminating variant of the nginx
config (HTTP redirects to HTTPS; HTTPS serves the app) — alongside the
default plain-HTTP `nginx.conf`, so the existing working setup isn't
disturbed by default. `nginx/certs/generate_self_signed.sh` generates
a local-testing certificate (`openssl req -x509 ...`); real deployments
should mount a real certificate (e.g. via certbot/Let's Encrypt)
instead. Switching is documented directly in `podman-compose.yml`'s
`nginx` service as commented-out volume lines.

### CI

`.github/workflows/ci.yml` runs on every push/PR to `main`: installs
system deps for `mysqlclient` (matching the Dockerfile), lints with
`ruff` (`E9`/`F` only — syntax errors and undefined names, not full
style, since this project wasn't written lint-clean from day one),
checks for missing migrations (`makemigrations --check --dry-run`),
runs `manage.py check`, and runs the new smoke test suite
(`campus/tests.py:SmokeTest`) — logs in as each of the four demo roles
and hits their dashboard plus several key pages, confirming nothing
500s. `requirements-dev.txt` adds `ruff` on top of the runtime
`requirements.txt`.

**Two real bugs this caught:**
1. `ruff` found ~25 unused-import lint errors, all leftover
   `startapp` boilerplate (`from django.shortcuts import render` /
   `from django.test import TestCase` in never-touched `views.py`/`tests.py`
   stubs across several apps) — harmless, but now clean.
2. Running the smoke tests surfaced that `ManifestStaticFilesStorage`
   (§20/§25) actually **raises** `ValueError` on a fresh checkout with
   no `collectstatic` ever run — contradicting what an earlier version
   of this README claimed ("gracefully falls back"). That claim was
   wrong; it only appeared to work locally because a stale manifest
   happened to already exist on disk from earlier testing. Real fix:
   `STORAGES` now picks plain `StaticFilesStorage` when `DEBUG=True`
   (dev/tests, no `collectstatic` needed) and the hashed manifest
   storage only when `DEBUG=False` (production, where the Docker
   entrypoint always runs `collectstatic` first anyway).





