# Prepwise: Security Re-Audit (after Phases 1–3)

**Scope:** the full repository after the Phase 1–3 fixes (branch `fix/frontend-bugs`, commit `354c072`).

**Method:**

- An independent adversarial code review.
- Hands-on reproduction with the Flask test client on a throwaway database.
- A fuzzer that sends malformed input to every route.
- Crafted resume files.
- `pip-audit` and `bandit`.

**Constraints:** no code was changed during this re-audit. Secrets were not read or printed.

**Confidence labels:**

- **Confirmed:** reproduced.
- **Likely:** strong code evidence, not run.
- **Potential:** needs runtime verification.

---

## 1. Summary

The Phase 1–3 fixes hold up. All 28 original findings are fixed in code, except the two that need your action (M-04 and M-05).

The re-audit found **3 new High issues**, and I reproduced each of them myself:

1. **N-01 Account takeover on unverified accounts.** This is a **regression from my L-01 fix**. A password someone sets by re-registering an unverified email is applied when the real owner later verifies.
2. **N-02 Ownership check bypass.** Sending two different `candidate_id` values in one request lets a user write questions and problems into another user's profile. With AI enabled, it can also expose parts of that user's resume.
3. **N-03 Resume-parser denial of service, no login needed.** A crafted **3.7 KB PDF** took **65 s and 2.2 GB of memory** to parse. A handful of uploads can take the site down.

There are also 4 Medium issues:

- An open redirect: the `next` check I had listed as a positive control is bypassable.
- Unbounded code-runner output.
- The Docker sandbox can't read the submitted code on Linux hosts.
- Worker-thread exhaustion.

The remaining issues are Low or informational.

**Tooling:**

- `pip-audit`: no known vulnerabilities.
- `bandit`: 0 medium/high issues.
- Tests: 127 passed.

---

## 2. Status of the original findings

| ID | Title | Status |
|---|---|---|
| C-01 | Unsandboxed code execution | ✅ Fixed and verified (no execution without a sandbox). ⚠ See N-06 for Linux Docker hosts |
| C-02 | Hardcoded SECRET_KEY fallback | ✅ Fixed and verified (refuses to start) |
| H-01 | Upload path traversal | ✅ Fixed and verified (random names; traversal names tested) |
| H-02 | OTP race / no rate limit | ✅ Fixed and verified (atomic attempts; 40 parallel guesses → max 4 evaluated) |
| H-03 | Werkzeug debugger | ✅ Fixed and verified |
| M-01 | No rate limiting | ✅ Fixed. ⚠ Small gaps: N-09, N-10 |
| M-02 | No CSRF | ✅ Fixed and verified (form, text/plain and multipart all rejected without a token) |
| M-03 | Sessions survive password reset | ✅ Fixed and verified. Logout itself doesn't revoke a copied cookie (N-11) |
| M-04 | Credentials in the shared zip | ⏳ **Your action**: rotate credentials |
| M-05 | Resumes and DB in the shared zip | ⏳ **Your action**: delete the shared copies |
| M-06 | Resume PII in the cookie | ✅ Fixed and verified (192-bit opaque id, 24 h expiry) |
| M-07 | Unbounded uploads / parser DoS | ⚠ **Partly fixed**: the 5 MB cap works, but tiny crafted files still exhaust the parser → **N-03** |
| M-08 | LLM cost abuse | ✅ Fixed (per-user hourly and daily budgets) |
| M-09 | Prompt injection → executed code | ✅ Fixed (server-side profile, clipped fields, sandbox-only execution) |
| M-10 | Security headers | ✅ Fixed and verified (CSP nonces on every script; headers present) |
| M-11 | Account enumeration | ✅ Fixed (identical responses). Small timing residue: N-12 |
| L-01 | Unverified-account password overwrite | ❌ **Fix introduced a regression → N-01** |
| L-02 | OTP/email in logs | ✅ Fixed |
| L-03 | Unpinned dependencies | ✅ Fixed (capped; pip-audit clean) |
| L-04 | Pickle model loading | ✅ Fixed (HMAC-signed files only) |
| L-05 | Mass assignment on profile | ✅ Fixed and verified (whitelist and caps) |
| L-06 | DB TLS | ✅ Fixed for URL form. ⚠ Other connection-string forms missed (N-14) |
| L-07 | Docker container outlives timeout | ✅ Fixed (container killed) |
| L-08 | Logout via GET | ✅ Fixed |
| L-09 | Weak password policy | ✅ Fixed (blocklist, 72-byte cap, breach check) |
| L-10 | Grader manipulation | ✅ Fixed. Regex misses some phrasings (N-15, informational) |
| L-11 | Default DB credentials | ✅ Fixed (the default, which overrode `.env`, was removed) |
| — | "Safe `next` redirect" (listed as a positive control) | ❌ **Was wrong: bypassable → N-04** |

---

## 3. New findings

| ID | Title | Severity | Confidence | Location |
|---|---|---|---|---|
| N-01 | Pending-password takeover of unverified accounts (regression) | **High** | Confirmed | `app.py` register → verify_email; `database.set/apply_pending_password` |
| N-02 | Ownership check bypass with conflicting `candidate_id` values | **High** | Confirmed | `app.py` `_requested_candidate_id` + `/questions/generate`, `/coding/problems/generate` |
| N-03 | Unauthenticated resume-parser CPU/memory exhaustion | **High** | Confirmed | `/upload`, `extract_text.py`, `parser.py` |
| N-04 | Open redirect after login (`/%09/evil.com`) | Medium | Confirmed | `app.py` `_safe_next` |
| N-05 | Code-runner output unbounded (memory; stored in the DB) | Medium | Confirmed | `runner.py` `capture_output`; submission feedback |
| N-06 | Docker sandbox can't read the code dir on Linux (0700 temp dir vs uid 65532) | Medium | Likely | `runner.py` |
| N-07 | Parallel submissions can occupy all server threads | Medium | Likely | `runner.py`, submit routes |
| N-08 | 16 malformed inputs cause HTTP 500 | Low | Confirmed | guard (`OverflowError`), JSON APIs |
| N-09 | Per-email rate limit skipped when `email` is in the query string | Low | Confirmed | `_rate_limit` vs `request.values` |
| N-10 | Rate-limiter keys never expire; IPv6 rotation | Low | Confirmed | `services/security.py` |
| N-11 | Logout doesn't revoke a copied session cookie | Low | Confirmed | `/logout` |
| N-12 | SMTP timing reveals which emails exist | Low | Likely | forgot/resend routes |
| N-13 | "Account exists" email spam; reset lockout through the hourly code cap | Low | Likely | register, `issue_otp` cap |
| N-14 | TLS not enforced for key=value DSNs or `?host=` URLs; silent SQLite fallback | Low | Likely | `database.py` |
| N-15 | Grader regex misses some phrasings (AI flag and rubric weight still apply) | Info | Confirmed | `evaluator.py` |
| N-16 | Local (opt-in, unsafe) runner: forked children outlive the timeout | Info | Confirmed | `runner.py` local mode |
| N-17 | Model signature check-then-load gap; OTP "locked" message race | Info | Likely | `ml_adapter.py`, `auth.py` |

### N-01: Pending-password takeover of unverified accounts (High, Confirmed)

**Why:** For L-01, re-registering an unverified email now stores the new password as *pending*, and applies it once the code is entered. The pending password isn't tied to the person who chose it. Whoever enters the owner's code applies it, and in practice that is the owner.

**Attack:**

1. The victim signs up (unverified).
2. Within the 60 s cool-down, so no new email goes out, the attacker re-registers the same email with their own password.
3. The victim enters the code from their inbox.
4. The victim's password no longer works (401) and **the attacker's works (302)**.

The pending value also persists, so any unverified account can be primed ahead of time.

**Impact:** takeover of newly created accounts, with the victim locked out.

**Fix:**

- Bind the pending password to the browser that set it: store a random nonce in both the session and the DB row.
- Apply it only when the verifying session presents that nonce.
- Otherwise keep the original password.
- Also clear the pending value on a successful login and on expiry.

### N-02: Ownership check bypass with conflicting `candidate_id` values (High, Confirmed)

**Why:** The access guard checks the *first* `candidate_id` it finds (URL → query → form → JSON), but `/questions/generate` and `/coding/problems/generate` read the JSON body.

**Attack:** `POST /questions/generate?candidate_id=<mine>` with body `{"candidate_id": <victim>}` → 200. The question is stored on the victim's profile. Ids are sequential, so every user is reachable.

**Impact:**

- Writes into other users' practice data; the attacker chooses the victim's next question.
- With AI enabled, the returned question and reason are built from the victim's projects and internships (a resume-content leak).

**Fix:** The guard should collect *every* `candidate_id` in the request and reject a request if they differ or any isn't owned. Handlers should use one validated value (`g.candidate_id`).

### N-03: Unauthenticated resume-parser DoS (High, Confirmed)

**Why:** `/upload` is public and parses in the request thread. The only protection is the 5 MB cap and 20 uploads per hour per IP, but compressed content expands enormously.

**Evidence:**

- A 3.7 KB PDF with one compressed content stream took **65 s and 2.2 GB** (reproduced here).
- The reviewer also measured a 22 KB `.docx` taking 12 s / 176 MB, and a quadratic regex taking 17.7 s on a 20,000-digit line.

**Impact:** a few requests tie up every worker thread and memory. **No login is needed.**

**Fix:**

- Parse in a **child process with a wall-clock timeout (~10 s) and a memory limit**.
- Cap pages (e.g. 10), decompressed size (e.g. 20 MB) and the total `.docx` zip entry size before opening.
- Cap line length before the education regex, and rewrite that regex without the nested repetition.

### N-04: Open redirect (Medium, Confirmed)

`/login?next=/%09/evil.com` → `Location: //evil.com`, because browsers strip the tab. A `next` containing CR/LF causes a 500.

**Fix:** reject control characters and whitespace. Accept only a path whose `urlsplit` has no scheme or host and that doesn't start with `//` or `/\`.

### N-05: Unbounded runner output (Medium, Confirmed)

Code that writes huge amounts to stderr is fully buffered. The app process reached 3.9 GB in 3 s, and 300 MB came back as the result message, which is also stored as submission feedback.

**Fix:** read output through a bounded pipe (e.g. 64 KB, then kill the process), and truncate the stored and returned messages.

### N-06: Docker sandbox permissions on Linux (Medium, Likely)

The code folder is created with mode 0700 and mounted read-only, while the container runs as uid 65532 with all capabilities dropped, so it can't read `solution.py`. Docker Desktop on Windows likely hides this, but a Linux server would fail every run and every AI-problem check.

**Fix:** `chmod 0755` the folder and `0644` the file, or pass the code on stdin.

### N-07: Thread exhaustion (Medium, Likely)

Each submission runs every hidden test in sequence (up to about 5 s each in Docker). Eight parallel infinite-loop submissions occupy all 8 waitress threads for about 25 s or more.

**Fix:** allow one running job per user and set a wall-clock budget per request. Later: a job queue.

### Low and informational (short)

- **N-08:** return 400 instead of 500. Catch `OverflowError`, bound ids to 64-bit, and type-check JSON fields.
- **N-09:** build the rate-limit key from `request.values`, the same field the handler uses.
- **N-10:** drop empty buckets, cap the total number of keys, and treat IPv6 by /64.
- **N-11:** add a per-user session version, increased on logout. Set `PERMANENT_SESSION_LIFETIME`.
- **N-12:** send emails in a background thread so response time doesn't depend on whether the account exists.
- **N-13:** rate-limit the "account exists" email per address. Count the hourly code cap per purpose.
- **N-14:** handle key=value DSNs and `?host=`. Log loudly (or refuse) instead of silently falling back to SQLite when `DATABASE_URL` is set.
- **N-15 to N-17:** informational. N-16 is already opt-in and documented as unsafe.

---

## 4. Checked and fine

- **CSRF:** form, text/plain and multipart posts are rejected without a token. JSON posts can't be sent cross-site (no CORS).
- **Access guard:** URL, form and query conflicts; non-integer and negative ids.
- **Endpoint ownership:** DSA and coding run/submit and practice submit/skip are all owner-bound.
- **Session fingerprint:** 96-bit HMAC, constant-time compare. Change and reset revoke other sessions (tested).
- **OTP:** attempts are atomic, codes are single-use, purpose is bound, and an expired code still spends an attempt.
- **Pending uploads:** 192-bit id, only reachable through the signed cookie, 24 h TTL.
- **Uploads:** random names, signature check, deleted after parsing, 413 handling.
- **`safe_url`:** about 40 bypass payloads tried; output is always `http(s)`.
- **Templates:** no `|safe`; `innerHTML` input is escaped; every script has a nonce; no inline handlers.
- **Runner and generator:** identifiers are validated, test arguments are JSON values, and the Docker kill on timeout is present.
- **Error pages:** generic, with no stack traces.
- **`tools/cleanup.py`:** fixed folders and patterns, symlink-safe.
- **`serve.py`:** refuses to run with `FLASK_DEBUG`.
- **Proxy headers:** ignored unless `PREPWISE_TRUST_PROXY=1`.

## 5. Risk count (new findings)

| Severity | Count |
|---|---|
| High | 3 |
| Medium | 4 |
| Low | 7 |
| Informational | 3 |

## 6. Proposed Phase 4

1. **Now:** N-01 (bind the pending password to the session), N-02 (a guard that validates every id), N-03 (sandboxed parsing with limits), N-04 (strict `next` check).
2. **Next:** N-05 (bounded output), N-06 (sandbox permissions), N-07 (one running job per user), N-08 (400s instead of 500s).
3. **Then:** N-09 to N-14.
4. **Tests:** add a regression test for every item, and re-run the adversarial review once more.

---

## 7. Phase 4 results (fixes applied and re-verified)

The reviewer re-ran every original reproduction script against the fixed code, then reviewed the new code a second time. The second pass found 5 problems in my fixes, all now fixed and tested.

| ID | Fix | Verified by |
|---|---|---|
| N-01 | The pending password only applies in the browser session that set it (nonce); it's dropped on any login with the real password | Reviewer repro: victim keeps their password, attacker's → 401; 3 regression tests |
| N-02 | The guard collects **every** `candidate_id` (URL, repeated query/form values, JSON); any mismatch or non-owned id → 404 | Repro: 404, nothing written to the other user's profile |
| N-03 | Parsing runs in a child process (10 s, 1 GB limit set by the worker itself, including a Windows memory watchdog). One parse per client (IP or IPv6 /64), 4 overall with a short queue. Page, text and `.docx` zip-size caps. The regex is now linear | 3.7 KB PDF bomb stopped, app process at 12 MB; zip bomb refused in 0.1 s; regex 17.7 s → 0.03 s |
| N-04 | `next` must be a same-site path: control characters, whitespace, backslashes, scheme or host → home | `/\t/evil.com` and CR/LF → `/`; no 500 |
| N-05 | Output capped at 64 KB per stream, then the process is killed; messages clipped | App process at 13 MB under an output flood |
| N-06 | Sandbox folder 0755, script 0644 | Test checks permissions (Docker itself untested here) |
| N-07 | One running code job per user (4 overall); Run budget 20 s, Submit 40 s, AI-problem check budget 20 s | 20 infinite hidden tests stop at 40 s; second concurrent job → 429 |
| N-08 | JSON type checks, 64-bit id bounds | Fuzzer: **0 of 16** 500s remain |
| N-09 | Rate-limit key uses the same field as the handler | 429 from the 11th query-string attempt |
| N-10 | LRU-bounded limiter with O(1) eviction that **never drops an active lockout** (refuses new keys instead); IPv6 limited per /64 | 0.0 ms per hit at 100k keys; victim stays blocked after 1,001 junk keys |
| N-11 | Session version in the session identity, increased on logout; 7-day lifetime | Copied cookie → redirect to login after logout |
| N-12 | All sign-up and reset emails are sent in the background | forgot-password time equal with or without an account |
| N-13 | "Account exists" notice limited to 3 per address per day; code cap per purpose; forgot/resend limited per email **and network** | A stranger can no longer get the victim's own request refused (429) |
| N-14 | TLS enforced for key=value DSNs, `?host=` and multi-host; hostnames compared case-insensitively. A **remote** DB that can't be reached stops the app instead of silently switching to SQLite (local dev still falls back) | 8 connection-string forms tested |
| N-15 | Grader flag narrowed to score demands and text addressed to the grader | 9 honest technical answers not flagged; injection examples flagged |
| N-16 | Local runner: own process group, self-applied limits (no `preexec_fn`), pipes closed after a stuck grandchild | Forked child killed; no leaked fds or threads |
| N-17 | Model signature checked on the exact bytes that are then loaded | Swapped file rejected |

**Checks after the fixes:**

- 163 tests pass, including 35 new ones.
- The validation suites pass.
- `bandit`: 0 medium/high issues.
- `pip-audit`: no known vulnerabilities.
- A full browser run-through works.

**Accepted residual risks:**

- Someone who knows your email can still use up that account's hourly reset-code limit (6 per hour). Your own request is no longer refused, but no new code is sent until the hour passes.
- Rate limits and job slots are kept in memory: right for one `serve.py` process, but they would need Redis for several.
- The Docker sandbox and the Windows memory watchdog weren't run on real Docker or real Windows here. Test one DSA submission and one resume upload after restarting.
