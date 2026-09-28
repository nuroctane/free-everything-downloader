"""Dump fed.unsigned.plist into a readable, nesting-aware action listing.

Usage: python -X utf8 scripts/dump.py [--out FILE] [--grep TEXT]
"""
import plistlib, sys, io, os, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'shortcut', 'fed.unsigned.plist')

SHORT = {
    'is.workflow.actions.comment': 'COMMENT',
    'is.workflow.actions.dictionary': 'DICT',
    'is.workflow.actions.getvalueforkey': 'GET-VALUE',
    'is.workflow.actions.setvariable': 'SETVAR',
    'is.workflow.actions.downloadurl': 'DOWNLOAD-URL',
    'is.workflow.actions.urlencode': 'URL-ENCODE',
    'is.workflow.actions.notification': 'NOTIFY',
    'is.workflow.actions.nothing': 'NOTHING',
    'is.workflow.actions.exit': 'STOP',
    'is.workflow.actions.conditional': 'IF',
    'is.workflow.actions.choosefrommenu': 'MENU',
    'is.workflow.actions.gettext': 'TEXT',
    'is.workflow.actions.setitemname': 'SET-NAME',
    'is.workflow.actions.url': 'URL',
    'is.workflow.actions.savetocameraroll': 'SAVE-CAMERA-ROLL',
    'is.workflow.actions.repeat.each': 'REPEAT-EACH',
    'is.workflow.actions.repeat.count': 'REPEAT-COUNT',
    'is.workflow.actions.number': 'NUMBER',
    'is.workflow.actions.math': 'MATH',
    'is.workflow.actions.delay': 'DELAY',
    'is.workflow.actions.openurl': 'OPEN-URL',
    'is.workflow.actions.url.expand': 'EXPAND-URL',
    'is.workflow.actions.detect.link': 'DETECT-LINK',
    'is.workflow.actions.appendvariable': 'APPEND-VAR',
    'is.workflow.actions.waittoreturn': 'WAIT-RETURN',
    'is.workflow.actions.file.createfolder': 'CREATE-FOLDER',
    'is.workflow.actions.documentpicker.save': 'SAVE-FILE',
    'is.workflow.actions.documentpicker.open': 'OPEN-FILE',
    'is.workflow.actions.makegif': 'MAKE-GIF',
    'is.workflow.actions.getfile': 'GET-FILE',
    'is.workflow.actions.getimagesfrominput': 'GET-IMAGES',
    'is.workflow.actions.selectphotos': 'SELECT-PHOTOS',
    'is.workflow.actions.ask': 'ASK',
    'is.workflow.actions.getmyworkflows': 'GET-SHORTCUTS',
    'AsheKube.app.a-Shell-mini.ExecuteCommandIntent': 'A-SHELL-EXEC',
    'AsheKube.app.a-Shell-mini.GetFileIntent': 'A-SHELL-GETFILE',
}


def sval(v, depth=0):
    """Render a WFTextTokenString-ish value to plain text with {placeholders}."""
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, dict):
        st = v.get('WFSerializationType')
        if st == 'WFTextTokenString':
            inner = v.get('Value', {})
            txt = inner.get('string', '')
            atts = inner.get('attachmentsByRange', {}) or {}
            for rng, att in atts.items():
                kind = att.get('Type') or att.get('WFSerializationType')
                if att.get('Type') == 'Variable':
                    rep = '{%s}' % (att.get('VariableName') or att.get('OutputUUID', '?'))
                elif att.get('Type') == 'ActionOutput':
                    rep = '{out:%s}' % (att.get('OutputName') or att.get('OutputUUID', '?'))
                else:
                    rep = '{%s}' % (kind or 'token')
                if '\ufffc' in txt:
                    txt = txt.replace('\ufffc', rep, 1)
                else:
                    txt = txt + rep
            return txt
        if st == 'WFTextTokenAttachment':
            att = v.get('Value', {})
            if att.get('Type') == 'Variable':
                return '{%s}' % (att.get('VariableName') or att.get('OutputUUID', '?'))
            return '{out:%s}' % (att.get('OutputName') or att.get('OutputUUID', '?'))
        if st == 'WFDictionaryFieldValue':
            items = v.get('Value', {}).get('WFDictionaryFieldValueItems', [])
            parts = []
            for it in items:
                parts.append('%s=%s' % (sval(it.get('WFKey')), sval(it.get('WFValue'))))
            return '{' + ', '.join(parts) + '}'
        return str({k: sval(x) for k, x in list(v.items())[:10]})[:400]
    if isinstance(v, list):
        return '[' + ', '.join(sval(x) for x in v) + ']'
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--grep')
    a = ap.parse_args()
    d = plistlib.load(open(SRC, 'rb'))
    acts = d['WFWorkflowActions']
    buf = io.StringIO()
    indent = 0
    for i, act in enumerate(acts):
        ident = act.get('WFWorkflowActionIdentifier', '?')
        p = act.get('WFWorkflowActionParameters', {}) or {}
        name = SHORT.get(ident, ident)
        mode = p.get('WFControlFlowMode')
        lines = []
        if name == 'IF':
            if mode == 0:
                lines.append('IF %s | %s | %s' % (sval(p.get('WFInput')), p.get('WFCondition', ''), sval(p.get('WFConditionalActionString'))))
            elif mode == 1:
                indent = max(0, indent - 1)
                lines.append('ELSE')
            else:
                indent = max(0, indent - 1)
                lines.append('ENDIF')
        elif name == 'MENU':
            if mode == 0:
                lines.append('MENU prompt=%s' % sval(p.get('WFMenuPrompt')))
                for m in (p.get('WFMenuItems') or []):
                    lines.append('   ITEM %s' % sval(m))
            elif mode == 1:
                indent = max(0, indent - 1)
                lines.append('CASE %s' % sval(p.get('WFMenuItemTitle')))
            else:
                indent = max(0, indent - 1)
                lines.append('END-MENU')
        elif name == 'COMMENT':
            lines.append('COMMENT %s' % sval(p.get('WFCommentActionText')).replace('\n', '\n           # '))
        elif name == 'DICT':
            lines.append('DICT name=%s' % sval(p.get('CustomOutputName')))
            lines.append('     %s' % sval(p.get('WFItems'))[:4000])
        elif name == 'DOWNLOAD-URL':
            lines.append('DOWNLOAD-URL %s' % sval(p.get('WFURL')))
            if p.get('WFHTTPMethod'):
                lines.append('     method=%s' % p.get('WFHTTPMethod'))
            if p.get('WFJSONValues'):
                lines.append('     json=%s' % sval(p.get('WFJSONValues'))[:1500])
            if p.get('WFHTTPHeaders'):
                lines.append('     headers=%s' % sval(p.get('WFHTTPHeaders'))[:500])
            if p.get('WFHTTPBodyType'):
                lines.append('     bodytype=%s' % p.get('WFHTTPBodyType'))
        elif name == 'GET-VALUE':
            lines.append('GET-VALUE key=%s type=%s from=%s' % (sval(p.get('WFDictionaryKey')), p.get('WFGetDictionaryValueType'), sval(p.get('WFInput'))))
        elif name == 'SETVAR':
            lines.append('SETVAR %s = %s' % (p.get('WFVariableName'), sval(p.get('WFInput'))))
        elif name == 'TEXT':
            lines.append('TEXT %s' % sval(p.get('WFTextActionText')))
        elif name == 'NOTIFY':
            lines.append('NOTIFY %s' % sval(p.get('WFNotificationActionBody')))
        elif name == 'URL-ENCODE':
            lines.append('URL-ENCODE mode=%s in=%s' % (p.get('WFEncodeMode'), sval(p.get('WFInput'))))
        elif name == 'SAVE-CAMERA-ROLL':
            lines.append('SAVE-CAMERA-ROLL album=%s' % sval(p.get('WFPhotoAlbumName')))
        elif name == 'A-SHELL-EXEC':
            lines.append('A-SHELL-EXEC %s' % sval(p.get('command') or p.get('Command') or p))
        elif name == 'A-SHELL-GETFILE':
            lines.append('A-SHELL-GETFILE %s' % sval(p.get('path') or p))
        else:
            simple = {k: sval(v) for k, v in p.items()}
            lines.append('%s %s' % (name, str(simple)[:400]))
        for ln in lines:
            buf.write('%s%4d  %s\n' % ('  ' * indent, i, ln))
        if name == 'IF' and mode == 0:
            indent += 1
        elif name == 'MENU' and mode == 1:
            indent += 1
        elif name in ('REPEAT-EACH', 'REPEAT-COUNT') and mode == 0:
            indent += 1
        elif name in ('REPEAT-EACH', 'REPEAT-COUNT') and mode == 2:
            indent = max(0, indent - 1)
    text = buf.getvalue()
    if a.grep:
        pat = a.grep.lower()
        for ln in text.splitlines():
            if pat in ln.lower():
                print(ln)
        return
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(text)
        print('wrote', a.out, len(text), 'chars')
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
