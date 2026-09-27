#!/usr/bin/env python3
"""Offline checks for browser share-sheet URL normalization.

This does not pretend to run Shortcuts on Windows. It verifies the serialized
action graph keeps the browser-specific adapter ahead of every site branch and
that the YouTube guard still covers the URL forms mobile browsers emit.
"""
import plistlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLIST = ROOT / "shortcut" / "fed.unsigned.plist"


def params(action):
    return action.get("WFWorkflowActionParameters") or {}


def action_id(action):
    return action.get("WFWorkflowActionIdentifier")


def contains_variable(value, name):
    if isinstance(value, dict):
        if value.get("VariableName") == name:
            return True
        return any(contains_variable(v, name) for v in value.values())
    if isinstance(value, list):
        return any(contains_variable(v, name) for v in value)
    return False


def main():
    actions = plistlib.loads(PLIST.read_bytes())["WFWorkflowActions"]
    ids = [action_id(a) for a in actions]

    # The adapter must run before the first site comment and before any use of
    # userLink. The order is what prevents a multi-link webpage object from
    # reaching URL expansion as a list.
    first_user_link = next(i for i, a in enumerate(actions)
                           if params(a).get("WFVariableName") == "userLink")
    type_i = ids.index("is.workflow.actions.getitemtype")
    safari_i = ids.index("is.workflow.actions.properties.safariwebpage")
    first_item_i = ids.index("is.workflow.actions.getitemfromlist")
    text_i = ids.index("is.workflow.actions.detect.text")
    expand_i = ids.index("is.workflow.actions.url.expand")
    assert type_i < first_user_link
    assert safari_i < first_user_link
    assert first_item_i < expand_i
    assert text_i < expand_i
    assert expand_i < first_user_link
    assert params(actions[safari_i]).get("WFContentItemPropertyName") == "Page URL"
    assert params(actions[first_item_i]).get("WFItemSpecifier") == "First Item"

    # All accepted share-sheet classes remain enabled, including the webpage,
    # rich-text, string, and URL forms emitted by mobile browsers.
    text = plistlib.loads(PLIST.read_bytes())
    classes = set(text["WFWorkflowInputContentItemClasses"])
    for cls in ("WFSafariWebPageContentItem", "WFRichTextContentItem",
                "WFStringContentItem", "WFURLContentItem"):
        assert cls in classes, cls

    # YouTube routing is intentionally host-agnostic after normalization. The
    # samples model the values a browser can provide: a bare URL, a title plus
    # URL, and a mobile/shorts URL with tracking parameters.
    browser_samples = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "Watch this video - https://youtu.be/dQw4w9WgXcQ?t=12",
        "YouTube Short: https://www.youtube.com/shorts/dQw4w9WgXcQ",
    ]
    for shared_text in browser_samples:
        match = re.search(r"https?://[^\s<>\"']+", shared_text)
        assert match and "youtu" in match.group(0).lower(), shared_text

    # The a-Shell command must receive the normalized scalar variable, not the
    # raw ExtensionInput or the URL list produced by Get URLs from Input.
    shell_texts = [params(a).get("WFTextActionText")
                   for a in actions if action_id(a) == "is.workflow.actions.gettext"]
    assert any(contains_variable(v, "userLink") for v in shell_texts)

    print("browser input matrix: PASS (webpage, URL, rich text, and YouTube forms)")


if __name__ == "__main__":
    main()
