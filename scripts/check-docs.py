#!/usr/bin/env python3
"""Check local Markdown links, heading anchors and fenced blocks without network access."""
import argparse
from pathlib import Path
import re
import sys
import subprocess
import unicodedata
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def markdown_lines(text):
    """Yield non-code lines; support backtick and tilde fenced blocks."""
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            run = marker[1]
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not line[marker.end():].strip():
                fence = None
            continue
        if fence is None:
            yield number, line
    if fence is not None:
        raise ValueError('unclosed fenced code block')


def heading_anchors(text):
    counts, anchors = {}, set()
    for _, line in markdown_lines(text):
        match = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line)
        if not match:
            continue
        title = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', match[1]).lower()
        title = title.replace('`', '').replace('*', '')
        slug = ''.join(c for c in title if c in '-_' or not unicodedata.category(c).startswith(('P', 'S')))
        slug = slug.replace(' ', '-')
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(slug if count == 0 else f'{slug}-{count}')
    return anchors


def check(root):
    root = Path(root).resolve()
    errors = []
    paths = sorted(p for p in root.rglob('*.md') if not any(part in {'.git', 'secrets', 'generated'} for part in p.relative_to(root).parts))
    for path in paths:
        try:
            lines = list(markdown_lines(path.read_text()))
        except ValueError as error:
            errors.append(f'{path.relative_to(root)}: {error}')
            continue
        text = path.read_text()
        for block in re.finditer(r'^```bash\n(.*?)^```\s*$', text, re.M | re.S):
            result = subprocess.run(['bash', '--noprofile', '--norc', '-n'],
                                    input=block[1], text=True, capture_output=True)
            if result.returncode:
                number = text[:block.start()].count('\n') + 1
                errors.append(f'{path.relative_to(root)}:{number}: Bash syntax: {result.stderr.strip()}')
        for number, line in lines:
            # Repository docs use inline links; skip inline code examples.
            line = re.sub(r'`[^`]*`', '', line)
            for match in re.finditer(r'\[[^]]*\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)', line):
                url = match[1].strip('<>')
                parsed = urlsplit(url)
                if parsed.scheme or parsed.netloc:
                    continue
                target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
                prefix = f'{path.relative_to(root)}:{number}: {url}'
                if not target.is_relative_to(root):
                    errors.append(f'{prefix}: outside repository')
                elif not target.exists():
                    errors.append(f'{prefix}: missing target')
                elif parsed.fragment and target.suffix == '.md':
                    try:
                        if unquote(parsed.fragment) not in heading_anchors(target.read_text()):
                            errors.append(f'{prefix}: missing heading anchor')
                    except ValueError as error:
                        errors.append(f'{prefix}: {error}')
    return paths, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    paths, errors = check(args.root)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'Checked {len(paths)} Markdown files: local links, heading anchors, fences and Bash syntax are valid')
    return 0


if __name__ == '__main__':
    sys.exit(main())
