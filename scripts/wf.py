#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal iOS Shortcuts action-graph authoring kit for fed.unsigned.plist.

Parameter names and value shapes are mirrored from actions already present in
shortcut/fed.unsigned.plist plus the ScPL/Cherri action definitions, so a
generated action is byte-compatible with what the Shortcuts app writes.

Only the action types this shortcut needs are implemented.
"""
import uuid

FFFC = "\ufffc"  # U+FFFC OBJECT REPLACEMENT CHARACTER: token slot in a string

# WFCondition values, all three already used by fed.unsigned.plist:
COND_IS = 4        # "is"            (Text is "completed")
COND_CONTAINS = 8  # "contains"      (Text contains "tiktok")
COND_HAS_VALUE = 100  # "has any value" (Variable has any value)


def new_uuid():
    return str(uuid.uuid4()).upper()


# --------------------------------------------------------------- token pieces
def tstr(*parts):
    """WFTextTokenString from str / attachment parts."""
    if len(parts) == 1 and isinstance(parts[0], str):
        return {"Value": {"string": parts[0]}, "WFSerializationType": "WFTextTokenString"}
    out, atts, pos = [], {}, 0
    for p in parts:
        if isinstance(p, str):
            out.append(p)
            pos += len(p)
        else:
            out.append(FFFC)
            atts["{%d, 1}" % pos] = p
            pos += 1
    v = {"string": "".join(out)}
    if atts:
        v["attachmentsByRange"] = atts
    return {"Value": v, "WFSerializationType": "WFTextTokenString"}


def coerce(cls):
    return {"CoercionItemClass": cls, "Type": "WFCoercionVariableAggrandizement"}


def dkey(key):
    return {"DictionaryKey": key, "Type": "WFDictionaryValueVariableAggrandizement"}


def var(name, aggs=None):
    """Reference a named variable."""
    v = {"Type": "Variable", "VariableName": name}
    if aggs:
        v["Aggrandizements"] = aggs
    return {"Value": v, "WFSerializationType": "WFTextTokenAttachment"}


def out(action, aggs=None):
    """Reference another action's output."""
    v = {"OutputName": action.name, "OutputUUID": action.uuid, "Type": "ActionOutput"}
    if aggs:
        v["Aggrandizements"] = aggs
    return {"Value": v, "WFSerializationType": "WFTextTokenAttachment"}


def file_ext(action):
    return out(action, [{"PropertyName": "File Extension",
                         "PropertyUserInfo": "WFFileExtensionProperty",
                         "Type": "WFPropertyVariableAggrandizement"}])


def dict_field(pairs):
    """WFDictionaryFieldValue, used for HTTP headers."""
    items = []
    for k, v in pairs:
        items.append({
            "WFItemType": 0,
            "WFKey": tstr(k) if isinstance(k, str) else k,
            "WFValue": tstr(v) if isinstance(v, str) else v,
        })
    return {"Value": {"WFDictionaryFieldValueItems": items},
            "WFSerializationType": "WFDictionaryFieldValue"}


# --------------------------------------------------------------------- actions
class Action:
    __slots__ = ("uuid", "name", "d")

    def __init__(self, ident, params, name=None):
        self.uuid = new_uuid()
        self.name = name or ident.rsplit(".", 1)[-1]
        p = dict(params)
        p["UUID"] = self.uuid
        self.d = {"WFWorkflowActionIdentifier": ident,
                  "WFWorkflowActionParameters": p}

    def __repr__(self):
        return "<%s %s>" % (self.name, self.uuid[:8])


class Graph:
    """Ordered action graph with control-flow bookkeeping."""

    def __init__(self):
        self.actions = []
        self._stack = []

    # -- internals
    def _push(self, action):
        self.actions.append(action)
        return action

    def _top_group(self):
        return self._stack[-1] if self._stack else None

    # -- plain actions
    def comment(self, text):
        a = Action("is.workflow.actions.comment", {"WFCommentActionText": text}, "Comment")
        return self._push(a)

    def text(self, *parts, name="Text"):
        a = Action("is.workflow.actions.gettext", {"WFTextActionText": tstr(*parts)}, name)
        return self._push(a)

    def setvar(self, varname, token, name=None):
        a = Action("is.workflow.actions.setvariable",
                   {"WFVariableName": varname, "WFInput": token},
                   name or ("Set " + varname))
        a.name = varname
        return self._push(a)

    def getval(self, key, src, name=None, varname=None):
        a = Action("is.workflow.actions.getvalueforkey",
                   {"WFDictionaryKey": key, "WFInput": src},
                   name or key)
        # the Shortcuts app stores the output name it shows in the UI
        a.d["WFWorkflowActionParameters"]["CustomOutputName"] = a.name
        return self._push(a)

    def download(self, url, method=None, headers=None, name="Contents of URL"):
        params = {"WFURL": url}
        if method:
            params["WFHTTPMethod"] = method
        if headers:
            params["ShowHeaders"] = True
            params["WFHTTPHeaders"] = dict_field(headers)
        a = Action("is.workflow.actions.downloadurl", params, name)
        return self._push(a)

    def match(self, pattern, src=None, case_sensitive=False, name="Matches"):
        params = {"WFMatchTextPattern": pattern,
                  "WFMatchTextCaseSensitive": case_sensitive}
        if src is not None:
            params["WFInput"] = src
        a = Action("is.workflow.actions.text.match", params, name)
        return self._push(a)

    def group(self, index, src, name="Group"):
        a = Action("is.workflow.actions.text.match.getgroup",
                   {"WFGetGroupType": "Group At Index", "WFGroupIndex": index,
                    "WFInput": src},
                   name)
        return self._push(a)

    def replace(self, find, repl, src, regex=False, case_sensitive=True,
                name="Replaced Text"):
        a = Action("is.workflow.actions.text.replace",
                   {"WFReplaceTextFind": find, "WFReplaceTextReplace": repl,
                    "WFInput": src, "WFReplaceTextCaseSensitive": case_sensitive,
                    "WFReplaceTextRegularExpression": regex},
                   name)
        return self._push(a)

    def urlencode(self, src, mode="Encode", name="URL Encoded Text"):
        a = Action("is.workflow.actions.urlencode",
                   {"WFEncodeMode": mode, "WFInput": src}, name)
        return self._push(a)

    def save_camera_roll(self, album=""):
        a = Action("is.workflow.actions.savetocameraroll",
                   {"WFPhotoAlbumName": album}, "Save to Camera Roll")
        return self._push(a)

    def save_file(self, src, name="Save File"):
        a = Action("is.workflow.actions.documentpicker.save",
                   {"WFInput": src}, name)
        return self._push(a)

    def notify(self, *parts):
        a = Action("is.workflow.actions.notification",
                   {"WFNotificationActionBody": tstr(*parts)}, "Show Notification")
        return self._push(a)

    def stop(self):
        return self._push(Action("is.workflow.actions.exit", {}, "Stop"))

    def delay(self, seconds):
        a = Action("is.workflow.actions.delay", {"WFDelayTime": str(seconds)}, "Wait")
        return self._push(a)

    def number(self, value):
        a = Action("is.workflow.actions.number",
                   {"WFNumberActionNumber": str(value)}, "Number")
        return self._push(a)

    def nothing(self):
        return self._push(Action("is.workflow.actions.nothing", {}, "Nothing"))

    # -- control flow
    def if_(self, condition, src, operand=None, name="If"):
        """Condition on a variable or action output.

        The Shortcuts app wraps a conditional's input as
        {"Type": "Variable", "Variable": <token attachment>} - see every
        conditional already in fed.unsigned.plist. A bare attachment here would
        not import the same way.
        """
        gid = new_uuid()
        params = {"GroupingIdentifier": gid, "WFCondition": condition,
                  "WFControlFlowMode": 0,
                  "WFInput": {"Type": "Variable", "Variable": src}}
        if operand is not None:
            params["WFConditionalActionString"] = operand
        self._push(Action("is.workflow.actions.conditional", params, name))
        self._stack.append(("if", gid))
        return gid

    def else_(self):
        kind, gid = self._stack[-1]
        assert kind == "if", "else_ outside an if"
        self._push(Action("is.workflow.actions.conditional",
                          {"GroupingIdentifier": gid, "WFControlFlowMode": 1}, "Otherwise"))
        return gid

    def endif(self):
        kind, gid = self._stack.pop()
        assert kind == "if", "endif outside an if"
        self._push(Action("is.workflow.actions.conditional",
                          {"GroupingIdentifier": gid, "WFControlFlowMode": 2}, "End If"))
        return gid

    def repeat_each(self, src, name="Repeat with Each"):
        gid = new_uuid()
        self._push(Action("is.workflow.actions.repeat.each",
                          {"GroupingIdentifier": gid, "WFControlFlowMode": 0,
                           "WFInput": src}, name))
        self._stack.append(("repeat", gid))
        return gid

    def endrepeat(self):
        kind, gid = self._stack.pop()
        assert kind == "repeat", "endrepeat outside a repeat"
        self._push(Action("is.workflow.actions.repeat.each",
                          {"GroupingIdentifier": gid, "WFControlFlowMode": 2}, "End Repeat"))
        return gid

    def close(self):
        """Close any group left open (used by a branch that always stops)."""
        while self._stack:
            kind, _ = self._stack[-1]
            if kind == "if":
                self.endif()
            else:
                self.endrepeat()

    # -- convenience: download a URL list and save each item
    def save_media_list(self, list_token, url_key=None, type_key=None,
                        notify_text=None, suffix=None):
        """Repeat over a list of {url,...} dicts (or plain URLs) and save each.

        Mirrors the media loop the shortcut already uses for the aggregator:
        audio goes to Files, everything else to Camera Roll. `suffix` is
        appended to each URL (used to force a JPEG off an image CDN).
        """
        self.repeat_each(list_token)
        item = var("Repeat Item")
        if url_key:
            u = self.getval(url_key, item, name="mediaURL")
            media_url = out(u)
        else:
            self.setvar("mediaURL", item)
            media_url = var("mediaURL")
        if suffix:
            media_url = out(self.text(media_url, suffix, name="mediaURLFormatted"))
        self.download(media_url, name="Media")
        media = self.actions[-1]
        if type_key:
            tv = self.getval(type_key, item, name="mediaType")
            self.setvar("mediaType", out(tv))
            self.if_(COND_IS, var("mediaType"), "audio")
            self.save_file(out(media))
            self.else_()
            self.save_camera_roll()
            self.endif()
        else:
            self.save_camera_roll()
        self.endrepeat()
        if notify_text:
            self.notify(notify_text)
        self.stop()


def wrap(actions, note):
    """Wrap a flat action list as a standalone graph body (no groups)."""
    g = Graph()
    g.actions = list(actions)
    g.comment(note)
    return g
