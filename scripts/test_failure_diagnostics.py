"""Small local tests: exception scope, the Threads tail block, and YouTube back on 1.7.

No network, installs, real user folders or iOS apps are used by these tests.
"""
import copy
import json
import plistlib
import unittest
from pathlib import Path

import failure_diagnostics as D
import test_input as I

ROOT = Path(__file__).resolve().parents[1]


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
        self.assertEqual(sorted(new_blocks), ["Threads server-failed posts", "YouTube original links",
                                            "YouTube shares without a link"])
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

    def test_youtube_is_back_to_the_confirmed_1_7_command(self):
        # 2026-10-14: the logged 1.7.3 command hid yt-dlp's output and looked
        # like a hang on the phone. YouTube's command and failure notice must be
        # the confirmed 1.7 text again, byte for byte.
        notice = "4D12CADC-FD41-4F7B-B76F-74F5BDC9EA48"
        self.assertNotIn(D.COMMAND_UUID, D.FIELDS)
        self.assertNotIn(notice, D.FIELDS)
        for uuid, field in ((D.COMMAND_UUID, "WFTextActionText"),
                            (notice, "WFNotificationActionBody")):
            self.assertEqual(self.action(self.cur, uuid)["WFWorkflowActionParameters"][field],
                             self.action(self.good, uuid)["WFWorkflowActionParameters"][field])

if __name__ == "__main__":
    unittest.main(verbosity=2)
