"""Small local tests: shell behavior with stubbed downloads, and exception scope.

No network, installs, real user folders or iOS apps are used by these tests.
"""
import copy
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import failure_diagnostics as D
import test_input as I

ROOT = Path(__file__).resolve().parents[1]
BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = plistlib.loads((ROOT / "tests/fixtures/good-1.7.plist").read_bytes())["WFWorkflowActions"]
        cls.cur = plistlib.loads((ROOT / "shortcut/fed.unsigned.plist").read_bytes())["WFWorkflowActions"]
        cls.lock = json.loads((ROOT / "tests/locked-platforms.json").read_text())

    def test_only_four_authorized_fields_changed_outside_new_blocks(self):
        before, after = I.stamp_free(self.good), I.stamp_free(self.cur)
        # The Threads tail block is an addition, not a lock exception: drop the
        # named FMD+ / FMD- blocks that are new since the confirmed baseline and
        # the remainder must line up action for action.
        new_blocks = {n: ix for n, ix in I.blocks(after).items() if n not in I.blocks(before)}
        new_idx = set().union(*new_blocks.values()) if new_blocks else set()
        rest = [a for i, a in enumerate(after) if i not in new_idx]
        self.assertEqual(sorted(new_blocks), ["Threads server-failed posts"])
        self.assertEqual(len(rest), len(before))
        expected = D.expected_changes(self.good)
        changed = set()
        for base, current in zip(before, rest):
            self.assertEqual(base["WFWorkflowActionIdentifier"], current["WFWorkflowActionIdentifier"])
            bp, cp = base["WFWorkflowActionParameters"], current["WFWorkflowActionParameters"]
            for field in set(bp) | set(cp):
                if bp.get(field) != cp.get(field):
                    uuid = cp.get("UUID")
                    self.assertEqual(D.FIELDS.get(uuid), field)
                    self.assertEqual(cp[field], expected[uuid])
                    changed.add(uuid)
        self.assertEqual(changed, set(D.FIELDS))

    def test_x_and_instagram_steps_are_identical_without_exception_normalization(self):
        before, after = I.stamp_free(self.good), I.stamp_free(self.cur)
        for platform in ("X", "Instagram"):
            for link in self.lock["locked"][platform]["links"]:
                for outcome, sections in I.OUTCOMES:
                    self.assertEqual(I.as_steps(before, I.walk(before, link, outcome=outcome, sections=sections)),
                                     I.as_steps(after, I.walk(after, link, outcome=outcome, sections=sections)))

    def action(self, actions, uuid):
        return next(a for a in actions
                    if a["WFWorkflowActionParameters"].get("UUID") == uuid)

    def text_of(self, actions, uuid):
        return self.action(actions, uuid)["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]["string"]

    def test_exception_is_not_a_blanket_unlock(self):
        for uuid, field in D.FIELDS.items():
            bad = copy.deepcopy(self.cur)
            p = self.action(bad, uuid)["WFWorkflowActionParameters"]
            if isinstance(p[field], str):
                p[field] += " unapproved edit"
            else:
                p[field]["Value"]["string"] += " unapproved edit"
            self.assertTrue(I.graph_problems(bad, self.good)[0])
        bad = copy.deepcopy(self.cur)
        instagram = self.text_of(bad, "454F5E3D-03E0-4151-814F-895ACF768637")
        self.assertIn("U=", instagram)   # the Instagram a-Shell command, not the YouTube one
        self.action(bad, "454F5E3D-03E0-4151-814F-895ACF768637")[
            "WFWorkflowActionParameters"]["WFTextActionText"]["Value"]["string"] = \
            instagram + "; echo altered"
        self.assertTrue(I.locked_problems(bad, self.good))
        bad = copy.deepcopy(self.cur)
        self.action(bad, "259C7097-21EA-46E0-8446-0C36B7523014")["WFWorkflowActionParameters"]["WFInput"] = {}
        self.assertTrue(I.graph_problems(bad, self.good)[0])
        lock = copy.deepcopy(self.lock)
        del lock["authorized_exceptions"][D.EXCEPTION_ID]
        with self.assertRaises(ValueError):
            D.apply(copy.deepcopy(self.good), lock)

    def test_threads_block_is_gated_and_never_replaces_a_working_path(self):
        # The block must sit behind its own If and must not be reachable on a
        # completed download (test_input.reach_problems also walks that).
        block = I.blocks(self.cur)["Threads server-failed posts"]
        first = min(block)
        self.assertEqual(I.kind(self.cur[first]), "comment")
        self.assertEqual(I.kind(self.cur[first + 1]), "conditional")
        self.assertEqual(I.params(self.cur[first + 1]).get("WFConditionalActionString"), "threads.")
        for link in ("https://www.threads.com/@zuck/post/Ddt7cL5EfUG",
                     "https://www.threads.net/@natgeo/post/DdzAoYVDY8o"):
            ran = [i for i, _ in I.walk(self.cur, link, outcome="completed")]
            self.assertFalse(set(ran) & block,
                             "the Threads tail block ran on a completed download")
        # The walker has no page body, so a failed Threads share takes the
        # no-media branch. That branch must open a URL action output, not the
        # userLink variable the report says never opens.
        failed = I.walk(self.cur, "https://www.threads.com/@zuck/post/Ddt7cL5EfUG", outcome="failed")
        opened = [self.cur[i] for i, _ in failed if I.kind(self.cur[i]) == "openurl"]
        self.assertEqual(len(opened), 1)
        src = opened[0]["WFWorkflowActionParameters"]["WFInput"]["Value"]
        self.assertEqual(src.get("Type"), "ActionOutput")
        self.assertNotEqual(src.get("VariableName"), "userLink")

    def run_shell(self, result):
        if not BASH.exists():
            self.skipTest("Git Bash unavailable; shell execution was not performed")
        command = next(a["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]["string"]
                       for a in self.cur if a["WFWorkflowActionParameters"].get("UUID") == D.COMMAND_UUID)
        # Substitute only the supplied URL and isolate all filesystem writes.
        command = command.replace("\ufffc", "https://www.youtube.com/watch?v=control")
        command = command.replace("$HOME", "$FED_TEST_ROOT")
        stubs = r'''
pip() { printf 'test package metadata\n'; }
ffmpeg() { return 0; }
open() { return 0; }
sleep() { return 0; }
python3() { "$FED_TEST_PYTHON" "$@"; }
yt-dlp() {
  if [ "$FED_TEST_RESULT" = retry-success ]; then
    if [ -f "$FED_TEST_ROOT/.attempted" ]; then
      printf media-payload > "$FED_TEST_ROOT/Documents/fed-dl.mp4"
      return 0
    fi
    : > "$FED_TEST_ROOT/.attempted"
    printf 'CONTROL ERROR: first attempt failed\n' >&2
    return 23
  fi
  if [ "$FED_TEST_RESULT" = success ]; then
    printf media-payload > "$FED_TEST_ROOT/Documents/fed-dl.mp4"
    return 0
  fi
  if [ "$FED_TEST_RESULT" = large-error ]; then
    "$FED_TEST_PYTHON" -c 'import sys; sys.stderr.write("x"*100000+"\nCONTROL ERROR\n")'
  else
    printf 'CONTROL ERROR: requested format unavailable\n' >&2
  fi
  return 23
}
'''
        with tempfile.TemporaryDirectory(prefix="fed-diagnostic-test-") as tmp:
            root = Path(tmp)
            (root / "Documents").mkdir()
            env = dict(os.environ, FED_TEST_ROOT=root.as_posix(),
                       FED_TEST_PYTHON=Path(sys.executable).as_posix(),
                       FED_TEST_RESULT=result, SHORTCUTS=(root / "shared").as_posix())
            proc = subprocess.run([str(BASH), "--noprofile", "--norc", "-c", stubs + command],
                                  env=env, capture_output=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace")[:500])
            log = (root / "Documents/fed-youtube-last.log").read_bytes()
            self.assertLessEqual(len(log), 65536)
            if result == "retry-success":
                # First attempt leaves no file, so FED updates yt-dlp and reruns
                # the identical command; the shortcut still gets its media.
                self.assertIn(b"retrying once", log)
                self.assertIn(b"CONTROL ERROR: first attempt failed", log)
                self.assertIn(b"yt-dlp exit status: 0", log)
                self.assertEqual((root / "shared/fed-kind.txt").read_text(), "photo")
                self.assertEqual((root / "shared/fed-media").read_bytes(), b"media-payload")
                self.assertEqual((root / "shared/fed-ext.txt").read_text(), "mp4")
                return
            self.assertIn(b"yt-dlp exit status: " + (b"0" if result == "success" else b"23"), log)
            self.assertEqual((root / "shared/fed-kind.txt").read_text(), "photo" if result == "success" else "missing")
            if result == "success":
                # A download that works must not pay for an update, and must not
                # dump the diagnostic log into a-Shell.
                self.assertNotIn(b"retrying once", log)
                self.assertNotIn(b"FED YouTube diagnostic", proc.stdout)
                self.assertEqual((root / "shared/fed-media").read_bytes(), b"media-payload")
                self.assertEqual((root / "shared/fed-ext.txt").read_text(), "mp4")
            else:
                self.assertIn(b"CONTROL ERROR", log)
                self.assertIn(b"CONTROL ERROR", proc.stdout)

    def test_state_files_are_written_before_the_helper_check(self):
        # The shortcut reads fed-kind.txt back with GetFileIntent the moment the
        # command returns. A slow or killed first-run install must not leave it
        # missing, which is what produced "the file can't be found".
        command = self.text_of(self.cur, D.COMMAND_UUID)
        for name in ("fed-kind.txt", "fed-ext.txt", "fed-media"):
            self.assertLess(command.index(name), command.index("pip show"),
                            "%s is written after the helper check" % name)

    def test_success_still_produces_same_media_handoff(self):
        self.run_shell("success")

    def test_a_failed_attempt_is_retried_once_with_updated_yt_dlp(self):
        self.run_shell("retry-success")

    def test_failure_retains_error_and_exit_status(self):
        self.run_shell("failure")

    def test_log_is_bounded(self):
        self.run_shell("large-error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
