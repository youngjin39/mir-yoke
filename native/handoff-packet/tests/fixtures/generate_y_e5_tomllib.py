"""Freeze Python 3.12 tomllib diagnostics; invoke with -I and explicit output."""
import argparse
import json
import sys
import sysconfig
import tomllib
from pathlib import Path

assert sys.flags.isolated and sys.version_info[:2] == (3, 12)
assert Path(tomllib.__file__).resolve().is_relative_to(Path(sysconfig.get_path('stdlib')).resolve())
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
cases = []
for prefix in ('a=', 'bad = ', '[table]\na=', 'unicode="한글"\na=', 'a=[['):
    for content in ('[', '[1', '[1,', '[1,2', '[true', '[true,', '[[]', '[[],',
                    '["x"', '["x",', '[{a=1}', '[{a=1},', '[#comment', '[1 #comment',
                    '[,', '[1,,', '[1 ', '[\n', '[\r\n', '[\v', '[\u001c',
                    '["#,["', "['#,['", '["""\n#,["""', "['''\n#,['''",
                    '["escaped\\\"#"', '["#",'):
        for tail in ('', ' ', '\t', '\n', '\r\n', '# eof', '\n# eof\n'):
            text = prefix + content + tail
            try:
                tomllib.loads(text)
            except tomllib.TOMLDecodeError as exc:
                cases.append({'text': text, 'error': str(exc)})
# Six quotes leave an extra quote after the maximum five-quote terminator.
for quote in ('"', "'"):
    for count in (3, 4, 5, 6):
        value = quote * 3 + 'x' + quote * count
        for prefix, tails in (('a=[', (']', ',', ', ', ',# eof', ',\n# eof\n')),
                              ('a={b=', ('}', ', c=1}', ',')),
                              ('a=', ('', '\n'))):
            for tail in tails:
                text = prefix + value + tail
                record = {'text': text, 'closing_quotes': count, 'quote': quote}
                try:
                    record['value'] = tomllib.loads(text)
                except tomllib.TOMLDecodeError as exc:
                    record['error'] = str(exc)
                cases.append(record)
a.output.write_text(json.dumps(cases, ensure_ascii=True, indent=2) + '\n')
