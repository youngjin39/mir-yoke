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
SHELL_TOOLS = {'bash', 'shell', 'shell_command', 'exec_command'}
RECEIVED_PINS = re.compile(r'\b(?:handoff )?pins:\s*(?:```(?:json)?\s*)?', re.I)
RECEIPT_RULE = (
    'Received handoff: label every pin verified-in-repo, parent-supplied or unavailable; '
    'every path claimed verified-in-repo needs a Read or shell reference in this turn, '
    'and if commands are forbidden and no reader was used, state that limitation.'
)


def recipient(prompt: str) -> bool:
    """A supplied qualified packet with pins, excluding requests to author one."""
    plain = re.sub(r'[*`]', '', prompt)
    return not detect(prompt) and bool(
        re.search(r'qualified target\s*:\s*[\w.-]+:[\w./-]+', plain, re.I)
        and re.search(r'handoff pins:|\bpins\s*:|sha256[^\n]*[0-9a-f]{64}', plain, re.I))


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
    for line in prompt.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            active = None
            continue
        if fenced or line.lstrip().startswith('>'):
            continue
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
        'excluded': [item.strip().strip('`') for line in values['excluded']
                     for item in re.split(r';|\n', line) if item.strip()],
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


def check_packet(body: str, state: dict) -> list[str]:
    """Conservative format/lexical checks, never a semantic permission decision."""
    defects = []
    pins = state['pins']
    if body.count('handoff pins:') > 1:
        defects.append('duplicate supplied pins blocks')
    if not matching_pins(body, pins):
        differences = pin_differences(body, pins)
        defects.append('missing/changed supplied pins (copy the entire supplied block unchanged): '
                       + ', '.join(differences))
    # Inspect the entire enclosing artifact, not only a fenced packet or its first section.
    for index, excluded in enumerate(state['owner']['excluded'], 1):
        if excluded in body:
            defects.append(f'excluded item #{index} appears in forwarded artifact')
    plain = re.sub(r'(?m)^[ \t]*[-+][ \t]+', '',
                   re.sub(r'[*`#]', '', body.replace(pins, '')))
    if not re.search(r'(?im)^\s*qualified target:\s*[\w.-]+:[\w./-]+', plain):
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
    grant = ' ; '.join(normalized(item) for item in items(state['owner']['may']))
    denied = [normalized(item) for item in items(state['owner']['may_not'])]
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
                     if state['owner'].get('explicit_authority', True)
                     else bool(READ.search(item)) and not ACTION.search(item))
        permitted = permitted or (bool(READ.search(item)) and not ACTION.search(item))
        if (not candidate or not permitted
                or any(deny and f' {deny} ' in f' {candidate} ' for deny in denied)):
            defects.append('extra may: ' + item)
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
        'Inspect the whole forwarded artifact, including enclosing text.\n'
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
    deny = normalized(owner['may_not'])
    return bool(re.search(
        r'\b(?:run|execute) (?:any )?(?:commands|shell|python)\b', deny
    ) or re.search(
        r'\b(?:no commands|commands (?:are )?(?:forbidden|prohibited)'
        r'|do not (?:run|execute) (?:any )?commands)\b',
        prompt.casefold(),
    ) or re.search(r'(?:\uba85\ub839|\ucee4\ub9e8\ub4dc|\uc250|\ud30c\uc774\uc36c)'
                   r'[^\n.!?]*(?:\uc9c0\s*(?:\ub9d0|\ub9c8|\uc54a\uace0)|'
                   r'\uc2e4\ud589\s*\uc5c6\uc774|\uae08\uc9c0)', owner['may_not']))


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
                         'additionalContext': RECEIPT_RULE}}))
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
    if marker not in body:
        return False
    raw = body.split(marker, 1)[1]
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
        elif row.get('type') == 'response_item' and payload.get('role') == 'user':
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
    return calls


def tool_kind(name: str) -> str:
    return name.rsplit('.', 1)[-1].lower()


def recipient_check(prompt: str, body: str, event: dict) -> list[str]:
    """Check declared accounting and tool references, never attest pin bytes."""
    defects = []
    paths = {'mapping.digest': '.mir/ontology-map.json',
             'mapping.version': '.mir/ontology-map.json',
             'mapping.identity': '.mir/ontology-map.json'}
    marker = RECEIVED_PINS.search(prompt)
    if marker:
        data, _ = json.JSONDecoder().raw_decode(prompt[marker.end():])
        names = [entry['pin'] for entry in data.get('pin_inventory', [])]
        if not names:
            names = ['repository_root', 'head', 'mapping.identity', 'mapping.version',
                     'mapping.digest', 'contract.identity', 'contract.version', 'contract.digest']
            for index, _source in enumerate(data.get('sources', [])):
                names.extend([f'sources[{index}].digest', f'sources[{index}].revision'])
        for index, source in enumerate(data.get('sources', [])):
            for key in ('digest', 'revision'):
                paths[f'sources[{index}].{key}'] = source['path']
    else:
        names = [line.split(':', 1)[0].strip(' -*`') for line in prompt.splitlines()
                 if re.search(r'sha256[^\n]*[0-9a-f]{64}', line, re.I)]
    plain = re.sub(r'[*`]', '', body)
    verified_paths = set()
    for name in names:
        match = re.search(rf'(?im)(?<![\w.-])(?:pin )?{re.escape(name)}\s*[=:]\s*'
                          r'(verified-in-repo|parent-supplied|unavailable)\b', plain)
        if not match:
            defects.append('missing recipient pin label: ' + name)
        elif match[1].lower() == 'verified-in-repo' and name in paths:
            # Inferred source paths also count when only a pin name appears in the answer.
            verified_paths.add(paths[name])
    _, rows = current_turn(event)
    calls = [(tool_kind(name), arguments) for name, arguments in tool_calls(rows)]
    reads = [str(arguments.get('file_path', arguments.get('path', '')))
             for name, arguments in calls if name == 'read']
    commands = [arguments.get('command', arguments.get('cmd', ''))
                for name, arguments in calls if name in SHELL_TOOLS]
    root = repository_root(event)
    for line in plain.splitlines():
        if 'verified-in-repo' in line.lower():
            verified_paths.update(CITED.findall(line))
    for path in sorted(verified_paths):
        referenced = any(os.path.abspath(root / value) == os.path.abspath(root / path)
                         for value in reads if value)
        referenced = referenced or any(path in command for command in commands)
        if path == '.mir/ontology-map.json':
            referenced = referenced or any('mapping --handoff' in command for command in commands)
        if not referenced:
            defects.append('verified-in-repo path lacks this-turn tool reference: ' + path)
    if restricted(prompt) and not any(reads) and not (
        (re.search(r'commands?[^\n]*(?:forbidden|prohibited|not (?:run|allowed))', plain, re.I)
         and re.search(r'no (?:non-command )?reader[^\n]*(?:used|available)', plain, re.I))
        or (re.search(r'\uba85\ub839[^\n]*(?:\uae08\uc9c0|\uc2e4\ud589\ud558\uc9c0)', plain)
            and re.search(r'(?:\uc77d\uae30\s*\ub3c4\uad6c|\ub9ac\ub354)'
                          r'[^\n]*(?:\uc5c6|\uc0ac\uc6a9\ud558\uc9c0|\ubabb)', plain))
    ):
        defects.append('state commands forbidden and no non-command reader was used/available')
    return defects


def pretool(event: dict) -> None:
    if tool_kind(event['tool_name']) not in SHELL_TOOLS:
        return
    prompt = event.get('prompt')
    if not isinstance(prompt, str) or not prompt:
        prompt, _ = transcript_turn(event)
    if (detect(prompt) or recipient(prompt)) and restricted(prompt):
        reason = 'Owner forbids commands in this handoff turn; shell tool denied.'
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                          'permissionDecision': 'deny', 'permissionDecisionReason': reason}}))
        print(reason, file=sys.stderr)
        raise SystemExit(2)  # Both CLI shell hooks honour exit 2; Claude also consumes deny JSON.


def stop(event: dict) -> None:
    prompt, body = transcript_turn(event)
    # The transcript can lag behind the turn's final message; the native payload carries it.
    native = event.get('last_assistant_message')
    if isinstance(native, str) and native.strip():
        body = native
    receiving = recipient(prompt)
    if not detect(prompt) and not receiving:
        return
    if not receiving and not PACKET.search(body):
        return  # no emitted packet, e.g. a clarification
    if not isinstance(event.get('stop_hook_active'), bool):
        warning('native retry guard unavailable; packet check skipped to prevent a loop.')
        return
    if event['stop_hook_active']:
        warning('repair already requested; allowing stop without another block.')
        return
    if receiving:
        defects = recipient_check(prompt, body, event)
        if defects:
            print(json.dumps({'decision': 'block',
                              'reason': 'Repair recipient accounting once: ' + '; '.join(defects)}))
        return
    guard = re.search(r'(?im)^Prompt SHA256: ([0-9a-f]{64})\s*$', body)
    if guard and guard[1] != hashlib.sha256(prompt.encode()).hexdigest():
        warning('current prompt hash changed; packet check skipped to avoid stale authority.')
        return
    if restricted(prompt):
        warning('pins/check unavailable: owner forbids commands; no runner performed.')
        return
    owner = owner_sections(prompt)
    pins = run_pins(event, owner)
    defects = check_packet(body, {'pins': pins, 'owner': owner})
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
    if defects:
        print(json.dumps({'decision': 'block',
                          'reason': 'Repair handoff once: ' + '; '.join(defects)}))


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
