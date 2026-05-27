"""Scope check, merge-commit check, and head-change detection tests using a real temp git repo."""
import os
import subprocess
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import pr_babysit_git as g


def _run(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def temp_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "git", "init", "-q", "-b", "main")
    _run(repo, "git", "config", "user.email", "test@test")
    _run(repo, "git", "config", "user.name", "Test")
    _run(repo, "git", "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("a\n")
    _run(repo, "git", "add", "a.txt")
    _run(repo, "git", "commit", "-qm", "init")
    return repo


def test_scope_check_passes_when_only_pr_files_touched(temp_repo):
    pre_fix_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_repo,
                                 capture_output=True, text=True).stdout.strip()
    (temp_repo / "a.txt").write_text("a\nfix\n")
    _run(temp_repo, "git", "add", "a.txt")
    _run(temp_repo, "git", "commit", "-qm", "fix")
    ok, off_scope = g.scope_check(temp_repo, pre_fix_sha=pre_fix_sha,
                                  pr_diff_files=["a.txt"],
                                  generated_paths=[])
    assert ok is True
    assert off_scope == []


def test_scope_check_fails_when_out_of_scope_file_touched(temp_repo):
    pre_fix_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_repo,
                                 capture_output=True, text=True).stdout.strip()
    (temp_repo / "b.txt").write_text("b\n")
    _run(temp_repo, "git", "add", "b.txt")
    _run(temp_repo, "git", "commit", "-qm", "fix")
    ok, off_scope = g.scope_check(temp_repo, pre_fix_sha=pre_fix_sha,
                                  pr_diff_files=["a.txt"],
                                  generated_paths=[])
    assert ok is False
    assert "b.txt" in off_scope


def test_scope_check_allows_generated_paths(temp_repo):
    pre_fix_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_repo,
                                 capture_output=True, text=True).stdout.strip()
    (temp_repo / "build").mkdir()
    (temp_repo / "build" / "x.txt").write_text("generated\n")
    _run(temp_repo, "git", "add", "build/x.txt")
    _run(temp_repo, "git", "commit", "-qm", "fix")
    ok, off_scope = g.scope_check(temp_repo, pre_fix_sha=pre_fix_sha,
                                  pr_diff_files=[],
                                  generated_paths=["build/**", "build/*"])
    assert ok is True


def test_is_merge_commit_true_for_merge(temp_repo):
    _run(temp_repo, "git", "checkout", "-qb", "feature")
    (temp_repo / "f.txt").write_text("f\n")
    _run(temp_repo, "git", "add", "f.txt")
    _run(temp_repo, "git", "commit", "-qm", "feat")
    _run(temp_repo, "git", "checkout", "-q", "main")
    (temp_repo / "m.txt").write_text("m\n")
    _run(temp_repo, "git", "add", "m.txt")
    _run(temp_repo, "git", "commit", "-qm", "main")
    _run(temp_repo, "git", "merge", "feature", "--no-ff", "-qm", "merge")
    assert g.is_merge_commit(temp_repo, "HEAD") is True


def test_is_merge_commit_false_for_single_parent(temp_repo):
    assert g.is_merge_commit(temp_repo, "HEAD") is False


def test_head_change_detection_fast_forward(temp_repo):
    old_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_repo,
                             capture_output=True, text=True).stdout.strip()
    (temp_repo / "c.txt").write_text("c\n")
    _run(temp_repo, "git", "add", "c.txt")
    _run(temp_repo, "git", "commit", "-qm", "advance")
    new_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_repo,
                             capture_output=True, text=True).stdout.strip()
    kind = g.detect_head_change(temp_repo, prev_sha=old_sha, current_sha=new_sha)
    assert kind == "fast_forward"


def test_head_change_detection_rewrite(temp_repo):
    old_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_repo,
                             capture_output=True, text=True).stdout.strip()
    _run(temp_repo, "git", "checkout", "--orphan", "rebase-result")
    _run(temp_repo, "git", "rm", "-rf", ".")
    (temp_repo / "y.txt").write_text("y\n")
    _run(temp_repo, "git", "add", "y.txt")
    _run(temp_repo, "git", "commit", "-qm", "rebased")
    new_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_repo,
                             capture_output=True, text=True).stdout.strip()
    kind = g.detect_head_change(temp_repo, prev_sha=old_sha, current_sha=new_sha)
    assert kind == "rewrite"


def test_merge_scope_check_accepts_pr_file_in_diff(temp_repo):
    """Merge-commit check: PR files that auto-merged cleanly are NOT escalated."""
    _run(temp_repo, "git", "remote", "add", "origin", str(temp_repo))
    _run(temp_repo, "git", "fetch", "origin", "main")
    _run(temp_repo, "git", "checkout", "-qb", "pr")
    (temp_repo / "a.txt").write_text("a\npr-edit\n")
    _run(temp_repo, "git", "add", "a.txt")
    _run(temp_repo, "git", "commit", "-qm", "pr edit a")
    _run(temp_repo, "git", "checkout", "-q", "main")
    (temp_repo / "base.txt").write_text("base\n")
    _run(temp_repo, "git", "add", "base.txt")
    _run(temp_repo, "git", "commit", "-qm", "base unrelated")
    _run(temp_repo, "git", "fetch", "origin", "main")
    _run(temp_repo, "git", "checkout", "-q", "pr")
    pre_fix_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_repo,
                                 capture_output=True, text=True).stdout.strip()
    _run(temp_repo, "git", "merge", "main", "--no-ff", "-qm", "merge base")
    ok, off_scope = g.merge_scope_check(
        temp_repo,
        pre_fix_sha=pre_fix_sha,
        pr_diff_files=["a.txt"],
        safe_paths=[],
        base_branch="main",
        resolved_files=[],
    )
    assert ok is True, f"merge scope check should pass; got off_scope={off_scope}"
