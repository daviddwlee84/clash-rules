# clash-rules Agent Contract

- User-facing documentation uses Traditional Chinese; identifiers stay English.
- Keep private nodes, subscriptions, credentials, device profiles and observations below ignored private/ or an explicitly selected external private path, mode 0600. Never print contents or credentials.
- Do not stage, commit, push or create PRs without explicit user instruction. Do not touch .specstory/ without explicit instruction.
- rules/ owns personal policy; vendor/ is byte-preserved upstream data. Update mirrors only through fetch/review/promote; never bypass a lock mismatch or relabel vendor licenses.
- Offline build must remain deterministic. Validate with just check, just test and pinned native fixture; do not claim hardware or Shadowrocket acceptance from host tests.
- AI fixed policy points directly to a concrete leaf node; retain general groups and order. No automatic failover or kill-switch claim.
- Never deploy through ad hoc controller API calls on a managed Pi. Hand reviewed rules to its managed rule-update transaction; follow its strict SSH, controller TLS, snapshot and confirmation contract.
- Use TODO.md as the only future-work index. Run project-knowledge-harness add-todo.sh from this repo; long analysis belongs in backlog/, past debugging in pitfalls/.


<!-- project-knowledge-harness:agent-guidance -->
<!-- Snippet for the project's agent contract file (AGENTS.md / CLAUDE.md /
     similar). The project-knowledge-harness skill's init.sh appends this
     between sentinel markers; safe to re-run. -->

### Long-term backlog → `TODO.md` + `backlog/`

When the user surfaces an idea explicitly **not** being implemented this
session (signals: "maybe later", "nice to have", "if I'm interested",
"工程量太大需要再評估", "先記下來"), add an entry to [`TODO.md`](TODO.md) using
the priority + effort tag schema. Do **not** create new `ROADMAP.md` /
`IDEAS.md` / `BACKLOG.md` files — `TODO.md` is the single index.

> **These helpers (`add-todo.sh`, `sweep-inbox.sh`, `promote-todo.sh`,
> `todo-kanban.sh`) are provided by the `project-knowledge-harness` skill and
> are _not_ copied into this repo.** Invoke them through that skill — it knows
> where its `scripts/` live, and they operate on this repo's `TODO.md` /
> `backlog/`. If the skill isn't available, maintain `TODO.md` by hand using the
> schema below; the format is simple and the validator is optional.

The skill's `todo-kanban.sh` validates the format — run
`todo-kanban.sh --validate-only TODO.md` after editing so syntax drift is
caught immediately.

#### Three ways to add a TODO entry (preferred order)

1. **Structured CLI — `add-todo.sh`** (default):

   ```
   add-todo.sh --priority P3 --effort M \
     --title "Title" --description "Description"
   ```

   Inserts a canonically-formatted line into the right `## P*` lane and
   re-runs the validator. Add `--backlog` to also scaffold
   `backlog/<slug>.md` from the bundled template.

2. **Quick capture — `backlog/inbox.md`** (when priority/effort unclear):

   ```
   echo "- maybe add docs versioning with mike" >> backlog/inbox.md
   ```

   When the user asks "sweep the inbox", run
   `sweep-inbox.sh`. It prompts for the missing fields per loose
   line and calls `add-todo.sh`. Use `--batch` for non-interactive runs
   that only formalize lines with parseable `key=value` pairs.

3. **Direct edit of `TODO.md`** — fine if the format is fresh; run
   `todo-kanban.sh --validate-only` afterwards.

Add a `backlog/<slug>.md` companion doc when the item meets any of:

- carries a `P?` tag (record what was tried so it doesn't need re-investigation)
- captures a paused troubleshooting session that you intend to fix later
  (preserve the error trace + root cause analysis before context evaporates)
- weighs multiple options (record trade-offs, not only the winner)
- is `[L]` or `[XL]` (architectural; needs design before code)

`[S]` items rarely need a backlog doc — a file path in the `TODO.md` line is
usually enough. See [`backlog/README.md`](backlog/README.md) for the full
template and "when to add a doc" rules.

When implementing a `TODO.md` item, in the same commit:

1. Run `promote-todo.sh --title "<substring>" --summary "<what shipped>"`
   to move the entry into `## Done` with the dated syntax and re-validate.
2. Mark the corresponding `backlog/<slug>.md` (if any) `Status: shipped`
   and keep it as a historical record (don't delete — future-you may
   revisit adjacent decisions).

`backlog/` is repo metadata for maintainers, not user-facing config to
deploy.

### Past pitfalls → `pitfalls/`

When you spend more than ~15 minutes debugging something that wasn't
googleable and the fix is non-obvious, write a `pitfalls/<slug>.md`
capturing:

1. **Verbatim symptom** — copy-paste error messages exactly, do not
   paraphrase (preserves grep-ability for future-you / future agent)
2. **Root cause** — why this happens (with source / docs / upstream issue link)
3. **Workaround** — copy-pasteable commands or config diff
4. **Prevention** — how to avoid stepping on this again

Title the doc by the **symptom**, not the root cause (you'll search by what
you're seeing, not by what you eventually learned). See
[`pitfalls/README.md`](pitfalls/README.md) for the full template and
when-to-add rules.

**Pitfall vs Hard invariant**: a pitfall *graduates* to a Hard invariant in
this file when it (a) recurs across machines/agents/sessions despite being
documented, (b) silently corrupts state, or (c) the workaround is non-obvious
enough that "remember to do X" isn't safe. When graduating, leave the
`pitfalls/<slug>.md` as historical record and link to it from the new
invariant.

`pitfalls/` is **not** auto-redacted; review for secrets before
committing.
<!-- project-knowledge-harness:agent-guidance (end) -->
