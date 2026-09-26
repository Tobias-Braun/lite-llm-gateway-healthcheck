#!/usr/bin/env bash
# PreToolUse guard for factory agents, the second line of defence behind the permission rules.
#
# Permission rules only match command prefixes, so variants slip through: other flag orders,
# refspecs like HEAD:main, `gh api` instead of `gh issue create`, or a shell redirect into a
# protected file. This hook inspects every tool call and blocks the factory's forbidden actions:
#   - creating issues (gh issue create/transfer, REST or GraphQL via gh api or curl, GitHub MCP)
#   - editing the title or body of an issue, or closing, reopening or deleting it
#   - merging PRs (gh pr merge, the REST merge endpoint, GraphQL merge/auto-merge, GitHub MCP)
#   - pushing to main, pushing all branches, and force-pushing
#   - changing .claude/, .devcontainer/ or factory.conf (edit tools and common shell writes)
#   - writing commit statuses or check runs directly; the review agent sets `factory/review`
#     through .claude/tools/set-review.sh, which no other agent may run
#   - for the review agent (FACTORY_AGENT=review-agent): editing files outside /tmp, committing
#     and pushing, since the reviewer never changes the code it reviews
# It is a heuristic, not a shell parser. Branch protection stays the real barrier for main.
#
# Exit code 2 blocks the call and shows the reason to the agent. If the tool call can't be parsed,
# the guard also blocks, so it fails closed. Written for bash 3.2 (macOS) as well as newer bash.

block() {
  echo "Blocked by factory guard: $1" >&2
  exit 2
}

PROTECTED_MSG="agents never change .claude/, .devcontainer/ or factory.conf"
# Set by the dispatcher for the whole run; the agent can't change the hook's environment.
AGENT="${FACTORY_AGENT:-}"

input="$(cat)"
tool="$(jq -r '.tool_name // empty' <<<"$input" 2>/dev/null)" || block "could not parse the tool call"
project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"

# Matches any .claude or .devcontainer directory and any factory.conf, wherever the path points,
# so relative, absolute and ../ paths are all caught.
is_protected() {
  [[ "$1" =~ (^|/)\.claude(/|$) || "$1" =~ (^|/)\.devcontainer(/|$) || "$1" =~ (^|/)factory\.conf$ ]]
}

check_push() {
  local positional=() arg skip=0
  for arg in "$@"; do
    if ((skip)); then skip=0; continue; fi
    case "$arg" in
      --force | --force=* | --force-with-lease* | --force-if-includes) block "force-push is not allowed" ;;
      --all | --mirror) block "pushing all branches is not allowed" ;;
      -o | --push-option | --repo | --receive-pack | --exec) skip=1 ;;
      --*) ;;
      -*f*) block "force-push is not allowed" ;;
      -*) ;;
      *) positional+=("$arg") ;;
    esac
  done

  # positional[0] is the remote; everything after it is a refspec.
  local branch spec dst
  branch="$(git -C "$project_dir" branch --show-current 2>/dev/null)"
  if ((${#positional[@]} <= 1)); then
    [[ "$branch" == main ]] && block "pushing from main is not allowed; work on a feature branch"
    return 0
  fi
  for spec in "${positional[@]:1}"; do
    [[ "$spec" == +* ]] && block "force-push (+refspec) is not allowed"
    # Without a colon the destination has the source's name; HEAD means the current branch.
    dst="${spec#*:}"
    [[ "$dst" == HEAD ]] && dst="$branch"
    dst="${dst#refs/heads/}"
    [[ "$dst" == main ]] && block "pushing to main is not allowed; open a PR instead"
  done
  return 0
}

check_git() {
  local i=0 args=("$@")
  # Skip global options to reach the subcommand; -C and -c take a separate value.
  while ((i < ${#args[@]})) && [[ "${args[i]}" == -* ]]; do
    [[ "${args[i]}" == -C || "${args[i]}" == -c ]] && i=$((i + 1))
    i=$((i + 1))
  done
  local sub="${args[i]}"
  [[ "$AGENT" == review-agent && "$sub" =~ ^(commit|push|merge|rebase|cherry-pick|revert|am|tag)$ ]] &&
    block "the review agent never changes the code it reviews"
  case "$sub" in
    push) check_push "${args[@]:i+1}" ;;
    rm | mv | restore | checkout) check_write "$sub" "${args[@]:i+1}" ;;
  esac
}

# Covers gh api, curl and similar: creating an issue is a write to .../issues (gh api turns into a
# POST as soon as fields are passed), editing or closing one is a write to .../issues/<n> (labels
# and comments live below it and stay allowed), merging is anything on .../pulls/<n>/merge.
check_http() {
  local joined=" $* " write=0
  [[ "$joined" =~ /pulls/[0-9]+/merge[[:space:]?] ]] && block "only Tobi merges PRs"
  [[ "$joined" =~ [[:space:]](-X|--method|--request)[[:space:]=]*GET ]] && return 0
  if [[ "$joined" =~ [[:space:]](-X|--method|--request)[[:space:]=]*(POST|PATCH|PUT|DELETE) ]] ||
    [[ "$joined" =~ [[:space:]](-f|-F|--field|--raw-field|--input|-d|--data|--data-raw|--json)[[:space:]=] ]]; then
    write=1
  fi
  ((write)) || return 0
  [[ "$joined" =~ repos/[^/[:space:]]+/[^/[:space:]]+/issues[[:space:]?] ]] && block "agents never create issues"
  [[ "$joined" =~ repos/[^/[:space:]]+/[^/[:space:]]+/issues/[0-9]+[[:space:]?] ]] &&
    block "agents only label and comment on issues, never edit or close them"
  [[ "$joined" =~ repos/[^/[:space:]]+/[^/[:space:]]+/(statuses|check-runs)([/[:space:]?]) ]] &&
    block "commit statuses come only from the review agent, through .claude/tools/set-review.sh"
  return 0
}

check_gh() {
  local a
  case "$1 $2" in
    "issue create" | "issue new" | "issue transfer") block "agents never create issues" ;;
    "issue close" | "issue reopen" | "issue delete" | "issue lock" | "issue unlock" | "issue pin" | "issue unpin")
      block "agents only label and comment on issues, never edit or close them" ;;
    "issue edit")
      # Labels are the agents' part of an issue; title and body are Tobi's.
      for a in "${@:3}"; do
        case "$a" in
          -t | -b | -F | --title | --title=* | --body | --body=* | --body-file | --body-file=* | -t* | -b* | -F*)
            block "agents only label and comment on issues, never edit or close them" ;;
        esac
      done ;;
    "pr merge") block "only Tobi merges PRs" ;;
  esac
  [[ "$1" == api ]] && check_http "$@"
  return 0
}

# Blocks shell commands that write into a protected path. cp/mv/install/rsync only write to their
# last argument, so reading from .claude/ (cp .claude/x /tmp) stays allowed.
check_write() {
  local cmd="$1" a
  shift
  case "$cmd" in
    rm | rmdir | unlink | touch | chmod | chown | truncate | tee | ln | mkdir | restore | checkout)
      for a in "$@"; do is_protected "$a" && block "$PROTECTED_MSG"; done ;;
    cp | mv | install | rsync)
      (($#)) && is_protected "${@: -1}" && block "$PROTECTED_MSG" ;;
    sed | perl)
      for a in "$@"; do
        if [[ "$a" == -*i* || "$a" == --in-place* ]]; then
          for a in "$@"; do is_protected "$a" && block "$PROTECTED_MSG"; done
          break
        fi
      done ;;
  esac
  return 0
}

# Redirects: `> file`, `>>file`, `x>file`, `2> file`. The target is the text after the last `>`,
# or the next word if nothing follows it.
check_redirects() {
  local words=("$@") i target
  for ((i = 0; i < ${#words[@]}; i++)); do
    [[ "${words[i]}" == *">"* ]] || continue
    target="${words[i]##*>}"
    [[ -z "$target" ]] && target="${words[i + 1]}"
    is_protected "$target" && block "$PROTECTED_MSG"
  done
  return 0
}

check_segment() {
  local words=()
  # Quotes are dropped before splitting into words; good enough for the patterns checked here.
  read -ra words <<<"$(tr -d "\"'" <<<"$1")"
  # Skip env assignments and wrappers so `FOO=1 bin/bot.sh gh issue create` is still seen as gh.
  while ((${#words[@]})); do
    case "${words[0]}" in
      *=* | env | command | exec | nohup | time | sudo | xargs | bot.sh | */bot.sh) words=("${words[@]:1}") ;;
      *) break ;;
    esac
  done
  ((${#words[@]})) || return 0

  check_redirects "${words[@]}"
  local cmd="${words[0]##*/}"
  [[ "$cmd" == set-review.sh && "$AGENT" != review-agent ]] && block "only the review agent sets factory/review"
  case "$cmd" in
    git) check_git "${words[@]:1}" ;;
    gh) check_gh "${words[@]:1}" ;;
    curl | wget | http | https) check_http "${words[@]:1}" ;;
    sh | bash | zsh | eval)
      local inner="${words[*]:1}"
      check_command "${inner#-c }" ;;
    *) check_write "$cmd" "${words[@]:1}" ;;
  esac
  return 0
}

# Splits a command line into simple commands at ; | & ( ) ` and newlines, then checks each one.
check_command() {
  local segment
  while IFS= read -r segment; do
    check_segment "$segment"
  done < <(awk '{ gsub(/[;|&()`]/, "\n"); print }' <<<"$1")
  return 0
}

case "$tool" in
  Edit | Write | MultiEdit | NotebookEdit)
    path="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$input")"
    is_protected "$path" && block "$PROTECTED_MSG"
    # The reviewer's notes (e.g. the findings for set-review.sh) go to /tmp, never into the repo.
    [[ "$AGENT" == review-agent && ("$path" != /tmp/* || "$path" == *..* || "$path" == "$project_dir"/*) ]] &&
      block "the review agent never edits files; write notes to /tmp" ;;
  Bash)
    command="$(jq -r '.tool_input.command // empty' <<<"$input")"
    # GraphQL mutations usually sit inside a quoted multi-line query, so check the raw text.
    if [[ "$command" == *graphql* ]]; then
      [[ "$command" == *createIssue* ]] && block "agents never create issues"
      [[ "$command" == *updateIssue\(* || "$command" == *closeIssue* || "$command" == *deleteIssue* ]] &&
        block "agents only label and comment on issues, never edit or close them"
      [[ "$command" == *mergePullRequest* || "$command" == *enablePullRequestAutoMerge* ]] && block "only Tobi merges PRs"
    fi
    check_command "$command" ;;
  mcp__*)
    case "$tool" in
      *create_issue* | *merge_pull_request*) block "agents never create issues or merge PRs" ;;
      *issue_write*)
        [[ "$(jq -r '.tool_input.method // empty' <<<"$input")" == create ]] && block "agents never create issues"
        jq -e '.tool_input | has("title") or has("body") or has("state")' <<<"$input" >/dev/null &&
          block "agents only label and comment on issues, never edit or close them" ;;
      *push_files* | *create_or_update_file* | *delete_file*)
        [[ "$(jq -r '.tool_input.branch // empty' <<<"$input")" == main ]] && block "pushing to main is not allowed" ;;
    esac ;;
esac
exit 0
