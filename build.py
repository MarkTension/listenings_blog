#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown==3.11.3", "jinja2==3.1.6"]
# ///
"""
Tiny static site generator for Listenings.

    uv run build.py                 build the site into public/
    uv run build.py serve           build, serve on http://localhost:8000, rebuild on changes
    uv run build.py new "Artist - Album" --author Mark
                                    create a new post in content/posts/

How it works (top to bottom, that's all there is):
  1. read site.toml
  2. read every markdown file in content/ (front matter between +++ lines, TOML)
  3. render pages with the Jinja templates in templates/
  4. copy static/ and style.css into public/
"""

import argparse
import hashlib
import html
import re
import shutil
import sys
import time
import tomllib
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
PARTIALS = ROOT / "partials"
STATIC = ROOT / "static"
OUT = ROOT / "public"


# ---------------------------------------------------------------- content


class Page:
    def __init__(self, path: Path):
        self.source = path
        raw = path.read_text(encoding="utf-8")
        self.meta, body = parse_front_matter(raw, path)

        self.title = str(self.meta.get("title", "")).strip()
        self.description = str(self.meta.get("description", "")).strip()
        self.author = str(self.meta.get("author", "")).strip()
        self.draft = bool(self.meta.get("draft", False))
        self.date = parse_date(self.meta.get("date"))

        self.content = render_markdown(body)
        self.image = first_image(self.content)
        self.summary = summarize(self.content)

        # URL: content/posts/foo.md -> /posts/foo/ ; content/manifesto/_index.md -> /manifesto/
        rel = path.relative_to(CONTENT).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "_index":
            parts = parts[:-1]
        self.parts = parts
        self.section = parts[0] if len(parts) > 1 else ""
        self.url = "/" + "".join(p + "/" for p in parts)

    @property
    def author_url(self):
        return f"/author/{slugify(self.author)}/" if self.author else None


def parse_front_matter(raw: str, path: Path):
    m = re.match(r"^\+\+\+\s*\n(.*?)\n\+\+\+\s*\n?(.*)$", raw, re.S)
    if not m:
        sys.exit(f"{path}: expected TOML front matter between +++ lines")
    return tomllib.loads(m.group(1)), m.group(2)


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    elif not isinstance(value, datetime):  # TOML date without time
        value = datetime(value.year, value.month, value.day)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


SHORTCODE = re.compile(r"\{\{<\s*(\w[\w-]*)\s*>\}\}")


def render_markdown(body: str) -> str:
    # Shortcodes like {{< mailchimp >}} insert partials/<name>.html.
    # Swap them for a placeholder first so markdown leaves the HTML alone.
    inserts = {}

    def stash(m):
        key = f"SHORTCODE{len(inserts)}PLACEHOLDER"
        inserts[key] = (PARTIALS / f"{m.group(1)}.html").read_text(encoding="utf-8")
        return f"\n\n{key}\n\n"

    body = SHORTCODE.sub(stash, body)
    out = markdown.markdown(body, extensions=["extra", "sane_lists", "smarty"])
    for key, value in inserts.items():
        out = out.replace(f"<p>{key}</p>", value).replace(key, value)
    return out


def first_image(content: str):
    m = re.search(r'<img[^>]+src="([^"]+)"', content)
    return html.unescape(m.group(1)) if m else None


def plain_text(content: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", content, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def summarize(content: str, length=200) -> str:
    text = plain_text(content)
    if len(text) <= length:
        return text
    return text[:length].rsplit(" ", 1)[0] + " …"


def slugify(s: str) -> str:
    return re.sub(r"[\W_]+", "-", s.strip().lower()).strip("-")


def load_content(include_drafts=False):
    now = datetime.now(timezone.utc)
    posts, pages = [], []
    for path in sorted(CONTENT.rglob("*.md")):
        page = Page(path)
        if page.draft and not include_drafts:
            continue
        if page.date and page.date > now and not include_drafts:
            print(f"  skipping future post: {path.name}")
            continue
        (posts if page.section == "posts" and path.stem != "_index" else pages).append(page)

    posts.sort(key=lambda p: p.date or now, reverse=True)
    for i, post in enumerate(posts):
        post.newer = posts[i - 1] if i > 0 else None
        post.older = posts[i + 1] if i + 1 < len(posts) else None
    return posts, pages


# ---------------------------------------------------------------- build


def build(include_drafts=False, dev=False):
    t0 = time.time()
    config = tomllib.loads((ROOT / "site.toml").read_text(encoding="utf-8"))
    base_url = config["base_url"].rstrip("/")
    posts, pages = load_content(include_drafts)

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(STATIC, OUT)

    css = (ROOT / "style.css").read_bytes()
    (OUT / "style.css").write_bytes(css)

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["date"] = lambda d, fmt="%B %-d, %Y": d.strftime(fmt) if d else ""
    env.filters["rfc822"] = lambda d: format_datetime(d) if d else ""
    env.filters["slug"] = slugify
    env.filters["abs"] = lambda url: base_url + quote(url)
    env.globals.update(
        site=config,
        dev=dev,
        css_version=hashlib.md5(css).hexdigest()[:8],
        year=datetime.now().year,
    )

    def write(url, template, **ctx):
        path = OUT / url.strip("/") / "index.html" if not url.endswith((".html", ".xml", ".txt")) else OUT / url.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(env.get_template(template).render(url=url, **ctx), encoding="utf-8")

    by_url = {p.url: p for p in pages}

    # home + /posts/ (same listing)
    home = by_url.pop("/", None)
    posts_index = by_url.pop("/posts/", None)
    write("/", "home.html", page=home, posts=posts)
    write("/posts/", "home.html", page=posts_index or home, posts=posts)

    # posts
    for post in posts:
        write(post.url, "post.html", page=post)

    # other pages (manifesto, ...)
    for page in by_url.values():
        write(page.url, "page.html", page=page)

    # authors
    authors = {}
    for post in posts:
        if post.author:
            authors.setdefault(post.author, []).append(post)
    authors = sorted(authors.items(), key=lambda a: (-len(a[1]), a[0]))
    write("/author/", "authors.html", authors=authors, title="Authors")
    for name, author_posts in authors:
        write(f"/author/{slugify(name)}/", "author.html", name=name, posts=author_posts, title=name)

    # redirects (QR stickers etc.)
    for src, target in config.get("redirects", {}).items():
        write(f"/{src.strip('/')}/", "redirect.html", target=target)

    write("/404.html", "404.html", title="Page not found")
    write("/index.xml", "rss.xml", posts=posts, feed_url="/index.xml")
    write("/posts/index.xml", "rss.xml", posts=posts, feed_url="/posts/index.xml")
    all_urls = ["/", "/posts/", "/author/"] + [p.url for p in posts] + [p.url for p in by_url.values()] \
        + [f"/author/{slugify(n)}/" for n, _ in authors]
    write("/sitemap.xml", "sitemap.xml", urls=all_urls)
    write("/robots.txt", "robots.txt")

    print(f"built {len(posts)} posts, {len(by_url)} pages, {len(authors)} authors in {time.time() - t0:.2f}s")


# ---------------------------------------------------------------- serve


def snapshot():
    files = [ROOT / "site.toml", ROOT / "style.css"]
    for d in (CONTENT, TEMPLATES, PARTIALS, STATIC):
        files += [f for f in d.rglob("*") if f.is_file()]
    return {f: f.stat().st_mtime for f in files}


def serve(port, include_drafts):
    import functools
    import http.server
    import threading

    build(include_drafts, dev=True)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(OUT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"serving on http://localhost:{port}  (Ctrl+C to stop; rebuilds on save)", flush=True)

    state = snapshot()
    try:
        while True:
            time.sleep(0.5)
            new = snapshot()
            if new != state:
                state = new
                try:
                    build(include_drafts, dev=True)
                except Exception as e:  # keep serving if a template has a typo
                    print(f"build failed: {e}")
    except KeyboardInterrupt:
        server.shutdown()


# ---------------------------------------------------------------- new post


def new_post(title, author):
    path = CONTENT / "posts" / f"{slugify(title)}.md"
    if path.exists():
        sys.exit(f"{path} already exists")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    by = f" by {author}" if author else ""
    path.write_text(
        f"""+++
date = '{now}'
draft = true
title = "{title}"
description = "{title}: An album recommendation{by} on why to listen to this album back-to-back."
author = '{author}'
+++

""",
        encoding="utf-8",
    )
    print(f"created {path.relative_to(ROOT)} (draft = true; set it to false to publish)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the Listenings site.")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="build, serve locally and rebuild on changes")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--drafts", action="store_true", help="include drafts and future posts")
    n = sub.add_parser("new", help="create a new post")
    n.add_argument("title")
    n.add_argument("--author", default="")
    ap.add_argument("--drafts", action="store_true", help="include drafts and future posts")
    args = ap.parse_args()

    if args.cmd == "serve":
        serve(args.port, args.drafts)
    elif args.cmd == "new":
        new_post(args.title, args.author)
    else:
        build(args.drafts)
