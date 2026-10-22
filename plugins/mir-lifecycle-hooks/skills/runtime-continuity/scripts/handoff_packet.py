"""Stateless common handoff supply/check. Read-only, offline, no model or adapter."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

try:
    import tomllib
except ImportError:  # Claude may run hooks with macOS /usr/bin/python3 (3.9).
    tomllib = None

LIMIT = 1024 * 1024
STARTED = time.monotonic()
WARNING = 'Mir handoff WARNING: '
STAMP = r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)'
LABEL = re.compile(
    r'^\s*(?:#{1,6}\s+|[-*]\s+)?(?:\*\*)?'
    r'(May not|May-not|May|Sources|Exclude|Do not forward|Not read|Protected)'
    r'(?:\*\*)?\s*(?:\([^\n)]*\)\s*)?(?::\s*(?:\*\*)?(.*)|$)',
    re.IGNORECASE,
)
# Literal Korean forms are escaped to keep distributed source English/ASCII.
PROHIBITION = re.compile(
    r'\b(?:do not|don.t|never|no (?:commands|file changes|scratch writes))\b|'
    r'\b(?:commands|writes) (?:are )?(?:forbidden|prohibited)\b|'
    r'(?:\uc9c0\s*\ub9d0(?!\ub77c\ub294|\ub77c\uace0)|'
    r'\uc9c0\s*\ub9c8(?:\uc138\uc694|\ub77c)?|'
    r'\uc9c0\s*\uc54a\uace0|\uc2e4\ud589\s*\uc5c6\uc774|'
    r'\uae08\uc9c0(?!\s*\ubc94\uc704|\ub41c)|\ud558\uba74\s*\uc548)', re.I,
)
ACTION = re.compile(
    r'\b(?:edit\w*|modif\w*|chang\w*|writ\w*|creat\w*|delet\w*|remov\w*|'
    r'run\w*|execut\w*|test\w*|check\w*|install\w*|commit\w*|push\w*|'
    r'network\w*|internet|delegat\w*|spawn\w*|deploy\w*|releas\w*)\b|'
    r'(?:\uc218\uc815|\ubcc0\uacbd|\ud3b8\uc9d1|\uc4f0\uae30|\uc791\uc131|'
    r'\uc0dd\uc131|\uc0ad\uc81c|\uc2e4\ud589|\uc218\ud589|\uac80\uc99d|'
    r'\ud14c\uc2a4\ud2b8|\uc124\uce58|\ucee4\ubc0b|\ud478\uc2dc|'
    r'\ub124\ud2b8\uc6cc\ud06c|\uc778\ud130\ub137|\uc704\uc784|'
    r'\uc704\ud0c1|\ud638\ucd9c|\ubc30\ud3ec)', re.I,
)
READ = re.compile(r'\b(?:read|inspect)\b|(?:\uc77d|\uc5f4\ub78c)', re.I)
# A packet may be translated or relabelled: forwarded pin keys or a handoff heading also count.
PACKET = re.compile(
    r'qualified target\s*:|handoff pins:|\bmay[ -]not\s*:|"(?:pin_inventory|mapping_sha256)"\s*:|'
    r'^#{1,6}[^\n]*(?:handoff|brief|\ud578\ub4dc\uc624\ud504|\uc9c0\uc2dc\ubb38|\ube0c\ub9ac\ud504|\uc778\uacc4)',
    re.I | re.M,
)

# Relative file paths; Korean particles may follow a path directly.
CITED = re.compile(r'(?<![\w./~:-])\.?[\w-][\w.-]*(?:/[\w.-]+)*\.[A-Za-z0-9]+(?![A-Za-z0-9_/-])')
SHELL_TOOLS = {'bash', 'shell', 'shell_command', 'exec_command', 'js', 'js_reset',
               'node_repl', 'python', 'python_repl', 'js_repl', 'javascript_repl'}
WRITE_TOOLS = {'write', 'edit', 'multiedit', 'notebookedit', 'apply_patch'}
QUOTED = re.compile(r'`([^`\n]+)`|"([^"\n]+)"|(?<!\w)\'([^\'\n]+)\'(?!\w)')
UNQUOTED_EXCLUSION = re.compile(
    r'(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]{3,})'
    r'(?:\ub294|\uc740|\ub97c|\uc744|\uc774|\uac00)?\s*'
    r'(?:\uc804\ub2ec|\ud3ec\ud568)\ud558\uc9c0\s*(?:\uc54a|\ub9d0)|'
    r'\b(?i:do not (?:forward|include))\s+([A-Z][A-Z0-9_]{3,})(?![A-Za-z0-9_])|'
    r'(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]{3,})\s+(?i:must not be forwarded)\b'
)
SHELL_TOOL_RULE = ('Shell tools and code interpreters (for example node_repl or a Python REPL) '
                   'must not be called in this turn')
FILE_TOOL_RULE = 'Write/Edit/apply_patch and file-writing tools must not be called in this turn'
ATTEMPT_RULE = '; attempts are compliance failures even if denied.'
RECEIVED_PINS = re.compile(r'\b(?:handoff )?pins:\s*(?:```(?:json)?\s*)?', re.I)
BASE_PINS = ['repository_root', 'head', 'mapping.identity', 'mapping.version',
             'mapping.digest', 'contract.identity', 'contract.version', 'contract.digest']
TARGET_NAME = r'(?:qualified target|\ub300\uc0c1)\b(?:[ \t]*\([^\n)]*\))?'
PIN_KEY = (r'(?:repository_root|head|(?:mapping|contract)\.(?:identity|version|digest)|'
           r'sources\[\d+\]\.(?:digest|sha256|revision))')
NON_PIN_NAMES = {'lifecycle', 'temporal', 'epistemic', 'verification', 'evidence', 'unknowns',
                 'reason', 'reasons', '\uc774\uc720', 'sha256', 'revision'}
COMPLETE_ARTIFACT_RULE = (
    'Re-send the complete corrected artifact as your final message; it replaces the previous '
    'one, so do not send only the changed sections.'
)
RECEIPT_RULE = (
    'Received handoff: label every pin verified-in-repo, parent-supplied or unavailable; '
    'every path claimed verified-in-repo needs a this turn Read/Grep/Glob or shell reference. '
    'Digest/revision/HEAD claims need this-turn digest/git computation or mapping --handoff; '
    'a file read alone does not verify them. State a limitation if no local tool was used, '
    'or if commands are forbidden and no reader was used. ' + COMPLETE_ARTIFACT_RULE
)


def recipient(prompt: str) -> bool:
    """A qualified packet with pins or two other fields; authoring takes precedence."""
    if detect(prompt):
        return False
    plain = re.sub(r'[*`]', '', prompt)
    lines = plain.splitlines()
    target_label = (r'^\s*(?:#{1,6}\s+(?:\d+[.)]\s*)?'
                    + TARGET_NAME + r'|(?:[-+]\s*)?' + TARGET_NAME + r'\s*(?::|$))')
    target = any(
        re.search(target_label, line, re.I)
        and re.search(r'(?<![\w:/])[\w.-]+:[\w./-]+', '\n'.join(lines[i:i + 4]))
        for i, line in enumerate(lines))
    fields = sum(bool(re.search(pattern, plain, re.I)) for pattern in (
        r'\b(?:status axes|lifecycle|temporal|epistemic|verification)\b|\uc0c1\ud0dc',
        r'\bpins\b|\ud540', r'\bunknowns\b|\ubbf8\ud655\uc778',
        r'\bmay(?:[ -]not)?\s*:|\bauthority\b|\ud5c8\uc6a9|\uae08\uc9c0'))
    return bool(target and (fields >= 2 or re.search(
        r'handoff pins:|\bpins\s*:|sha256[^\n]*[0-9a-f]{64}', plain, re.I)))


def detect(prompt: str) -> bool:
    """Recognize explicit imperative requests, excluding fenced/quoted examples."""
    text = re.sub(r'```[\s\S]*?```|~~~[\s\S]*?~~~', '', prompt)
    for line in text.splitlines():
        if line.lstrip().startswith('>'):
            continue
        line = line.strip().lower()
        if re.match(r'^(?:please\s+)?(?:do not|don.t|never)\b', line):
            continue
        if re.search(r'(?:\uc791\uc131|\uc704\uc784)\ud558\uc9c0\s*\ub9c8', line):
            continue
        if re.search(
            r'^(?:please\s+)?(?:write|prepare|draft|create|give|send)\b'
            r'.*\b(?:handoff|brief)\b.*\b(?:agent|codex|claude)\b', line
        ) or re.search(
            r'^(?:please\s+)?delegate\b.*\b(?:agent|codex|claude)\b', line
        ):
            return True
        # Unicode escapes keep this distributed source ASCII.
        if re.search(
            r'(?:\ub2e4\ub978|\ub2e4\uc74c|\ud558\uc704)\s*\uc5d0\uc774\uc804\ud2b8'
            r'.*(?:\ud578\ub4dc\uc624\ud504|\ube0c\ub9ac\ud504|\uc9c0\uc2dc\ubb38|\uc778\uacc4\ubb38)'
            r'.*(?:\uc791\uc131|\uc368\s*(?:\uc918|\uc8fc))', line
        ):
            return True
        if re.search(
            r'(?:\ud578\ub4dc\uc624\ud504|\ube0c\ub9ac\ud504|\uc9c0\uc2dc\ubb38|\uc778\uacc4\ubb38)'
            r'.*(?:\ub2e4\ub978|\ub2e4\uc74c|\ud558\uc704)\s*\uc5d0\uc774\uc804\ud2b8'
            r'(?:\uc5d0\uac8c|\ud55c\ud14c)'
            r'.*(?:\ub118\uae30|\ub118\uae38|\uc804\ub2ec|\uc778\uacc4|'
            r'\ub9e1\uae30|\ub9e1\uae38)', line
        ):
            return True
    return False


def owner_sections(prompt: str) -> dict:
    """Preserve labeled grants and explicit prose prohibitions; never infer action grants."""
    values = {'may': [], 'may_not': [], 'sources': [], 'excluded': []}
    active = None
    fenced = False
    explicit = False
    excluded = []
    for line in prompt.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            active = None
            continue
        if fenced or line.lstrip().startswith('>'):
            continue
        for literal in QUOTED.finditer(line):
            before, after = line[:literal.start()], line[literal.end():]
            if (re.search(r'\b(?:do not|don.t|never)\s+(?:include|forward|copy)\b[^.!?;]*$'
                          r'|\bauthor-only\s+marker\s*$', before, re.I)
                    or re.match(r'(?:\ub294|\uc740|\ub97c|\uc744)?\s*'
                                r'(?:\uc804\ub2ec|\ud3ec\ud568|\ubcf5\uc0ac)\ud558\uc9c0\s*'
                                r'(?:\ub9c8|\ub9d0)', after)):
                excluded.append(next(value for value in literal.groups() if value is not None))
        for literal in UNQUOTED_EXCLUSION.finditer(QUOTED.sub(' ', line)):
            excluded.append(next(value for value in literal.groups() if value is not None))
        match = LABEL.match(line)
        if match:
            label, value = match.groups()
            active = {'may': 'may', 'may not': 'may_not', 'may-not': 'may_not',
                      'sources': 'sources', 'exclude': 'excluded',
                      'do not forward': 'excluded', 'not read': 'may_not',
                      'protected': 'may_not'}[label.lower()]
            if active in {'may', 'may_not'}:
                explicit = True
            if value:
                values[active].append(value)
        elif active and re.match(r'^\s*[-*]\s+', line):
            values[active].append(line)  # preserve owner spelling and bullet text
        else:
            active = None
            # Forward only the prohibiting sentence, not the surrounding task prose.
            for sentence in re.split(r'(?<=[.!?])(?=\s|$|[\uac00-\ud7a3])\s*', line):
                if PROHIBITION.search(sentence):
                    values['may_not'].append(sentence.strip())
    return {
        'may': '\n'.join(values['may']), 'may_not': '\n'.join(values['may_not']),
        'sources': '\n'.join(values['sources']),
        'explicit_authority': explicit,
        'excluded': list(dict.fromkeys(
            [item.strip().strip('`') for line in values['excluded']
             for item in re.split(r';|\n', line) if item.strip()] + excluded)),
    }


def normalized(text: str) -> str:
    return ' '.join(re.findall(r'\w+', text.casefold()))


def future_grant(text: str) -> bool:
    match = re.search(r'\b(?:only after|if|once) (?:a )?'
                      r'(?:separate|explicit|future|new) owner '
                      r'(?:grant|authoriz\w*|approval|permission)\b', text, re.I)
    if not match:
        match = re.search(r'(?:\ubcc4\ub3c4|\uba85\uc2dc\uc801)[^.!?;\n]*'
                          r'(?:\uc2b9\uc778|\ud5c8\uac00)[^.!?;\n]*'
                          r'(?:\ud6c4|\uc804|\ud574\uc57c|\uc154\uc57c|\uc788\uc5b4\uc57c)', text)
    return bool(match and not re.search(r'[.!?;](?:\s|$)', text[:match.start()]))


def items(text: str) -> list[str]:
    return [value.strip().lstrip('-* ').strip() for value in re.split(r';|\n', text)
            if value.strip().lstrip('-* ').strip()]


def authority_defects(body: str, boundary: dict) -> list[str]:
    """Shared lexical grant/exclusion check, independent of packet field language."""
    defects = [f'excluded item #{i} appears in forwarded artifact'
               for i, value in enumerate(boundary['excluded'], 1) if value in body]
    plain = re.sub(r'[*`#]', '', body)
    plain = re.sub(r'(?m)^(\s*(?:[-+]\s*)?)\ud5c8\uc6a9\s*:', r'\1May:', plain)
    plain = re.sub(r'(?m)^(\s*(?:[-+]\s*)?)\uae08\uc9c0\s*:', r'\1May not:', plain)
    owner = owner_sections(plain)
    grant = ' ; '.join(normalized(item) for item in items(boundary['may']))
    denied = [normalized(item) for item in items(boundary['may_not'])]
    grant_prose = '\n'.join(sentence for line in plain.splitlines() if not LABEL.match(line)
                            for sentence in re.split(r'(?<=[.!?])\s+', line)
                            if not future_grant(sentence))
    inline = re.findall(r'(?im)\b(?:you|recipient|agent) may (?!not\b)([^\n!?]+)', grant_prose)
    korean = re.findall(
        r'(?m)^([^\n]*(?:\ud574\ub3c4\s*\ub429\ub2c8\ub2e4|'
        r'\ud560\s*\uc218\s*\uc788\uc2b5\ub2c8\ub2e4|'
        r'\ud5c8\uc6a9\ub429\ub2c8\ub2e4)[^\n]*)', grant_prose)
    inline += [item for item in korean if ACTION.search(item) or READ.search(item)]
    grants = [sentence for item in items(owner['may'])
              for sentence in re.split(r'(?<=[.!?])\s+', item)]
    for item in grants + inline:
        item = item.rstrip('.')
        candidate = normalized(item)
        if candidate in {'none', 'no permissions', 'unavailable'}:
            continue
        if re.match(r'^This (?:packet|handoff|document) (?:does not grant|grants no) '
                    r'(?:current )?authority\b', item, re.I):
            continue
        if future_grant(item):
            continue
        permitted = (f' {candidate} ' in f' {grant} '
                     if boundary.get('explicit_authority', True)
                     else bool(READ.search(item)) and not ACTION.search(item))
        permitted = permitted or (bool(READ.search(item)) and not ACTION.search(item))
        if (not candidate or not permitted
                or any(deny and f' {deny} ' in f' {candidate} ' for deny in denied)):
            defects.append('extra may: ' + item)
    for i, value in enumerate(boundary['excluded'], 1):
        defects = [defect.replace(value, f'[excluded item #{i}]') for defect in defects]
    return defects


def check_packet(body: str, state: dict) -> list[str]:
    """Conservative format/lexical checks, never a semantic permission decision."""
    defects = []
    if state.get('root') is not None:
        defects.extend(namespace_defects(body, state['root']))
    pins = state['pins']
    if not re.search(r'(?m)^handoff pins:$', body) and supplied_json_present(body, pins):
        defects.append("supplied pins header altered (keep the literal 'handoff pins:' line)")
    if body.count('handoff pins:') > 1:
        defects.append('duplicate supplied pins blocks')
    if not matching_pins(body, pins):
        differences = pin_differences(body, pins)
        defects.append('missing/changed supplied pins (copy the entire supplied block unchanged): '
                       + ', '.join(differences))
    # Inspect the entire enclosing artifact, not only a fenced packet or its first section.
    plain = re.sub(r'(?m)^[ \t]*[-+][ \t]+', '',
                   re.sub(r'[*`#]', '', body.replace(pins, '')))
    if not re.search(r'(?im)^\s*' + TARGET_NAME + r'\s*:\s*[\w.-]+:[\w./-]+', plain):
        defects.append('missing qualified target (namespace:local-id)')
    for axis in ('lifecycle', 'temporal', 'epistemic', 'verification'):
        if not re.search(rf'(?im)^[ \t]*{axis}:[ \t]*\S[^\n]*', plain):
            defects.append('missing ' + axis + ' status')
    evidence = re.search(r'(?im)^[ \t]*evidence:[ \t]*(.+)', plain)
    if not evidence or not (
        re.search(r'\b(?:parent-supplied|verified-in-repo|source|provenance)\b', evidence[1], re.I)
        and re.search(STAMP, evidence[1])
    ):
        defects.append('missing evidence provenance/time (source and ISO-8601 observation time)')
    for field in ('unknowns', 'self-check'):
        if not re.search(rf'(?im)^[ \t]*{field}:[ \t]*\S[^\n]*', plain):
            defects.append('missing ' + field)
    owner = owner_sections(re.sub(r'[`#]', '', body.replace(pins, '')))
    for label in ('may', 'may not'):
        if not re.search(rf'(?im)^\s*{label.replace(" ", "[ -]")}'
                         r'\s*(?:\([^\n)]*\)\s*)?:', plain):
            defects.append('missing ' + label)
    for denied_item in items(state['owner']['may_not']):
        if any(value in denied_item for value in state['owner']['excluded']):
            continue  # author-only literal; never require forwarding excluded data
        if normalized(denied_item) not in normalized(owner['may_not']):
            defects.append('missing owner restriction: ' + denied_item)
    defects.extend(authority_defects(body.replace(pins, ''), state['owner']))
    # Missing pin values remain unknown: require an explicit self-check for each gap.
    pin_data = json.loads(pins.split('handoff pins:\n', 1)[1])
    self_check = re.search(r'(?ims)^\s*self-check:\s*(.*)', plain)
    inventory = self_check[1] if self_check else ''
    for field in ('qualified target', 'lifecycle', 'temporal', 'epistemic', 'verification',
                  'evidence', 'unknowns', 'may', 'may not'):
        if not re.search(rf'(?<![\w.-])(?:field )?{field}\s*[=:]\s*'
                         r'(?:present|missing|abbreviated|unchecked)\b', inventory, re.I):
            defects.append('missing self-check field: ' + field)
    names = [entry['pin'] for entry in pin_data.get('pin_inventory', [])]
    if not names:
        names = ['repository_root', 'head', 'mapping.identity', 'mapping.version',
                 'mapping.digest', 'contract.identity', 'contract.version', 'contract.digest']
        for index, _ in enumerate(pin_data.get('sources', [])):
            names.extend([f'sources[{index}].digest', f'sources[{index}].revision'])
    for name in names:
        if not re.search(rf'(?<![\w.-])(?:pin )?{re.escape(name)}\s*[=:]\s*'
                         r'(?:parent-supplied|verified-in-repo|unavailable|missing|abbreviated|unchecked)\b',
                         inventory, re.I):
            defects.append('missing self-check pin: ' + name)
    for gap in pin_data.get('unknowns', []):
        if gap not in inventory:
            defects.append('unchecked pin gap: ' + gap)
    for index, excluded in enumerate(state['owner']['excluded'], 1):
        defects = [defect.replace(excluded, f'[excluded item #{index}]') for defect in defects]
    return defects


def context_text(owner: dict, pins: str | None = None, prompt: str | None = None) -> str:
    if pins is None:
        names = ['repository_root', 'head', 'mapping.identity', 'mapping.version',
                 'mapping.digest', 'contract.identity', 'contract.version', 'contract.digest']
        for index, _ in enumerate(items(owner['sources'])):
            names.extend([f'sources[{index}].digest', f'sources[{index}].revision'])
        pins = 'unavailable pins: ' + '; '.join(names)
    return (
        'Mechanical handoff packet: copy verbatim; do not add permissions.\n' + pins + '\n'
        + ('Prompt SHA256: ' + hashlib.sha256(prompt.encode()).hexdigest() + '\n'
           if prompt is not None else '') +
        'Owner boundary (author context; exclusion values must not be forwarded):\n'
        'May: ' + (owner['may'] or ('unavailable' if owner['explicit_authority']
                                  else 'read/inspect only')) + '\n'
        'May not: ' + (owner['may_not'] or 'unavailable; do not infer authority') + '\n'
        'Exclude: ' + '; '.join(owner['excluded']) + '\n'
        'Packet labels: Qualified target (namespace:local-id); Lifecycle; Temporal; Epistemic; '
        'Verification; Evidence (provenance + ISO observation time); Unknowns; May; May not; '
        'Self-check (field NAME=present/missing/abbreviated/unchecked; '
        'pin NAME=parent-supplied/verified-in-repo/missing/abbreviated/unchecked, individually, '
        'plus each exact unknown pin reason). Preserve the entire pins block above unchanged. '
        'For every other repository file you cite, add its sha256 and last-change revision from '
        '`python3 scripts/mir_ontology.py mapping --handoff <paths>` sources. '
        'Inspect the whole forwarded artifact, including enclosing text. '
        + COMPLETE_ARTIFACT_RULE + '\n' + tool_attempt_rule(owner)
    )


def warning(message: str, owner: dict | None = None) -> None:
    # Do not expose exception strings, prompt contents, subprocess stderr, or excluded values.
    print(WARNING + message, file=sys.stderr)
    output = {'systemMessage': WARNING + message}
    if owner is not None:
        output['hookSpecificOutput'] = {
            'hookEventName': 'UserPromptSubmit', 'additionalContext': context_text(owner)}
    print(json.dumps(output))


def restricted(prompt: str) -> bool:
    owner = owner_sections(prompt)
    # Quoted command examples are not a prohibition on all commands. Never scan
    # raw packet/fenced/blockquote text after owner_sections has excluded it.
    prohibition = QUOTED.sub(' ', owner['may_not'])
    deny = normalized(prohibition)
    return bool(re.search(
        r'\b(?:run|execute) (?:any )?(?:commands|shell|python)\b', deny
    ) or re.search(
        r'\b(?:no commands|commands (?:are )?(?:forbidden|prohibited)'
        r'|do not (?:run|execute) (?:any )?commands)\b',
        prohibition.casefold(),
    ) or re.search(r'(?:\uba85\ub839|\ucee4\ub9e8\ub4dc|\uc250|\ud30c\uc774\uc36c)'
                   r'[^\n.!?]*(?:\uc9c0\s*(?:\ub9d0|\ub9c8|\uc54a\uace0)|'
                   r'\uc2e4\ud589\s*\uc5c6\uc774|\uae08\uc9c0)', prohibition))


def files_restricted(owner: dict) -> bool:
    # Keep separate prohibitions separate: a scoped edit ban does not waive a
    # blanket ban elsewhere, and never bans every file-writing tool by itself.
    for clause in re.split(r';|\n|(?<=[.!?])(?:\s+|$)', QUOTED.sub(' ', owner['may_not'])):
        deny = normalized(clause)
        if re.search(r'\b(?:outside|other than|except|beyond|besides|under|in|not listed|only)\b|'
                     r'(?:\uc678|\ubc16|\uc774\uc678|\uc81c\uc678|\ubc94\uc704\s*\ubc16)', deny):
            continue
        if re.search(
            r'\b(?:no (?:file changes|scratch writes)|(?:edit|modify|change|write|create|delete) '
            r'(?:any )?files?|file (?:changes|writes) (?:are )?(?:forbidden|prohibited))\b|'
            r'(?:\ud30c\uc77c|\uc2a4\ud06c\ub798\uce58)[^\n.!?]*'
            r'(?:\uc218\uc815|\ubcc0\uacbd|\ud3b8\uc9d1|\uc4f0\uae30|\uc791\uc131|\uc0dd\uc131|\uc0ad\uc81c)',
            deny):
            return True
    return False


def tool_attempt_rule(owner: dict) -> str:
    # A file-only ban must not read as a command ban: command-permitted packets need the runner.
    rules = [rule for rule, active in (
        (SHELL_TOOL_RULE, restricted('May not: ' + owner['may_not'])),
        (FILE_TOOL_RULE, files_restricted(owner))) if active]
    return ''.join(rule + ATTEMPT_RULE + '\n' for rule in rules)


def namespace_defects(body: str, root: Path) -> list[str]:
    """Read only the local declaration; malformed/missing maps fail open."""
    try:
        data = json.loads((root / '.mir/ontology-map.json').read_text())
        namespace = data.get('namespace')
        if not isinstance(namespace, str) or not namespace:
            return []
        aliases = {entry['namespace'] for entry in data.get('namespace_aliases', [])
                   if isinstance(entry, dict) and entry.get('reviewed') is True
                   and isinstance(entry.get('namespace'), str)
                   and isinstance(entry.get('evidence'), str) and entry['evidence'].strip()}
    except (OSError, ValueError, AttributeError, TypeError):
        return []
    plain = re.sub(r'[*`]', '', body)
    targets = re.findall(r'(?im)^\s*(?:#{1,6}\s+|[-+]\s+)?'
                         + TARGET_NAME + r'\s*:\s*([\w.-]+):[\w./-]+', plain)
    return [f'qualified target namespace {target} differs from map namespace {namespace}'
            for target in dict.fromkeys(targets) if target != namespace and target not in aliases]


def source_paths(owner: dict, root: Path) -> list[str]:
    paths = []
    for raw in re.split(r'[;,\n]', owner['sources']):
        raw = raw.strip().lstrip('-* ').strip().strip('`')
        if not raw:
            continue
        path = (root / raw).resolve()
        relative = path.relative_to(root)
        if any(part.startswith('.env') or part == 'secrets' for part in relative.parts):
            raise ValueError('protected source')
        if relative.as_posix().startswith('.mir/memory.db'):
            raise ValueError('protected source')
        if any(item in raw for item in owner['excluded']):
            raise ValueError('excluded source')
        paths.append(relative.as_posix())
    if len(paths) > 16:
        raise ValueError('too many sources')
    return paths


def repository_root(event: dict) -> Path:
    cwd = Path(event['cwd'])
    if not cwd.is_absolute() or not cwd.is_dir():
        raise ValueError('native cwd unavailable')
    cwd = cwd.resolve()
    for root in (cwd, *cwd.parents):
        if (root / '.git').exists():
            return root
    raise ValueError('repository root unavailable')


def cited_paths(body: str, owner: dict, root: Path) -> list[str]:
    """Repository files the packet names that the supplied pins do not already cover."""
    covered = {*source_paths(owner, root), '.mir/ontology-map.json', 'scripts/mir_ontology.py'}
    denied = set(CITED.findall(owner['may_not']))
    denied.update(CITED.findall(owner_sections(body)['may_not']))
    for line in body.splitlines():
        if re.search(r'\b(?:not[- ]read|did not read|not opened|protected (?:scope|paths?))\b',
                     line, re.I):
            denied.update(CITED.findall(line))
    protected = []
    try:
        if tomllib is None:
            raise OSError('profile parser unavailable')
        with (root / '.mir/repo-profile.toml').open('rb') as stream:
            profile = tomllib.load(stream)
        protected = (profile.get('paths', {}).get('protected_paths', [])
                     + profile.get('paths', {}).get('secret_paths', [])
                     + profile.get('boundaries', {}).get('secrets', []))
        if not isinstance(protected, list) or not all(isinstance(p, str) for p in protected):
            protected = []
    except (OSError, ValueError, TypeError, AttributeError):
        pass  # An absent/unreadable/malformed profile must not break the hook.
    paths = []
    for raw in CITED.findall(body):
        if (raw in covered or raw in denied or raw in paths
                or any(item in raw for item in owner['excluded'])
                or any(fnmatch.fnmatchcase(raw, pattern) for pattern in protected)):
            continue
        parts = Path(raw).parts
        if any(part.startswith('.env') or part in {'secrets', '..'} for part in parts):
            continue
        if raw.startswith('.mir/memory.db'):
            continue
        path = root / raw
        if path.is_symlink() or not path.is_file():
            continue
        paths.append(raw)
    return paths[:32]


def run_pins(event: dict, owner: dict, paths: list[str] | None = None, timeout: float = 5) -> str:
    root = repository_root(event)
    runner = root / 'scripts/mir_ontology.py'
    if runner.is_symlink() or not runner.is_file():
        raise ValueError('repository pin runner unavailable')
    if paths is None:
        paths = source_paths(owner, root)
    process = subprocess.Popen(
        [sys.executable, str(runner), 'mapping', '--handoff', *paths],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'GIT_OPTIONAL_LOCKS': '0'},
    )
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise ValueError('pin runner timed out') from None
    marker = 'handoff pins:\n'
    if process.returncode or marker not in stdout or len(stdout) > LIMIT:
        raise ValueError('pin runner failed')
    pins = marker + stdout.split(marker, 1)[1].rstrip('\n')
    if not isinstance(json.loads(pins[len(marker):]), dict):
        raise ValueError('invalid pins')
    if any(excluded in pins for excluded in owner['excluded']):
        raise ValueError('pins contain excluded data')
    return pins


def supply(event: dict) -> None:
    prompt = event.get('prompt', '')
    if not isinstance(prompt, str):
        raise ValueError('invalid prompt')
    if recipient(prompt):
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit',
                         'additionalContext': RECEIPT_RULE + '\n'
                         + tool_attempt_rule(owner_sections(prompt))}}))
        return
    if not detect(prompt):
        return  # detection only: no filesystem, runner, or output on ordinary prompts
    owner = owner_sections(prompt)
    if restricted(prompt):
        warning('pins/check unavailable: owner forbids commands; '
                'no runner performed. Inventory unavailable pins.', owner)
        return
    pins = run_pins(event, owner)
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit',
                     'additionalContext': context_text(owner, pins, prompt)}}))


def matching_pins(body: str, fresh: str) -> bool:
    """Keep original observation time; all other bytes must match the fresh runner."""
    marker = 'handoff pins:\n'
    header = re.search(r'(?m)^handoff pins:\n', body)
    if not header:
        return False
    raw = body[header.end():]
    try:
        supplied, end = json.JSONDecoder().raw_decode(raw)
        current = json.loads(fresh[len(marker):])
        # Observation time changes on each read. No state can attest its original value.
        stamp = supplied.get('observed_at')
        if not isinstance(stamp, str) or not re.fullmatch(STAMP, stamp):
            return False
        current['observed_at'] = stamp
        return raw[:end] == json.dumps(current, indent=2)
    except (ValueError, AttributeError, TypeError):
        return False


def supplied_json_present(body: str, fresh: str) -> bool:
    current = json.loads(fresh.split('handoff pins:\n', 1)[1])
    for match in re.finditer(r'\{\s*"repository_root"\s*:', body):
        try:
            supplied, _ = json.JSONDecoder().raw_decode(body[match.start():])
            expected = {**current, 'observed_at': supplied.get('observed_at')}
            if supplied == expected:
                return True
        except ValueError:
            continue
    return False


def pin_differences(body: str, fresh: str) -> list[str]:
    """Name changed/missing JSON pointers without echoing potentially private values."""
    marker = 'handoff pins:\n'
    try:
        supplied, _ = json.JSONDecoder().raw_decode(body.split(marker, 1)[1])
        current = json.loads(fresh.split(marker, 1)[1])
    except (ValueError, IndexError):
        return ['entire pin block missing or malformed']

    def changed(expected, actual, pointer):
        if isinstance(expected, dict) and isinstance(actual, dict):
            return [item for key in sorted(expected.keys() | actual.keys())
                    if key != 'observed_at'
                    for item in changed(expected.get(key), actual.get(key), pointer + '/' + key)]
        if isinstance(expected, list) and isinstance(actual, list):
            return [item for index in range(max(len(expected), len(actual)))
                    for item in changed(expected[index] if index < len(expected) else None,
                                        actual[index] if index < len(actual) else None,
                                        pointer + '/' + str(index))]
        return [pointer or '/'] if expected != actual else []

    return changed(current, supplied, '') or ['pin block formatting or /observed_at']


def transcript_records(event: dict) -> list[dict]:
    transcript = Path(event['transcript_path'])
    # Native runtime owns this explicit transcript path; do not scan logs or directories.
    fd = os.open(transcript, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('transcript must be a regular file')
        stream.seek(0, 2)
        start = max(0, stream.tell() - LIMIT)
        stream.seek(start)
        tail = stream.read(LIMIT)
        if start:
            tail = tail.partition(b'\n')[2]  # discard partial record without any extra read
        records = tail.decode('utf-8').splitlines()
    return [json.loads(line) for line in records if line.strip()]


def message_text(message: dict) -> str:
    content = message.get('content', [])
    return content if isinstance(content, str) else '\n'.join(
        item.get('text', '') for item in content
        if item.get('type') in {'text', 'output_text', 'input_text'}
    )


def hook_prompts(row: dict) -> list[tuple[str, str]]:
    """Codex emits two views of the same native feedback, keyed by hook run ID."""
    payload = row.get('payload', {})
    if row.get('type') == 'response_item' and payload.get('role') == 'user':
        match = re.fullmatch(r'\s*<hook_prompt\s+hook_run_id="([^"]+)">'
                             r'([\s\S]*)</hook_prompt>\s*', message_text(payload))
        return [(match[1], match[2])] if match else []
    if (row.get('type') == 'event_msg' and payload.get('type') == 'item_completed'
            and payload.get('item', {}).get('type') == 'HookPrompt'):
        return [(item.get('hookRunId', ''), item.get('text', ''))
                for item in payload['item'].get('fragments', [])]
    return []


def current_turn(event: dict) -> tuple[str, list[dict]]:
    prompt, rows = None, []
    for row in transcript_records(event):
        payload = row.get('payload', {})
        found = None
        if row.get('type') == 'user' and not row.get('isMeta'):
            message = row['message']
            content = message.get('content', [])
            if isinstance(content, str) or any(
                item.get('type') == 'text' for item in content
            ):
                found = message_text(message)
        elif (row.get('type') == 'response_item' and payload.get('role') == 'user'
              and not hook_prompts(row)):
            found = message_text(payload)
        elif row.get('type') == 'event_msg' and payload.get('type') == 'user_message':
            found = payload['message']
        if found is not None:
            prompt, rows = found, []
        rows.append(row)
    if not isinstance(prompt, str):
        raise ValueError('current prompt unavailable within transcript tail')
    return prompt, rows


def transcript_turn(event: dict) -> tuple[str, str]:
    prompt, rows = current_turn(event)
    body = ''
    for row in rows:
        message = (row.get('message', {}) if row.get('type') == 'assistant'
                   else row.get('payload', {}))
        if row.get('type') == 'assistant' or (
            row.get('type') == 'response_item' and message.get('role') == 'assistant'
            and message.get('phase') in {None, 'final_answer'}
        ):
            text = message_text(message)
            if text:
                body = text
    return prompt, body


def tool_calls(rows: list[dict]) -> list[tuple[str, dict]]:
    calls = []
    for row in rows:
        if row.get('type') == 'assistant':
            content = row.get('message', {}).get('content', [])
            if isinstance(content, list):
                calls.extend((item['name'], item.get('input', {})) for item in content
                             if item.get('type') == 'tool_use')
        payload = row.get('payload', {})
        if row.get('type') == 'response_item' and payload.get('type') == 'function_call':
            arguments = payload.get('arguments', {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            calls.append((payload['name'], arguments))
        elif (row.get('type') == 'response_item' and payload.get('type') == 'custom_tool_call'
              and tool_kind(payload.get('name', '')) == 'exec'):
            calls.append((payload['name'], {'input': payload.get('input', '')}))
    for name, arguments in list(calls):
        if tool_kind(name) == 'exec':
            calls.extend(code_shell_calls(arguments.get('input', arguments.get('code', ''))))
    return calls


def code_shell_calls(code: str) -> list[tuple[str, dict]]:
    """Count static nested shell/interpreter calls without evaluating JavaScript.

    Tokenization excludes comments and quoted decoy calls. Dynamic expressions
    still count as calls, but supply no command/computation evidence.
    """
    token_pattern = (r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'
                     r"'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|[\w$]+|[^\s]")
    tokens = [match[0] for match in re.finditer(token_pattern, code)
              if not match[0].startswith(('//', '/*'))]
    calls = []
    for i in range(len(tokens) - 3):
        if not (tokens[i:i + 2] == ['tools', '.'] and tool_kind(tokens[i + 2]) in SHELL_TOOLS
                and tokens[i + 3] == '('):
            continue
        arguments = {}
        calls.append((tokens[i + 2], arguments))
        if tokens[i + 4:i + 5] != ['{']:
            continue
        depth = 1
        for j in range(i + 5, len(tokens) - 3):
            if tokens[j] == '}':
                depth -= 1
            elif tokens[j] == '{':
                depth += 1
            if depth == 0:
                break
            if (depth != 1 or tokens[j].strip('"\'') not in {'cmd', 'command'}
                    or tokens[j + 1] != ':' or tokens[j + 3] not in {',', '}'}):
                continue
            literal = tokens[j + 2]
            if literal[0] not in {'"', "'", '`'} or '${' in literal:
                continue

            def unescape(match):
                value = match[1]
                if value.startswith(('u', 'x')) and len(value) > 1:
                    return chr(int(value[1:], 16))
                return {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
                        'v': '\v', '\n': '', '\r\n': ''}.get(value, value)

            command = re.sub(r'\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|\r?\n|.)',
                             unescape, literal[1:-1])
            arguments['command'] = command
    return calls


def tool_kind(name: str) -> str:
    kind = name.rsplit('.', 1)[-1].lower()
    repl = re.search(r'(?:^|__)(node_repl|python(?:_repl)?|js_repl|javascript_repl)(?:__|$)', kind)
    return repl[1] if repl else kind


def pin_claims(text: str) -> list[tuple[str, str]]:
    plain = re.sub(r'[*`]', '', text)
    claims = re.findall(r'(?im)(?<![\w.-])(?:pin )?([\w.\[\]-]+)\s*[=:]\s*'
                        r'(verified-in-repo|parent-supplied|unavailable)\b', plain)
    for line in plain.splitlines():
        if '|' not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        names = [cell for cell in cells if re.fullmatch(PIN_KEY, cell, re.I)]
        labels = [cell for cell in cells if re.fullmatch(
            r'verified-in-repo|parent-supplied|unavailable', cell, re.I)]
        if len(names) == 1 and len(labels) == 1:
            claims.append((names[0], labels[0]))
    return [(name, label) for name, label in claims if name.lower() not in NON_PIN_NAMES]


def claimed_paths(text: str) -> list[str]:
    """Separate file references from qualified IDs, versions and structured pin keys."""
    plain = re.sub(r'(?<![\w:/])[\w.-]+:[\w./-]+', '', text)
    plain = re.sub(r'(?<![\w./-])' + PIN_KEY + r'(?![\w./-])', '', plain, flags=re.I)
    return [value for value in CITED.findall(plain)
            if not re.fullmatch(r'v?\d+(?:\.\d+)+(?:[-+][\w.-]+)?', value, re.I)]


def received_data(text: str) -> dict:
    marker = RECEIVED_PINS.search(text)
    if marker:
        try:
            data, _ = json.JSONDecoder().raw_decode(text[marker.end():])
            if isinstance(data, dict):
                return data
        except ValueError:
            pass  # A prose pins inventory is also a valid received packet.
    return {}


def pin_paths(text: str, data: dict) -> dict:
    paths = {f'mapping.{key}': data.get('mapping_path', '.mir/ontology-map.json')
             for key in ('identity', 'version', 'digest')}
    contract = data.get('contract_path') or re.search(
        r'contract_path\s*:\s*[`\"]?([^\s`\"]+)', text, re.I)
    if contract:
        path = contract if isinstance(contract, str) else contract[1]
        paths.update({f'contract.{key}': path for key in ('identity', 'version', 'digest')})
    for index, source in enumerate(data.get('sources', [])):
        for key in ('digest', 'revision'):
            paths[f'sources[{index}].{key}'] = source['path']
    return paths


def turn_tools(event: dict) -> tuple[list[tuple[str, dict]], list[str], list[str]]:
    _, rows = current_turn(event)
    calls = [(tool_kind(name), arguments) for name, arguments in tool_calls(rows)]
    reads = [str(arguments.get('file_path', arguments.get('path',
                 arguments.get('pattern', ''))))
             for name, arguments in calls if name in {'read', 'grep', 'glob'}]
    commands = [arguments.get('command', arguments.get('cmd', ''))
                for name, arguments in calls if name in SHELL_TOOLS]
    return calls, reads, commands


def path_referenced(path: str, reads: list[str], commands: list[str], root: Path) -> bool:
    return any(os.path.abspath(root / value) == os.path.abspath(root / path)
               for value in reads if value) or any(path in command for command in commands)


def verification_defects(text: str, body: str, event: dict, no_commands: bool = False) -> list[str]:
    """References establish provenance; typed pin claims additionally need computation."""
    defects = []
    paths = pin_paths(text, received_data(text))
    calls, reads, commands = turn_tools(event)
    root = repository_root(event)
    plain = re.sub(r'[*`]', '', body)
    command_tools = sorted({name for name, _ in calls if name in SHELL_TOOLS})
    if no_commands and command_tools and not any(
        re.search(r'compliance failure|\uc9c0\uc2dc\s*\uc704\ubc18|\uc900\uc218\s*\uc2e4\ud328',
                  line, re.I)
        and re.search(r'interpreter|shell|command|\uc778\ud130\ud504\ub9ac\ud130|\uba85\ub839|'
                      + '|'.join(re.escape(name) for name in command_tools), line, re.I)
        for line in plain.splitlines()
    ):
        defects.append('command-ban compliance failure must be stated for tool calls: '
                       + ', '.join(command_tools))
    verified_paths = set()
    for name, label in pin_claims(plain):
        if label.lower() != 'verified-in-repo':
            continue
        if name == 'repository_root':
            referenced = any(
                os.path.commonpath([str(root), os.path.abspath(root / value)]) == str(root)
                for value in reads if value
            ) or (not no_commands and any(
                str(root) in command or re.search(r'\bmapping\s+--handoff\b', command)
                for command in commands
            ))
            if not referenced:
                defects.append('verified-in-repo pin lacks this-turn tool reference: ' + name)
            continue
        path = paths.get(name)
        line = next((line for line in plain.splitlines() if name in line
                     and 'verified-in-repo' in line.lower()), '')
        # Pin identifiers (mapping.digest etc.) are not file paths.
        explicit = [value for value in claimed_paths(line) if value != name]
        if not path and explicit:
            path = explicit[0]
        if no_commands:
            pin_reads = reads
            if name == 'head':
                path = '.git/HEAD'
                pin_reads = [str(args.get('file_path', args.get('path', '')))
                             for tool, args in calls if tool == 'read']
            if not path or not path_referenced(path, pin_reads, [], root):
                defects.append('verified-in-repo pin lacks this-turn tool reference: ' + name)
            continue
        typed = name == 'head' or name.endswith(('.digest', '.revision', '.sha256'))
        computed = False
        for command in commands:
            runner = bool(re.search(r'\bmapping\s+--handoff\b', command))
            referenced = bool(path and path in command)
            if runner and (name in BASE_PINS or referenced):
                computed = True
            elif name == 'head' and re.search(r'\bgit\s+rev-parse\b', command):
                computed = True
            elif referenced and name.endswith('.revision') and re.search(
                r'\bgit\s+(?:log|rev-list)\b', command
            ):
                computed = True
            elif referenced and name.endswith(('.digest', '.sha256')) and re.search(
                r'\bsha256sum\b|\bshasum\s+[^\n;|]*?(?:-a\s*256|--algorithm[= ]256)\b|'
                r'\bopenssl\s+dgst\s+[^\n;|]*?-sha256\b|\bhashlib\.sha256\s*\(', command
            ):
                computed = True
        if typed and not computed:
            defects.append('verified-in-repo pin lacks this-turn computation: ' + name)
        elif not typed and path:
            verified_paths.add(path)
    names = {name for name, _ in pin_claims(plain)}
    for line in plain.splitlines():
        if 'verified-in-repo' in line.lower():
            verified_paths.update(value for value in claimed_paths(line) if value not in names)
    for path in sorted(verified_paths):
        referenced = path_referenced(path, reads, [] if no_commands else commands, root)
        if not no_commands and path == '.mir/ontology-map.json':
            referenced = referenced or any('mapping --handoff' in command for command in commands)
        if not referenced:
            defects.append('verified-in-repo path lacks this-turn tool reference: ' + path)
    return defects


def abbreviated_hex(body: str) -> list[str]:
    defects = []
    plain = re.sub(r'[*`\"#]', '', body)
    pattern = (r'(?i)(?<![\w.])([\w.\[\]-]*(?:head|revision|commit|digest|sha256))'
               r'\s*(?:[:=@]|is)?\s*([0-9a-f]{7,39})(?![\w])|'
               r'([\w./-]+)@([0-9a-f]{7,39})(?![\w])')
    columns = []
    for line in plain.splitlines():
        for match in re.finditer(pattern, line):
            name = match[1] or match[3]
            inventoried = re.search(rf'(?i)(?<![\w.])(?:pin )?{re.escape(name)}\s*[=:]\s*'
                                    r'abbreviated\b', plain)
            if not re.search(r'\babbreviated\b', line, re.I) and not inventoried:
                defects.append('abbreviated hex value: ' + name)
        if '|' not in line:
            columns = []
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if any(re.search(r'head|revision|commit|digest|sha256', cell, re.I) for cell in cells):
            columns = [i for i, cell in enumerate(cells)
                       if re.search(r'head|revision|commit|digest|sha256', cell, re.I)]
        elif not re.search(r'\babbreviated\b', line, re.I):
            for i in columns:
                if i < len(cells) and re.fullmatch(r'[0-9a-f]{7,39}', cells[i], re.I):
                    defects.append('abbreviated hex value in pins table')
    return defects


def no_command_check(prompt: str, body: str, event: dict) -> list[str]:
    return (authority_defects(body, owner_sections(prompt)) + abbreviated_hex(body)
            + verification_defects(body, body, event, no_commands=True)
            + namespace_defects(body, repository_root(event)))


def recipient_check(prompt: str, body: str, event: dict) -> list[str]:
    """Check declared accounting and tool references, never attest pin bytes."""
    defects = namespace_defects(body, repository_root(event))
    data = received_data(prompt)
    names = list(BASE_PINS)
    names.extend(entry['pin'] for entry in data.get('pin_inventory', []))
    for index, _ in enumerate(data.get('sources', [])):
        names.extend([f'sources[{index}].digest', f'sources[{index}].revision'])
    names.extend(name for name, _ in pin_claims(prompt))
    names.extend(name for name in re.findall(r'(?i)\bpin\s+([\w.\[\]-]+)\s*[=:]', prompt)
                 if name.lower() not in NON_PIN_NAMES)
    if not data:
        for line in prompt.splitlines():
            name = re.match(r'^\s*(?:[-*]\s*)?`?([\w./\[\]-]+)`?\s*:', line)
            if (name and name[1].lower() not in NON_PIN_NAMES
                    and re.search(r'sha256[^\n]*[0-9a-f]{64}', line, re.I)):
                names.append(name[1])
    labels = {name: label.lower() for name, label in pin_claims(body)}
    for name in dict.fromkeys(names):
        if name not in labels:
            defects.append('missing recipient pin label: ' + name)
    defects.extend(verification_defects(prompt, body, event, no_commands=restricted(prompt)))
    plain = re.sub(r'[*`]', '', body)
    calls, reads, _ = turn_tools(event)
    if not restricted(prompt) and not calls and not re.search(
        r'no (?:local (?:check|verification)|(?:local )?tools?)[^\n]*|'
        r'(?:not|could not|unable to) verif[^\n]*locally|'
        r'(?:\ub85c\uceec|\ub3c4\uad6c)[^\n]*(?:\uc54a|\ubabb|\uc5c6|\uc548|\ud558\uc9c0)',
        plain, re.I
    ):
        defects.append('no local check and no stated limitation')
    if (restricted(prompt) and not any(reads)
            and not any(name in SHELL_TOOLS for name, _ in calls) and not (
        (re.search(r'commands?[^\n]*(?:forbidden|prohibited|not (?:run|allowed))', plain, re.I)
         and re.search(r'no (?:non-command )?reader[^\n]*(?:used|available)', plain, re.I))
        or (re.search(r'\uba85\ub839[^\n]*(?:\uae08\uc9c0|\uc2e4\ud589\ud558\uc9c0)', plain)
            and re.search(r'(?:\uc77d\uae30\s*\ub3c4\uad6c|\ub9ac\ub354)'
                          r'[^\n]*(?:\uc5c6|\uc0ac\uc6a9\ud558\uc9c0|\ubabb)', plain))
    )):
        defects.append('state commands forbidden and no non-command reader was used/available')
    return defects


def pretool(event: dict) -> None:
    tool = tool_kind(event['tool_name'])
    command = tool in SHELL_TOOLS
    if tool == 'exec':
        arguments = event.get('tool_input', {})
        code = (arguments if isinstance(arguments, str)
                else arguments.get('input', arguments.get('code', '')))
        command = bool(code_shell_calls(code))
    if not command and tool not in WRITE_TOOLS:
        return
    prompt = event.get('prompt')
    if not isinstance(prompt, str) or not prompt:
        prompt, _ = transcript_turn(event)
    if not (detect(prompt) or recipient(prompt)):
        return
    reason = None
    if command and restricted(prompt):
        reason = 'Owner forbids commands in this handoff turn; shell/interpreter tool denied.'
    elif tool in WRITE_TOOLS and files_restricted(owner_sections(prompt)):
        reason = 'Owner forbids file changes in this handoff turn; file-writing tool denied.'
    if reason:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                          'permissionDecision': 'deny', 'permissionDecisionReason': reason}}))
        print(reason, file=sys.stderr)
        raise SystemExit(2)  # Both CLI shell hooks honour exit 2; Claude also consumes deny JSON.


def prior_blocks(event: dict) -> int | None:
    """Count only this handler's native feedback, never assistant-quoted decisions."""
    _, rows = current_turn(event)
    count = 0
    seen = set()
    for row in rows:
        for run_id, text in hook_prompts(row):
            if (run_id.lower().startswith('stop:') and run_id not in seen
                    and re.match(r'Repair (?:handoff once|recipient accounting once|'
                                 r'handoff deterministic defects \(second/final block\)):', text)):
                seen.add(run_id)
                count += 1
        payload = row.get('payload', {})
        record = row if row.get('type') == 'system' else payload
        feedback = (row.get('type') == 'system' and row.get('subtype') == 'hook_response'
                    or row.get('type') == 'event_msg' and payload.get('type') == 'hook_response')
        meta = row.get('type') == 'user' and row.get('isMeta')
        if not feedback and not meta:
            continue
        text = (message_text(row.get('message', {})) if meta else
                str(record.get('stdout', record.get('output', ''))))
        if re.search(r'Repair (?:handoff once|recipient accounting once|'
                     r'handoff deterministic defects \(second/final block\)):', text):
            if feedback and record.get('hookName', record.get('hook_name', '')) != 'Stop':
                continue
            count += 1
    return count or None


def deterministic(defects: list[str]) -> list[str]:
    return [defect for defect in defects if defect.startswith((
        'missing cited-source pins', 'abbreviated hex', 'missing recipient pin label',
        'excluded item #', 'qualified target namespace ', 'command-ban compliance failure'))]


def block(defects: list[str], retry: bool, receiving: bool, owner: dict) -> None:
    if retry:
        defects = deterministic(defects)
    for index, value in enumerate(owner['excluded'], 1):
        defects = [defect.replace(value, f'[excluded item #{index}]') for defect in defects]
    if defects:
        prefix = ('Repair handoff deterministic defects (second/final block): ' if retry else
                  'Repair recipient accounting once: ' if receiving else 'Repair handoff once: ')
        print(json.dumps({'decision': 'block', 'reason': prefix + '; '.join(defects)
                          + '. ' + COMPLETE_ARTIFACT_RULE}))


def stop(event: dict) -> None:
    prompt, body = transcript_turn(event)
    # The transcript can lag behind the turn's final message; the native payload carries it.
    native = event.get('last_assistant_message')
    if isinstance(native, str) and native.strip():
        body = native
    receiving = recipient(prompt)
    if not detect(prompt) and not receiving:
        return
    if not receiving and not PACKET.search(body) and not recipient(body):
        return  # no emitted packet, e.g. a clarification
    if not isinstance(event.get('stop_hook_active'), bool):
        warning('native retry guard unavailable; packet check skipped to prevent a loop.')
        return
    retry = event['stop_hook_active']
    previous = prior_blocks(event)
    if (previous is not None and previous >= 2) or (retry and previous != 1):
        warning('repair already requested; allowing stop without another block.')
        return
    owner = owner_sections(prompt)
    if receiving:
        defects = recipient_check(prompt, body, event) + abbreviated_hex(body)
        defects.extend(authority_defects(body, owner))
        block(defects, retry, True, owner)
        return
    if restricted(prompt):
        message = 'pins/check unavailable: owner forbids commands; no runner performed.'
        print(WARNING + message, file=sys.stderr)
        defects = no_command_check(prompt, body, event)
        selected = deterministic(defects) if retry else defects
        if selected:
            block(selected, retry, False, owner)
        else:
            print(json.dumps({'systemMessage': WARNING + message}))
        return
    guard = re.search(r'(?im)^Prompt SHA256: ([0-9a-f]{64})\s*$', body)
    if guard and guard[1] != hashlib.sha256(prompt.encode()).hexdigest():
        warning('current prompt hash changed; packet check skipped to avoid stale authority.')
        return
    pins = run_pins(event, owner)
    defects = check_packet(body, {'pins': pins, 'owner': owner,
                                 'root': repository_root(event)}) + abbreviated_hex(body)
    # Every cited repository file needs its own digest and last-change revision.
    cited = cited_paths(body, owner, repository_root(event))
    if cited:
        # Both runner calls share the 8-second host budget; a late second call fails open.
        budget = max(0.5, 6.5 - (time.monotonic() - STARTED))
        found = json.loads(run_pins(event, owner, cited, budget).split('handoff pins:\n', 1)[1])
        unpinned = [source['path'] for source in found.get('sources', [])
                    if source.get('sha256') and (
                        source['sha256'] not in body
                        or (re.fullmatch(r'[0-9a-f]{40}', source.get('revision') or '')
                            and source['revision'] not in body))]
        if unpinned:
            defects.append('missing cited-source pins (add sha256 and last-change revision for '
                           'each from `python3 scripts/mir_ontology.py mapping --handoff <paths>` '
                           'sources; no second pins block): ' + ', '.join(unpinned))
    if not guard:
        defects.append('missing Prompt SHA256 (copy the supplied full prompt hash)')
    block(defects, retry, False, owner)


def main() -> None:
    event = None
    try:
        raw = sys.stdin.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError('oversized hook payload')
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError('invalid hook payload')
        if event.get('hook_event_name') == 'UserPromptSubmit':
            supply(event)
        elif event.get('hook_event_name') == 'Stop':
            stop(event)
        elif event.get('hook_event_name') == 'PreToolUse':
            pretool(event)
    except Exception:
        if isinstance(event, dict) and event.get('hook_event_name') == 'PreToolUse':
            return  # fail open silently: the guard runs on every shell call
        owner = None
        if (isinstance(event, dict) and event.get('hook_event_name') == 'UserPromptSubmit'
                and isinstance(event.get('prompt'), str) and detect(event['prompt'])):
            owner = owner_sections(event['prompt'])
        warning('hook unavailable; allowing turn to continue. Check native payload, '
                'explicit transcript tail and repository runner; pins/check unavailable.', owner)


if __name__ == '__main__':
    main()
