"""Chat-mode <remember> memory-write directive (ported local patch).

Covers the streaming filter that strips ``<remember>...</remember>`` spans from
a local model's reply, and the owner-scoped persistence helper. The filter must
survive deltas split at arbitrary boundaries (including char-by-char), never
leak the tag, capture unclosed directives, and leave Obsidian ``[[wikilinks]]``
untouched.
"""
from routes.chat_helpers import MemoryDirectiveFilter, persist_directive_memories


def _run(deltas):
    """Feed deltas in order; return (visible_text, captured_facts)."""
    f = MemoryDirectiveFilter()
    visible = "".join(f.feed(d) for d in deltas)
    visible += f.flush()
    return visible, f.captured


# ── streaming filter ──────────────────────────────────────────────────── #

def test_strips_single_directive_whole():
    vis, cap = _run(["Hello! <remember>user likes tea</remember>"])
    assert vis == "Hello! "
    assert cap == ["user likes tea"]


def test_directive_split_across_deltas():
    vis, cap = _run(["Hi <re", "member>fact ", "one</rem", "ember> bye"])
    assert "<remember>" not in vis and "</remember>" not in vis
    assert vis == "Hi  bye"
    assert cap == ["fact one"]


def test_char_by_char():
    text = "ab<remember>xyz</remember>cd"
    vis, cap = _run(list(text))
    assert vis == "abcd"
    assert cap == ["xyz"]


def test_unclosed_directive_captured_not_leaked():
    vis, cap = _run(["answer <remember>partial fact no close"])
    assert "<remember>" not in vis
    assert vis == "answer "
    assert cap == ["partial fact no close"]


def test_wikilink_passthrough():
    # A [[wikilink]] must never be mistaken for a directive.
    vis, cap = _run(["see [[My Note]] and ", "[[Another]]"])
    assert vis == "see [[My Note]] and [[Another]]"
    assert cap == []


def test_multiple_directives():
    vis, cap = _run(["a<remember>one</remember>b<remember>two</remember>c"])
    assert vis == "abc"
    assert cap == ["one", "two"]


def test_partial_open_tag_at_end_is_flushed_verbatim():
    # A trailing fragment that merely starts like <remember> but never becomes
    # the tag must be emitted on flush, not swallowed.
    vis, cap = _run(["all done <rem"])
    assert vis == "all done <rem"
    assert cap == []


# ── owner-scoped persistence ──────────────────────────────────────────── #

class _FakeMemoryManager:
    def __init__(self):
        self.store = []
        self._id = 0

    def load_all(self):
        return list(self.store)

    def find_duplicates(self, text, entries=None):
        pool = entries if entries is not None else self.store
        return [m for m in pool if m.get("text") == text]

    def add_entry(self, text, source="user", category="fact", owner=None):
        self._id += 1
        return {"id": self._id, "text": text, "source": source,
                "category": category, "owner": owner}

    def save(self, entries):
        self.store = list(entries)


def test_persist_saves_owner_scoped():
    mm = _FakeMemoryManager()
    saved = persist_directive_memories(mm, None, ["fact A", "fact B"], owner="alice")
    assert saved == ["fact A", "fact B"]
    assert {m["text"] for m in mm.store} == {"fact A", "fact B"}
    assert all(m["owner"] == "alice" for m in mm.store)
    assert all(m["source"] == "assistant" for m in mm.store)


def test_persist_dedups_within_owner():
    mm = _FakeMemoryManager()
    mm.store = [{"id": 99, "text": "fact A", "owner": "alice"}]
    saved = persist_directive_memories(mm, None, ["fact A", "new fact"], owner="alice")
    assert saved == ["new fact"]  # "fact A" already present for alice
    assert len(mm.store) == 2


def test_persist_does_not_dedup_across_owners():
    # bob saving "fact A" must not be blocked by alice already having it.
    mm = _FakeMemoryManager()
    mm.store = [{"id": 99, "text": "fact A", "owner": "alice"}]
    saved = persist_directive_memories(mm, None, ["fact A"], owner="bob")
    assert saved == ["fact A"]
    assert len(mm.store) == 2


def test_persist_empty_is_noop():
    mm = _FakeMemoryManager()
    saved = persist_directive_memories(mm, None, [], owner="alice")
    assert saved == []
    assert mm.store == []
