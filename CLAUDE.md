# CLAUDE.md

This repo is run by the software factory. Tobi (`Tobias-Braun`) files issues; agents clarify,
specify, implement and review them.

- Read `spec/README.md` first and load only the spec files you need.
- Flow is always issue → spec → code. Never invent spec content.
- Work for issue `n` happens on branch `factory/issue-<n>`, in one PR that closes the issue.
- Never create issues, never push to `main`, never edit `.claude/`, `.devcontainer/` or `factory.conf`.
- Use `.claude/tools/` for GitHub: they add the `<agent-name>@factory.tobi-braun.com` prefix line
  every comment needs, edit your in-place comments and set state labels.
- Only label and comment on issues; never edit their title or body, never close them.
- Keep changes minimal: low code volume, clear names, short comments only where they add value.
- When stuck, comment why and what would unblock you, then stop.
