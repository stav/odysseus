# Port notes — `<remember>` memory-write directive

**Branch:** `local`, based on `origin/dev` @ `85297cee`.
**Ported 2026-06-16, re-ported 2026-08-19** onto a force-updated `origin/dev`.

Carries the one local patch upstream still lacks: a Chat-mode write path so **local models can save
memory**. Everything else from the original memory-rag work has either been fixed upstream or moved
out of version control — see *What was dropped*.

## What this commit contains (3 files + 1 test)

1. **`routes/chat_helpers.py`** — `MemoryDirectiveFilter` (streaming `<remember>…</remember>`
   stripper that holds back partial tags across deltas) and `persist_directive_memories()`
   (owner-scoped save + dedup + vector sync + `memory_added` event). Injects the `<remember>`
   write-directive system prompt when `mem_enabled and not agent_mode and not incognito`.

2. **`routes/chat_routes.py`** — chat-mode stream loop only: instantiates `_mem_filter`, routes
   visible deltas through it, and at `[DONE]` flushes the tail, persists captured facts, and appends
   the `🧠 Saved to memory` confirmation. Agent/rewrite loops untouched.

3. **`src/chat_handler.py`** — owner-scoped `remember:` fix. The ownerless-save bug still exists in
   dev: `handle_memory_command` used `load()`/`add_entry()` without an owner, orphaning entries out
   of the brain panel.

4. **`tests/test_memory_directive.py`** — **11 tests**: filter split / char-by-char / unclosed /
   wikilink-passthrough / multi-tag, and persist owner-scoping / dedup / cross-owner / empty.
   *(The June notes said 12; the file has always had 11.)*

## What was dropped on 2026-08-19, and why

- 🔥 **Vault RAG force-on — dropped, superseded by a real UI toggle.** The June patch set
  `use_rag_val = True` unconditionally because the UI hid the control and sent `use_rag=false` on
  every message. Upstream has since added a genuine toggle: an overflow button plus an indicator
  (`static/app.js:2483-2495`), whose state persists via `saveToggleState` and is restored at boot
  (`static/app.js:2050-2051`).

  ⚠️ **It still defaults OFF.** `static/index.html:1032` declares `<input id="rag-toggle"
  style="display:none">` with no `checked`, and `static/js/chat.js:1918-1920` sends `use_rag=false`
  whenever it is unchecked — so out of the box the vault is *not* searched. This is **not** "fixed
  upstream"; it is "now user-controllable".

  Dropped anyway, deliberately: forcing it on would override a control the user is now entitled to
  turn off, and would fight upstream's newer `casual_low_signal` suppression.
  **Both conflicts in `chat_helpers.py` resolved to HEAD.**

  ➡️ **Consequence: after rebuilding, enable RAG once in the overflow menu.** It persists across
  reloads. Skip this and vault retrieval silently returns nothing — the same failure mode as a
  wrong owner tag.

- **The `docker-compose.yml` vault mount — moved, not deleted.** It now lives in
  `docker-compose.override.yml`, which is gitignored, so a machine-specific path can never be
  committed and can never be lost to a rebase. The hard-coded `/home/stav/Obsidian` caveat in the
  June notes no longer applies to this commit.

## Conflicts resolved this time (both in `chat_routes.py`, both needing *both* sides)

- **Stream loop.** Upstream added `thinking_response` accumulation for reasoning tokens, which the
  June patch predates. Merged: thinking deltas accumulate and yield as before; visible deltas route
  through `_mem_filter`.
- **`[DONE]` handler.** Upstream added a `_chat_terminal_saved` early-`continue` for providers that
  append DONE after a terminal error. **The guard must run before the flush/persist** — otherwise a
  failed stream would save memories from a partial reply. Guard first, then the patch block.

`chat_routes.py`, `chat_handler.py` and `docker-compose.yml` had **zero** upstream commits touching
them since the June base; only `chat_helpers.py` had churn (2 commits).

## Why it keeps porting cleanly

dev's memory API is unchanged (`load_all`, `load(owner=)`, `add_entry(text, source=, category=,
owner=)`, `find_duplicates`, `save`), `event_bus.fire_event("memory_added", owner)` is dev's own
pattern, and the chat-mode stream structure still matches. This is a re-apply, not a rewrite.

## Verification

- `python -m py_compile` on all three changed files — clean.
- **11/11 directive tests pass** against this resolution, run in the container image with the
  working tree mounted.
- ⚠️ **NOT done: live end-to-end.** A real local model emitting `<remember>` and the fact landing in
  the brain panel has not been re-verified since the re-port. That is the one manual step.

## Manual cutover

The running container serves the *image*, not the working tree, so these changes are not live until
rebuilt:

```bash
cd ~/Work/Odyssyus/odysseus
docker compose build odysseus && docker compose up -d odysseus
```

Then **turn RAG on once** in the overflow menu — it defaults off and persists once set, and
without it the vault is not searched at all.

Then in **Chat mode** tell a local model a durable fact and confirm three things: the `<remember>`
tag is hidden, `🧠 Saved to memory` appears, and the fact shows in the brain panel and recalls in a
new chat.

## Caveats

- `persist_directive_memories` calls `memory_vector.add(id, text)` guarded by
  `getattr(memory_vector, "healthy", False)` + try/except — if dev's vector API drifts, the fact
  still saves, just unindexed. Worth eyeballing during the live test.
- **This patch is the reason to keep a fork.** It is not upstreamed; every `git fetch` + rebase
  re-applies it. If upstream ever ships a Chat-mode memory-write path, delete this commit rather
  than merging around it.
