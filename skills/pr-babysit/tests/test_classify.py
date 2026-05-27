"""Tests for pr-babysit-classify.py — pure-function classification for CI failures and comments."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import pr_babysit_classify as c


def test_detekt_in_diff_fixable():
    result = c.classify_ci_failure(
        check_type="detekt",
        failing_file="job/apply/src/main/kotlin/Foo.kt",
        pr_diff_files=["job/apply/src/main/kotlin/Foo.kt"],
    )
    assert result.decision == "fix"


def test_detekt_outside_diff_escalates():
    result = c.classify_ci_failure(
        check_type="detekt",
        failing_file="other/file.kt",
        pr_diff_files=["job/apply/src/main/kotlin/Foo.kt"],
    )
    assert result.decision == "escalate"


def test_paparazzi_default_off_escalates_even_in_diff():
    result = c.classify_ci_failure(
        check_type="paparazzi",
        failing_file="job/apply/src/test/kotlin/FooTest.kt",
        pr_diff_files=["job/apply/src/test/kotlin/FooTest.kt"],
        config={"auto_record": False},
    )
    assert result.decision == "escalate"


def test_paparazzi_auto_record_with_source_in_diff_fixes():
    result = c.classify_ci_failure(
        check_type="paparazzi",
        failing_file="job/apply/src/main/kotlin/FooScreen.kt",
        test_file="job/apply/src/test/kotlin/FooScreenTest.kt",
        pr_diff_files=["job/apply/src/main/kotlin/FooScreen.kt"],
        config={"auto_record": True},
    )
    assert result.decision == "fix"


def test_paparazzi_auto_record_with_only_test_file_in_diff_fixes():
    result = c.classify_ci_failure(
        check_type="paparazzi",
        failing_file="job/apply/src/main/kotlin/FooScreen.kt",
        test_file="job/apply/src/test/kotlin/FooScreenTest.kt",
        pr_diff_files=["job/apply/src/test/kotlin/FooScreenTest.kt"],
        config={"auto_record": True},
    )
    assert result.decision == "fix"


def test_paparazzi_auto_record_neither_in_diff_escalates():
    result = c.classify_ci_failure(
        check_type="paparazzi",
        failing_file="job/apply/src/main/kotlin/FooScreen.kt",
        test_file="job/apply/src/test/kotlin/FooScreenTest.kt",
        pr_diff_files=["other/Bar.kt"],
        config={"auto_record": True},
    )
    assert result.decision == "escalate"


def test_comment_explicit_tag_mode_only_acts_on_tagged():
    result = c.classify_comment(
        comment_body="Please rename foo to bar",
        on_diff_line=True,
        config={"trigger_mode": "explicit_tag"},
    )
    assert result.decision == "escalate"

    result = c.classify_comment(
        comment_body="@pr-babysit rename foo to bar",
        on_diff_line=True,
        config={"trigger_mode": "explicit_tag"},
    )
    assert result.decision == "fix"


def test_comment_narrow_whitelist_rejects_question():
    result = c.classify_comment(
        comment_body="rename foo to bar?",
        on_diff_line=True,
        comment_length=20,
        is_bot=False,
        config={"trigger_mode": "narrow_whitelist"},
    )
    assert result.decision == "escalate"


def test_comment_narrow_whitelist_rejects_long():
    long_body = "rename foo to bar " * 30
    result = c.classify_comment(
        comment_body=long_body,
        on_diff_line=True,
        is_bot=False,
        config={"trigger_mode": "narrow_whitelist"},
    )
    assert result.decision == "escalate"


def test_comment_narrow_whitelist_rejects_out_of_diff():
    result = c.classify_comment(
        comment_body="rename foo to bar",
        on_diff_line=False,
        is_bot=False,
        config={"trigger_mode": "narrow_whitelist"},
    )
    assert result.decision == "escalate"


def test_comment_narrow_whitelist_rejects_bot():
    result = c.classify_comment(
        comment_body="rename foo to bar",
        on_diff_line=True,
        is_bot=True,
        config={"trigger_mode": "narrow_whitelist"},
    )
    assert result.decision == "escalate"


def test_module_path_resolution_traverses_to_build_gradle(tmp_path):
    (tmp_path / "job" / "apply" / "src" / "main" / "kotlin").mkdir(parents=True)
    (tmp_path / "job" / "apply" / "build.gradle.kts").write_text("")
    (tmp_path / "job" / "apply" / "src" / "main" / "kotlin" / "Foo.kt").write_text("")

    module = c.resolve_module_path(
        repo_root=str(tmp_path),
        failing_file="job/apply/src/main/kotlin/Foo.kt",
    )
    assert module == ":job:apply"


def test_module_path_resolution_flat_module(tmp_path):
    (tmp_path / "core" / "src" / "main").mkdir(parents=True)
    (tmp_path / "core" / "build.gradle.kts").write_text("")
    module = c.resolve_module_path(
        repo_root=str(tmp_path),
        failing_file="core/src/main/Utils.kt",
    )
    assert module == ":core"


def test_module_path_resolution_no_marker_returns_none(tmp_path):
    (tmp_path / "loose").mkdir()
    (tmp_path / "loose" / "file.kt").write_text("")
    module = c.resolve_module_path(
        repo_root=str(tmp_path),
        failing_file="loose/file.kt",
    )
    assert module is None


def test_file_under_test_strips_test_suffix():
    assert c.file_under_test_name("JobApplyViewModelTest") == "JobApplyViewModel"
    assert c.file_under_test_name("FooTests") == "Foo"
    assert c.file_under_test_name("BarSpec") == "Bar"
    assert c.file_under_test_name("BazIT") == "Baz"
    assert c.file_under_test_name("NoSuffix") == "NoSuffix"
