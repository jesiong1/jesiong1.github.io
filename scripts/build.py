#!/usr/bin/env python3
"""
Build the site.

For each posts/YYYY-MM-DD-slug.tex:
  * convert to an HTML body (LaTeXML in CI; Pandoc fallback for local smoke tests)
  * wrap it in templates/post.html  ->  _site/blog/<slug>/index.html
Then:
  * regenerate the homepage blog list between <!-- BLOG:START --> / <!-- BLOG:END -->
  * copy static assets into _site/
  * write _site/feed.xml (RSS 2.0)

Run from the repo root:  python3 scripts/build.py
"""
import os, re, sys, glob, shutil, subprocess, html, datetime
from email.utils import format_datetime

REPO   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE   = os.path.join(REPO, "_site")
POSTS  = os.path.join(REPO, "posts")
TPL    = os.path.join(REPO, "templates", "post.html")
BASEURL = os.environ.get("BASEURL", "https://janglowacki.com").rstrip("/")
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
FULLMONTHS = ["January","February","March","April","May","June","July",
              "August","September","October","November","December"]

# skip these when copying the repo into _site
SKIP = {".git", ".github", "posts", "scripts", "templates", "_site", "README.md", ".gitignore"}


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


# Injected into every post's preamble: shared helpers so posts stay DRY.
#   \postlink{slug}{text}  ->  a link to /blog/<slug>/  (link to your other posts)
PREAMBLE_INJECT = (
    "\\usepackage{hyperref}\n"
    "\\providecommand{\\postlink}[2]{\\href{/blog/#1/}{#2}}\n"
)


def tex_to_body(texpath):
    """Return (body_html, converter_name)."""
    src = open(texpath, encoding="utf-8").read()
    if "\\begin{document}" in src:
        src = src.replace("\\begin{document}", PREAMBLE_INJECT + "\\begin{document}", 1)
    tmp = texpath + ".build.tex"
    open(tmp, "w", encoding="utf-8").write(src)
    try:
        if shutil.which("latexmlc"):
            out = tmp + ".html"
            run(["latexmlc", tmp, "--dest=" + out, "--format=html5", "--quiet"])
            raw = open(out, encoding="utf-8").read()
            os.remove(out)
            return extract_latexml_body(raw), "latexml"
        # local smoke-test fallback
        r = run(["pandoc", tmp, "--mathjax", "-t", "html5"])
        return r.stdout, "pandoc"
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def extract_latexml_body(full_html):
    """Pull just the article content out of LaTeXML's full HTML page.
    LaTeXML wraps the content in <article class="ltx_document">...; grabbing that
    excludes the <head> tags, and CSS in the template hides the author/date block."""
    m = re.search(r'<article class="ltx_document.*?</article>', full_html, re.DOTALL)
    if not m:
        m = re.search(r'<div class="ltx_document.*</div>\s*</body>', full_html, re.DOTALL)
    body = m.group(0) if m else full_html
    # drop LaTeXML's own document title block (template supplies the H1)
    body = re.sub(r'<h1 class="ltx_title ltx_title_document">.*?</h1>', "", body, flags=re.DOTALL)
    return body


def meta_from_tex(texpath):
    src = open(texpath, encoding="utf-8").read()
    fname = os.path.basename(texpath)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.+)\.tex$", fname)
    if not m:
        raise SystemExit(f"Post filename must be YYYY-MM-DD-slug.tex, got: {fname}")
    y, mo, d, slug = int(m[1]), int(m[2]), int(m[3]), m[4]
    date = datetime.date(y, mo, d)

    tm = re.search(r"\\title\{(.+?)\}", src, re.DOTALL)
    title = re.sub(r"\s+", " ", tm.group(1)).strip() if tm else slug

    # excerpt: prefer a "% excerpt: ..." comment, else first sentence of the abstract
    em = re.search(r"^%\s*excerpt:\s*(.+)$", src, re.MULTILINE)
    if em:
        excerpt = em.group(1).strip()
    else:
        am = re.search(r"\\begin\{abstract\}(.+?)\\end\{abstract\}", src, re.DOTALL)
        text = re.sub(r"\s+", " ", am.group(1)).strip() if am else ""
        excerpt = (text.split(". ")[0] + ".") if text else ""
    return {"slug": slug, "title": title, "excerpt": excerpt,
            "date": date,
            "date_human": f"{date.day} {FULLMONTHS[mo-1]} {y}",
            "month": MONTHS[mo-1], "year": str(y)}


def build_posts():
    tpl = open(TPL, encoding="utf-8").read()
    posts, conv_used = [], None
    for texpath in sorted(glob.glob(os.path.join(POSTS, "*.tex"))):
        meta = meta_from_tex(texpath)
        body, conv_used = tex_to_body(texpath)
        page = (tpl.replace("{{TITLE}}", html.escape(meta["title"]))
                   .replace("{{EXCERPT}}", html.escape(meta["excerpt"]))
                   .replace("{{DATE_HUMAN}}", meta["date_human"])
                   .replace("{{BODY}}", body))
        outdir = os.path.join(SITE, "blog", meta["slug"])
        os.makedirs(outdir, exist_ok=True)
        open(os.path.join(outdir, "index.html"), "w", encoding="utf-8").write(page)
        posts.append(meta)
        print(f"  built /blog/{meta['slug']}/  ({conv_used})")
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def render_rows(posts):
    if not posts:
        return ('                <p style="color:var(--text-muted);">'
                'Work in progress — first posts coming soon.</p>')
    rows = []
    for p in posts:
        rows.append(f'''                <div class="talk fade-in">
                    <div class="talk-date">
                        <div class="month">{p["month"]}</div>
                        <div class="year">{p["year"]}</div>
                    </div>
                    <div class="talk-info">
                        <div class="title">{html.escape(p["title"])}</div>
                        <div class="event">{html.escape(p["excerpt"])}</div>
                    </div>
                    <div class="talk-link">
                        <a href="/blog/{p["slug"]}/">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14 2 14 8 20 8"></polyline>
                                <line x1="16" y1="13" x2="8" y2="13"></line>
                                <line x1="16" y1="17" x2="8" y2="17"></line>
                            </svg>
                            Read
                        </a>
                    </div>
                </div>''')
    return "\n".join(rows)


def regenerate_homepage(posts):
    src = open(os.path.join(REPO, "index.html"), encoding="utf-8").read()
    pat = re.compile(r"(<!-- BLOG:START -->).*?(<!-- BLOG:END -->)", re.DOTALL)
    if not pat.search(src):
        raise SystemExit("index.html is missing <!-- BLOG:START --> / <!-- BLOG:END --> markers")
    block = "<!-- BLOG:START -->\n" + render_rows(posts) + "\n                <!-- BLOG:END -->"
    src = pat.sub(lambda m: block, src, count=1)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(src)
    print(f"  homepage blog list regenerated ({len(posts)} post(s))")


def copy_assets():
    for name in os.listdir(REPO):
        if name in SKIP or name == "index.html":
            continue
        src = os.path.join(REPO, name)
        dst = os.path.join(SITE, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def write_feed(posts):
    items = []
    for p in posts:
        link = f"{BASEURL}/blog/{p['slug']}/"
        pub = format_datetime(datetime.datetime(p["date"].year, p["date"].month, p["date"].day, 12, 0))
        items.append(f"""    <item>
      <title>{html.escape(p['title'])}</title>
      <link>{link}</link>
      <guid>{link}</guid>
      <pubDate>{pub}</pubDate>
      <description>{html.escape(p['excerpt'])}</description>
    </item>""")
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
    <title>Jan Głowacki — Blog</title>
    <link>{BASEURL}/#blog</link>
    <description>Short notes and essays on mathematical physics.</description>
{chr(10).join(items)}
</channel></rss>
"""
    open(os.path.join(SITE, "feed.xml"), "w", encoding="utf-8").write(feed)
    print(f"  feed.xml written ({len(posts)} item(s))")


def main():
    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)
    print("Building site ->", SITE)
    posts = build_posts()
    copy_assets()
    regenerate_homepage(posts)
    write_feed(posts)
    print("Done.")


if __name__ == "__main__":
    main()
