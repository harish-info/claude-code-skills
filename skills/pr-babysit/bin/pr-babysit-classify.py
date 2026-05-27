#!/usr/bin/env python3
"""Pure-function classification for CI failures and review comments. No git/network side effects."""
import os
from dataclasses import dataclass


@dataclass
class Decision:
    decision: str           # "fix" or "escalate"
    reason: str = ""


def classify_ci_failure(check_type, failing_file, pr_diff_files,
                        test_file=None, config=None):
    config = config or {}

    if check_type == "detekt":
        if failing_file in pr_diff_files:
            return Decision("fix", "detekt failure on PR-modified file")
        return Decision("escalate", "detekt failed in untouched file")

    if check_type == "paparazzi":
        if not config.get("auto_record", False):
            return Decision("escalate", "paparazzi auto_record disabled in config")
        source_in_diff = failing_file in pr_diff_files
        test_in_diff = test_file is not None and test_file in pr_diff_files
        if source_in_diff or test_in_diff:
            return Decision("fix", "paparazzi failure on PR-modified composable/test")
        return Decision("escalate", "paparazzi failure on untouched UI — regression")

    if check_type == "unit_test":
        if failing_file in pr_diff_files or (test_file and test_file in pr_diff_files):
            return Decision("fix", "test failure on PR-modified file")
        return Decision("escalate", "test failed outside PR scope")

    return Decision("escalate", f"{check_type} not safely auto-fixable")


def classify_comment(comment_body, on_diff_line, config=None,
                     comment_length=None, is_bot=False):
    config = config or {}
    mode = config.get("trigger_mode", "explicit_tag")

    if mode == "explicit_tag":
        if "@pr-babysit" in comment_body:
            return Decision("fix", "explicit tag")
        return Decision("escalate", "no explicit tag (explicit_tag mode)")

    if mode == "narrow_whitelist":
        if not on_diff_line:
            return Decision("escalate", "comment outside PR diff")
        if "?" in comment_body:
            return Decision("escalate", "comment contains '?' — likely question")
        length = comment_length if comment_length is not None else len(comment_body)
        if length >= 200:
            return Decision("escalate", "comment too long (>=200 chars)")
        if is_bot:
            return Decision("escalate", "comment from bot — route to CI handler")
        return Decision("fix", "narrow_whitelist passes preflight checks")

    return Decision("escalate", f"unknown trigger_mode {mode}")


def resolve_module_path(repo_root, failing_file):
    """Walk up from failing_file to nearest dir with build.gradle[.kts]. Returns ':a:b' or None."""
    cur = os.path.normpath(os.path.dirname(os.path.join(repo_root, failing_file)))
    repo_root = os.path.normpath(repo_root)
    while cur.startswith(repo_root) and cur != repo_root:
        if any(os.path.exists(os.path.join(cur, marker))
               for marker in ("build.gradle", "build.gradle.kts")):
            rel = os.path.relpath(cur, repo_root)
            return ":" + rel.replace(os.sep, ":")
        cur = os.path.dirname(cur)
    return None


def file_under_test_name(test_class_name):
    """Strip Test/Tests/Spec/IT suffix. Tests first because endswith('Tests') also endswith('Test')."""
    for suffix in ("Tests", "Test", "Spec", "IT"):
        if test_class_name.endswith(suffix):
            return test_class_name[:-len(suffix)]
    return test_class_name


def substitute_template(command, module=None, flavor=None, test_class=None, test_method=None):
    """Substitute {{module}}, {{flavor}}, {{test_class}}, {{test_method}}.
    Returns None if a referenced variable is missing — caller escalates."""
    subs = {
        "{{module}}": module,
        "{{flavor}}": flavor,
        "{{test_class}}": test_class,
        "{{test_method}}": test_method,
    }
    for placeholder, value in subs.items():
        if placeholder in command:
            if value is None:
                return None
            command = command.replace(placeholder, value)
    return command
