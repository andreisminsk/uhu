#!/usr/bin/env python3
"""Format news JSON output into a readable summary."""
import json, re, html, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Read from stdin or file argument
if len(sys.argv) > 1:
    with open(sys.argv[1], encoding='utf-8') as f:
        d = json.load(f)
else:
    d = json.load(sys.stdin)

for cat, info in d['categories'].items():
    emoji = info['emoji']
    print(f'\n{emoji} {cat.upper()} ({info["count"]} headlines)')
    print('=' * 50)
    for h in info['headlines'][:10]:
        desc = re.sub(r'<[^>]+>', '', (h.get('description') or '')[:150])
        desc = html.unescape(desc).encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace').strip()
        title = h.get('title', 'No title').encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace')
        source = h.get('source', 'Unknown').encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace')
        link = h.get('link', '')
        print(f'  • {title}')
        if desc:
            print(f'    {desc}...')
        print(f'    [{source}] [→]({link})')
        print()
