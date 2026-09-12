#!/usr/bin/env python3
"""Refresh linked contents and render the specification PDF.

Install tools/requirements-render.txt and run `python -m playwright install chromium`
once, then run `python tools/render_spec.py` from any directory.
"""
import base64
import html
import re
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'vessel-logon-spec.md'
START, END = '<!-- contents:start -->', '<!-- contents:end -->'


def source_with_contents(source):
    # Explicit anchors make Markdown and PDF navigation agree across renderers.
    source = re.sub(r'<a id="section-[^"]+"></a>\n\n', '', source)
    source = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n*', '', source, flags=re.S)
    entries = []
    def heading(match):
        level, title = match.groups()
        anchor = 'section-' + slugify(title, '-')
        entries.append(('    ' if len(level) == 3 else '') + f'- [{title}](#{anchor})')
        return f'<a id="{anchor}"></a>\n\n{level} {title}'
    source = re.sub(r'^(#{2,3}) (.+)$', heading, source, flags=re.M)
    contents = START + '\n## Table of contents\n\n' + '\n'.join(entries) + '\n' + END + '\n\n'
    pos = source.index('---')
    return source[:pos] + contents + source[pos:]


def main():
    source = source_with_contents(SOURCE.read_text())
    SOURCE.write_text(source)
    body = markdown.markdown(source, extensions=['tables', 'fenced_code'])
    def table_style(match):
        table = match.group(0)
        classes = []
        if '<th>#</th>' in table:
            classes.append('acceptance')
        if table.count('<tr>') <= 7:
            classes.append('compact')
        return table.replace('<table>', '<table class="' + ' '.join(classes) + '">', 1)
    body = re.sub(r'<table>.*?</table>', table_style, body, flags=re.S)
    def embed(match):
        path = ROOT / html.unescape(match.group(1))
        return 'src="data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode() + '"'
    body = re.sub(r'src="(figures/[^"]+)"', embed, body)
    body = re.sub(r'<p>(<img alt="([^"]*)"[^>]+>)</p>', r'<figure>\1<figcaption>\2</figcaption></figure>', body)
    # Keep contents and evidence figures in dedicated print sections.
    begin = body.index(START)
    end = body.index(END) + len(END)
    body = body[:begin] + '<nav class="contents">' + body[begin:end] + '</nav>' + body[end:]
    version = re.search(r'\*\*Version:\*\* ([\d.]+)', source).group(1)
    title = f'Vessel Log On — Functional Specification v{version}'
    doc = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>''' + html.escape(title) + '''</title><style>
    @page { size: A4; margin: 17mm 16mm 19mm; }
    body { font-family: Arial, sans-serif; color: #23313c; font-size: 10pt; line-height: 1.43; }
    h1 { font-size: 25pt; line-height: 1.16; color: #143e54; margin: 0 0 16px; }
    h2 { font-size: 16pt; line-height: 1.2; color: #143e54; margin: 22px 0 10px; border-bottom: 1px solid #bbced8; padding-bottom: 5px; }
    h3 { font-size: 12pt; color: #1d536a; margin-top: 18px; }
    h1,h2,h3 { break-after: avoid; }
    p { margin: 9px 0; orphans: 3; widows: 3; }
    li { margin: 5px 0; }
    a { color: #145d83; text-decoration: underline; overflow-wrap: anywhere; }
    a[id] { display: block; break-after: avoid; }
    blockquote { margin: 15px 0; padding: 8px 15px; border-left: 3px solid #23657f; background: #f0f5f7; }
    table { width: 100%; border-collapse: collapse; font-size: 9pt; line-height: 1.35; margin: 12px 0; }
    thead { display: table-header-group; }
    table.compact { break-inside: avoid; }
    table.acceptance td:first-child, table.acceptance th:first-child { white-space: nowrap; width: 12mm; }
    tr { break-inside: avoid; }
    th,td { border: 1px solid #c5d1d8; padding: 6px; text-align: left; vertical-align: top; }
    th { background: #eef3f6; }
    code,pre { font-size: 8.5pt; }
    pre { white-space: pre-wrap; background: #eef3f6; padding: 10px; }
    hr { border: 0; border-top: 1px solid #dde5ea; margin: 18px 0; }
    figure { margin: 14px 0; text-align: center; break-inside: avoid; }
    figure img { max-width: 100%; max-height: 175mm; object-fit: contain; }
    figcaption { font-size: 9pt; color: #526875; margin-top: 6px; }
    .contents { break-after: page; }
    .contents > ul { columns: 2; column-gap: 20px; font-size: 9pt; padding-left: 16px; }
    .contents li { margin: 4px 0; break-inside: avoid; }
    .contents ul ul { padding-left: 13px; }
    a[id^="section-figure-"] { break-before: page; }
    a[id="section-appendix-f-evidence-figures"] { break-before: page; }
    a[id="section-figure-1-active-log-on-list"] { break-before: auto; }
    </style></head><body>''' + body + '</body></html>'
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(doc, wait_until='load')
        page.evaluate('document.fonts.ready')
        assert page.locator('img').count() == 4, 'Expected all four evidence figures'
        assert page.evaluate('Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)')
        assert page.evaluate('Array.from(document.querySelectorAll(\'a[href^="#"]\')).every(a => document.getElementById(a.hash.slice(1)))'), 'Broken contents link'
        page.pdf(path=str(ROOT / 'vessel-logon-spec.pdf'), format='A4', print_background=True,
                 display_header_footer=True, header_template='<span></span>',
                 footer_template=f'<div style="font-family:Arial;font-size:8px;color:#64748b;width:100%;text-align:center;">Vessel Log On · v{version} draft · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        browser.close()
    print(f'Rendered {ROOT / "vessel-logon-spec.pdf"}; contents links and 4 images verified.')


if __name__ == '__main__':
    main()
