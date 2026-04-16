---
title: Freeze Your Site
order: 3
category: Articles
description: Turn any Chirp app into a static site with one command.
tags: [chirp, static, deployment]
---

# Freeze Your Site

`chirp freeze` walks your route table and renders every page through the same
middleware stack the live server uses. The output is a directory of static HTML
files.

## The Command

```bash
chirp dev            # Live server — htmx, hot reload, Suspense
chirp freeze dist/   # Walk routes, render, write static HTML
```

During development you get the full framework. When you're ready to ship,
`freeze` projects the same content as flat files.

## Deploy Anywhere

The frozen output works on any static host:

- **S3 + CloudFront** — upload the directory, done
- **Cloudflare Pages** — connect your repo, set the build command
- **GitHub Pages** — push to `gh-pages` branch
- **Netlify** — drag and drop the `dist/` folder

## Progressive Enhancement

The frozen HTML retains htmx attributes. If you later put a Chirp server
in front of the static files, fragment navigation activates automatically.
You don't have to choose static vs dynamic up front.
