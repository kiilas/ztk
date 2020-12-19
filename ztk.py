#!/bin/env python3

import getopt
import os
import pathlib
import re
import subprocess
import sys

HELP = 'Sorry, no help yet. :('

TAG_REGEX = '(?<!\S)#([a-zA-Z0-9\-]+)'

class Rete:
    def __init__(self, nodes, title=None, style=None):
        self.nodes = nodes
        self.title = title
        self.style = style
        self.tags = self._generate_tags()
        self.top_node = self._infer_top_node()

    def export_as_website(self, out_dir):
        out_path = pathlib.Path(out_dir)
        if self.nodes:
            for name, node in self.nodes.items():
                self._export_html(node.markdown(),
                                  root=out_path,
                                  path=pathlib.Path(f'node/{name}.html'),
                                  title=f'{node.title}')
            self._export_html(self.all_nodes(),
                              root=out_path,
                              path=pathlib.Path('all.html'),
                              title='All nodes')
        if self.tags:
            for tag in self.tags:
                self._export_html(self.tag(tag),
                                  root=out_path,
                                  path=pathlib.Path(f'tag/{tag}.html'),
                                  title=f'#{tag}')
            self._export_html(self.tag_index(),
                              root=out_path,
                              path=pathlib.Path('tags.html'),
                              title='Tag index')
        self._export_html(self.top(),
                          root=out_path,
                          path=pathlib.Path('index.html'))
        if self.style:
            (out_path / 'style').mkdir(exist_ok=True)
            style_path = out_path / 'style' / 'style.css'
            style_path.write_text(self.style)

    def top(self):
        if self.top_node is None:
            return self.all_nodes()
        return self.top_node.markdown()

    def tag(self, tag):
        nodes = map(self.nodes.get, sorted(self.tags[tag], reverse=True))
        return node_list(nodes, f'#{tag}')

    def tag_index(self):
        def freq_sort_key(item):
            tag, freq = item
            # sort by frequency first, then by newest node in the tag
            return freq, max(self.tags[tag])

        alphabetical = ' '.join(['#' + tag for tag in sorted(self.tags)])
        freqs = {tag: len(self.tags[tag]) for tag in self.tags}
        freqs_sorted = sorted(freqs.items(), key=freq_sort_key, reverse=True)
        by_freq = ' '.join([f'#{tag}<small>({freq})</small>'
                            for tag, freq in freqs_sorted])

        return (f'# Tag index\n\n'
                f'*(generated automatically)*\n\n'
                f'## Alphabetically\n\n'
                f'{alphabetical}\n\n'
                f'## By frequency\n\n'
                f'{by_freq}\n\n')

    def all_nodes(self):
        if not self.nodes:
            return '# All nodes\n\nThere are no nodes here.\n\n'
        nodes = map(self.nodes.get, sorted(self.nodes, reverse=True))
        return node_list(nodes, 'All nodes')

    def _export_html(self, md, root, path, title=None):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        md = re.sub(TAG_REGEX, r'[\g<0>](/tag/\g<1>)', md)
        md = self._navigation_bar() + md
        md = resolve_links(md, path, 'html')
        style = resolve_path('style/style.css', path) if self.style else None
        html = md_to_html(md, title=self._title(title), style=style)
        (root / path).write_text(html)

    def _title(self, sub_title=None):
        parts = []
        if sub_title is not None:
            parts.append(sub_title)
        if self.title is not None:
            parts.append(self.title)
        return ' - '.join(parts)

    def _navigation_bar(self):
        elements = []
        if self.nodes:
            elements.append('[top](/index)')
            elements.append('[all](/all)')
        if self.tags:
            elements.append('[tags](/tags)')
        if not elements:
            return ''
        return ' '.join(elements) + '\n\n---\n\n'

    def _generate_tags(self):
        tags = {}
        for name, node in self.nodes.items():
            for tag in node.tags:
                tag_set = tags.setdefault(tag, set())
                tag_set.add(name)
        return tags

    def _infer_top_node(self):
        top_nodes = [node for node in self.nodes.values() if 'top' in node.tags]
        if not top_nodes:
            return None
        return min(top_nodes, key=lambda node: node.id)

class Node:
    def __init__(self, path, root_dir='.'):
        self.id = path
        self.content = (pathlib.Path(root_dir) / path).read_text()
        self.title = self._infer_title()
        self.tags = self._infer_tags()

    def matches(self, required_tags=None, forbidden_tags=None):
        if required_tags is not None:
            if not self.tags.issuperset(required_tags):
                return False
        if forbidden_tags is not None:
            if not self.tags.isdisjoint(forbidden_tags):
                return False
        return True

    def strip_tags(self, tags):
        self.tags.difference_update(tags)

    def markdown(self):
        return self.content

    def as_entry(self):
        return f'<small>{self.id}</small> [{self.title}]({self.id})'

    def _infer_title(self):
        match = re.search(r'^\s*#\s+(.+)', self.content, re.MULTILINE)
        return match.group(1) if match else self.id

    def _infer_tags(self):
        return set(re.findall(TAG_REGEX, self.content))

def node_list(nodes, title):
    entries = '\n'.join(['- ' + node.as_entry() for node in nodes])
    return (f'# {title}\n\n'
            f'*(generated automatically)*\n\n'
            f'{entries}')

def resolve_path(path, relative_to):
    path_parts = list(pathlib.Path(path).parts)
    rel_parts = list(pathlib.Path(relative_to).parent.parts)
    while path_parts and rel_parts and path_parts[0] == rel_parts[0]:
        path_parts = path_parts[1:]
        rel_parts = rel_parts[1:]
    return os.path.join(*['..'] * len(rel_parts) + path_parts)

def resolve_links(md, current_dir=None, extension=None):
    def resolve(match):
        path = match.group(2)
        if current_dir is not None:
            path = resolve_path(path, pathlib.Path('/') / current_dir)
        if (extension is not None and
            not path.endswith('/') and
            '.' not in path.split('/')[-1]):
                path += '.' + extension
        return f'[{match.group(1)}]({path})'

    # resolve simple links to /node/NAME
    md = re.sub(r'\[(.+?)\]\(([^/]+?)\)', r'[\g<1>](/node/\g<2>)', md)

    # resolve local links (with slash prefix)
    md = re.sub(r'\[(.+?)\]\((/.+?)\)', resolve, md)

    return md

def md_to_html(md, title='', style=None):
    # TODO more args to md2html?
    converter = subprocess.Popen(['md2html', '--fpermissive-url-autolinks', '--fstrikethrough'],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE)
    converter.stdin.write(md.encode('utf-8'))
    converter.stdin.close()
    res = converter.stdout.read().decode('utf-8').strip()
    html = ('<!DOCTYPE html>\n'
            '<html>\n'
            '<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="generator" content="ztk">\n'
            '<title>' + title + '</title>\n')
    if style:
        html += f'<link rel="stylesheet" href={style}>\n'
    html += (f'</head>\n'
             f'<body>\n'
             f'{res}\n'
             f'</body>\n'
             f'</html>')
    return html

def read_dir(path):
    return {f.name: Node(f.name, path) for f in pathlib.Path(path).glob('*')}

def main():
    required_tags = []
    forbidden_tags = []
    in_dir = None
    out_dir = None
    site_name = None
    style_path = None

    try:
        opts, args = getopt.getopt(sys.argv[1:], 't:T:I:n:s:', [])
        for opt, arg in opts:
            if opt == '-t':
                required_tags.append(arg)
            elif opt == '-T':
                forbidden_tags.append(arg)
            elif opt == '-I':
                in_dir = arg
            elif opt == '-n':
                site_name = arg
            elif opt == '-s':
                style_path = arg
        if len(args) == 1:
            out_dir = args[0]
        elif len(args) > 1:
            raise ValueError
    except Exception:
        print(HELP)
        sys.exit(2)

    nodes = None
    if in_dir:
        nodes = {name: node for name, node
                    in read_dir(in_dir).items()
                    if node.matches(required_tags=required_tags,
                                    forbidden_tags=forbidden_tags)}

    if nodes is not None:
        for node in nodes.values():
            pass
            # TODO we need to strip links from tags too etc
            #      but we also need to remove all missing local links
            #      ie missing nodes, tags, other files?
            #      node.strip_tags(required_tags)
        rete = Rete(nodes, title=site_name)
        if style_path is not None:
            rete.style = pathlib.Path(style_path).read_text()
        if out_dir is not None:
            rete.export_as_website(out_dir)

if __name__ == '__main__':
    main()
