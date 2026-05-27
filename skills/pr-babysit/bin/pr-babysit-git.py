#!/usr/bin/env python3
"""Git operations for scope checking, head-change detection, and workspace sync."""
import fnmatch
import os
import subprocess


def _git(repo, *args, capture=True, check=True):
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                          capture_output=capture, text=True, check=check)


def scope_check(repo_root, pre_fix_sha, pr_diff_files, generated_paths):
    """Verify changes since pre_fix_sha only touch (pr_diff_files + generated_paths)."""
    touched = _git(repo_root, "diff", "--name-only", f"{pre_fix_sha}..HEAD"
                   ).stdout.strip().splitlines()
    allowed = set(pr_diff_files)
    off_scope = [f for f in touched
                 if f not in allowed
                 and not any(fnmatch.fnmatch(f, pattern) for pattern in generated_paths)]
    return len(off_scope) == 0, off_scope


def is_merge_commit(repo_root, ref):
    """True iff ref has two or more parents."""
    parents = _git(repo_root, "rev-list", "--parents", "-n", "1", ref).stdout.split()[1:]
    return len(parents) >= 2


def merge_scope_check(repo_root, pre_fix_sha, pr_diff_files, safe_paths,
                      base_branch, resolved_files):
    """Merge-commit-specific scope check.
    (a) resolved_files must match safe_paths globs.
    (b) other touched files NOT in pr_diff_files must equal origin/<base> tip.
    """
    touched = set(_git(repo_root, "diff", "--name-only",
                       f"{pre_fix_sha}..HEAD").stdout.strip().splitlines())

    bad_resolved = [f for f in resolved_files
                    if not any(fnmatch.fnmatch(f, pattern) for pattern in safe_paths)]
    if bad_resolved:
        return False, bad_resolved

    non_resolved_external = touched - set(resolved_files) - set(pr_diff_files)
    smuggled = []
    for f in non_resolved_external:
        diff = _git(repo_root, "diff", f"origin/{base_branch}", "HEAD", "--", f,
                    check=False).stdout
        if diff.strip():
            smuggled.append(f)
    return len(smuggled) == 0, smuggled


def detect_head_change(repo_root, prev_sha, current_sha):
    """Detect head change type: 'fast_forward', 'rewrite', or None (equal)."""
    if prev_sha == current_sha:
        return None
    result = _git(repo_root, "merge-base", "--is-ancestor", prev_sha, current_sha,
                  check=False)
    return "fast_forward" if result.returncode == 0 else "rewrite"


def sync_workspace(repo_root, head_remote, head_branch):
    """Sync workspace: git fetch + git reset --hard to remote/branch."""
    _git(repo_root, "fetch", head_remote, head_branch)
    _git(repo_root, "reset", "--hard", f"{head_remote}/{head_branch}")


def get_resolved_conflict_files(repo_root):
    """List files with conflicts during a merge in progress."""
    return _git(repo_root, "diff", "--name-only", "--diff-filter=U"
                ).stdout.strip().splitlines()
