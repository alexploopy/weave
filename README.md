# weave

**Semantic git merging powered by your Claude chat history.**

`weave` merges two git branches by reasoning about *why* the code on each side
looks the way it does — using each branch's preserved Claude Code conversation —
to resolve conflicts that a plain `git merge` can't. It then carries the combined
reasoning forward, so the next Claude session inherits the full context of both
branches.

---

## The problem

Two developers each work on a separate branch, each with their own Claude Code
session. When the branches merge, the *code* comes together but the
*conversational context* — the intent, the trade-offs, the "why" behind every
decision — is lost. Plain `git merge` only sees text. It has no idea that branch
A renamed a function for a reason branch B's author never knew about.

## The solution

Claude Code already stores every conversation as JSONL at
`~/.claude/projects/<encoded-path>/<uuid>.jsonl`, including rich message types
like `file-history-snapshot` that tie code state to the dialogue that produced
it. `weave` treats that history as a first-class merge input:

1. Distill each branch's chat history into the intent and key decisions behind it.
2. Feed the conflicting code **plus both sides' reasoning** to Cerebras.
3. Produce a semantically-merged result with a rationale for each resolution.
4. Synthesize a combined chat history so the next session inherits the full "why."

Speed is the point: Cerebras reasoning inference resolves merges fast enough to
keep a human in flow.

---

## The pipeline

```
weave merge <A> --onto <B> [--new-branch C]

  ┌─ Resolve ──┐  ┌─ Extract ──┐  ┌─ Diff ───┐  ┌─ Merge ────┐  ┌─ Apply ──┐  ┌─ Fork ────┐
  │ branch →   │  │ JSONL →    │  │ 3-way    │  │ Cerebras   │  │ write    │  │ synthesize│
  │ session    │→ │ ChatContext│→ │ base/A/B │→ │ resolves   │→ │ onto B   │→ │ merged    │
  │ mapping    │  │ (distilled)│  │ conflicts│  │ w/ context │  │ or new C │  │ JSONL     │
  └────────────┘  └────────────┘  └──────────┘  └────────────┘  └──────────┘  └───────────┘
                                                                                     ↓
                                                                          reprompt loop if rejected
```

### Stages

1. **Resolve** — map each branch to its Claude session(s) via a sidecar
   (`.weave/sessions.toml`). `weave track` stamps the current branch ↔ session link.
2. **Extract** — parse both JSONL files into a normalized, **distilled**
   `ChatContext` (user intent, key assistant decisions, `file-history-snapshot`
   deltas) — signal, not 300 raw messages.
3. **Diff** — standard three-way diff (merge-base, A, B). Clean hunks pass through
   untouched; only conflicting regions go to the model.
4. **Merge (Cerebras)** — for each conflict, prompt with both sides' code + each
   side's distilled "why." Returns merged code **plus a one-line rationale** per
   resolution.
5. **Apply** — write the result either in-place onto B or into a new branch C.
   **Always shows a reviewable diff; never auto-commits silently.**
6. **Fork** — emit a new merged JSONL chat object fusing both histories + the
   merge rationales, so the next Claude session inherits combined context.
7. **Reprompt loop** — reject a resolution → re-run with feedback; the prior
   attempt + feedback go back to Cerebras.

---

## CLI

| Command | Purpose |
|---------|---------|
| `weave merge <A> --onto <B> [--new-branch <C>] [--dry-run]` | The hero command. |
| `weave track` | Record the current branch ↔ session link. |
| `weave show <branch>` | Preview the distilled context for a branch. |
| `weave edit <session>` | CRUD on JSONL chat objects *(stretch / post-hackathon)*. |

`merge A --onto B` writes either in-place onto B, or — with `--new-branch C` —
into a fresh branch. The combined chat history travels either way.

---

## Architecture

Each module has one clear purpose and is independently testable.

| Module | Responsibility | Depends on |
|--------|---------------|------------|
| `cli` | arg parsing, orchestration, diff display | all |
| `jsonl` | parse/normalize Claude JSONL → `ChatContext` | — |
| `gitops` | branch refs, 3-way diff, apply, new-branch | `git` |
| `context` | distill `ChatContext`; synthesize merged history | `jsonl` |
| `merge` | Cerebras client, prompt building, response parsing | `context`, `gitops` |

### Error handling — *never corrupt, always reviewable*

- Model returns unparseable output → fall back to standard conflict markers for
  that hunk; don't fail the whole merge.
- A branch has no chat history → degrade to a code-only merge, warn the user.
- Cerebras unreachable / no API key → clear error, exit **before** touching the repo.

---

## Testing & demo strategy

**Hybrid: real pipeline, controlled input.** The plumbing is genuinely
end-to-end — real JSONL, real branches, real Cerebras — but the demo runs on a
seeded fixture so the live result is deterministic.

- **Fixture repo** committed in-tree: two branches touching the same code in a
  way `git merge` botches, each with a seeded JSONL history. This *is* the demo.
- **Unit:** golden tests on `jsonl` distillation and `gitops` diff; `merge`
  tested against a **mocked** Cerebras response.
- **Integration:** one real-Cerebras test gated behind the API key env var.

---

## Configuration

| Variable | Purpose |
|----------|---------|
| `CEREBRAS_API_KEY` | Auth for Cerebras inference (OpenAI-compatible API). |

---

## Status

Proof of concept — hackathon build. Implemented in Rust.
