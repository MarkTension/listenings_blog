# Listenings

The blog at https://www.listenings.nl, built by a ~250 line Python script (`build.py`).
No Hugo, no theme: the HTML templates and the CSS are all here and all yours.

## Writing a post

Add a markdown file to `content/posts/` and push to `main`. GitHub Actions builds and deploys it.

```
+++
date = '2026-11-15T12:00:00+01:00'
draft = false
title = "Artist - Album"
description = "Artist - Album: An album recommendation by Mark on why to listen to this album back-to-back."
author = 'Mark'
+++

[![](cover-image-url)](spotify-url)

Your text...
```

Or let the script create it for you: `uv run build.py new "Artist - Album" --author Mark`

- `draft = true` hides the post. So does a date in the future (until a build runs after that date).
- The first image in the post is used as the thumbnail on the home page.
- `{{< mailchimp >}}` inserts `partials/mailchimp.html`. Any file in `partials/` works this way.

## Previewing locally

```
uv run build.py serve            # http://localhost:8000, rebuilds when you save
uv run build.py serve --drafts   # also show drafts and future posts
```

The dependencies are declared at the top of `build.py`; uv installs them automatically.

## Where things are

| What                          | Where                         |
|-------------------------------|-------------------------------|
| Site title, menu, redirects   | `site.toml`                   |
| All styling                   | `style.css`                   |
| Page layout (header, footer)  | `templates/base.html`         |
| Home page                     | `templates/home.html`         |
| Post card on home page        | `templates/_card.html`        |
| A single post                 | `templates/post.html`         |
| Manifesto and other pages     | `templates/page.html`         |
| Images, favicon, CNAME        | `static/` (copied as-is)      |

Templates are plain HTML with [Jinja](https://jinja.palletsprojects.com/templates/) tags:
`{{ page.title }}`, `{% for post in posts %}...{% endfor %}`, `{% if ... %}`.
