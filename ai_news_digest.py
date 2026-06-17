#!/usr/bin/env python3
"""AI News Digest Agent — weekly email template generator for sales teams."""

import os
import sys
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

def install(pkg):
    os.system(f"{sys.executable} -m pip install {pkg} -q")

try:
    import anthropic
except ImportError:
    install("anthropic")
    import anthropic

try:
    import requests
except ImportError:
    install("requests")
    import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

AI_KEYWORDS = {
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "large language model", "gpt", "claude", "gemini", "mistral",
    "chatgpt", "openai", "anthropic", "deepmind", "meta ai", "grok",
    "neural", "generative", "diffusion", "transformer", "model release",
    "foundation model", "multimodal", "autonomous", "agent", "robotics",
    "inference", "finetuning", "benchmark", "agi",
}

RSS_FEEDS = [
    ("OpenAI Blog",          "https://openai.com/blog/rss.xml",                                    False),
    ("Google DeepMind",      "https://deepmind.google/blog/rss.xml",                               False),
    ("Hugging Face Blog",    "https://huggingface.co/blog/feed.xml",                               False),
    ("The Decoder",          "https://the-decoder.com/feed/",                                      False),
    ("Ars Technica AI",      "https://arstechnica.com/ai/feed/",                                   False),
    ("VentureBeat AI",       "https://venturebeat.com/category/ai/feed/",                          False),
    ("TechCrunch AI",        "https://techcrunch.com/category/artificial-intelligence/feed/",      False),
    ("MIT Technology Review","https://www.technologyreview.com/topic/artificial-intelligence/feed",False),
    ("Wired AI",             "https://www.wired.com/feed/tag/ai/latest/rss",                       False),
    ("IEEE Spectrum AI",     "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",  False),
    ("The Verge",            "https://www.theverge.com/rss/index.xml",                             True),
    ("404 Media",            "https://www.404media.co/rss/",                                       True),
]

SYSTEM_PROMPT = """You are an AI news curator for a sales team. Select and present the most exciting AI capability breakthroughs in a way that energizes people about what AI can DO.

PRIORITY ORDER when selecting stories:
1. New AI model releases and capability breakthroughs (always first)
2. AI doing something genuinely new — a frontier crossed
3. AI solving major real-world problems
4. New AI tools that change how businesses operate
5. Strategic moves revealing where AI is heading

Tone: Optimistic, enthusiastic, forward-looking. Even controversial stories get framed around the achievement. Make the reader feel like they're watching history happen.

Audience: Sales professionals who need credible, exciting AI conversations with clients.

When writing:
- Lead with the capability/achievement, not company name or funding
- Use vivid, concrete language
- Tie back to what this unlocks for real businesses
- Keep energy high"""


def parse_date(date_str):
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def is_ai_related(title, summary):
    text = (title + " " + summary).lower()
    return any(kw in text for kw in AI_KEYWORDS)


def fetch_rss(name, url, ai_filter, cutoff):
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for item in root.findall(".//item"):
            pub = (item.findtext("pubDate") or
                   item.findtext("{http://purl.org/dc/elements/1.1/}date") or "")
            dt = parse_date(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff:
                continue
            title = (item.findtext("title") or "").strip()
            summary = (item.findtext("description") or "").strip()[:800]
            if ai_filter and not is_ai_related(title, summary):
                continue
            articles.append({"source": name, "title": title, "summary": summary,
                              "date": dt.strftime("%Y-%m-%d"), "ts": dt})

        for entry in root.findall("atom:entry", ns):
            pub = (entry.findtext("atom:published", namespaces=ns) or
                   entry.findtext("atom:updated", namespaces=ns) or "")
            dt = parse_date(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff:
                continue
            title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
            sel = entry.find("atom:summary", ns)
            if sel is None:
                sel = entry.find("atom:content", ns)
            summary = (sel.text or "").strip()[:800] if sel is not None else ""
            if ai_filter and not is_ai_related(title, summary):
                continue
            articles.append({"source": name, "title": title, "summary": summary,
                              "date": dt.strftime("%Y-%m-%d"), "ts": dt})
    except Exception as e:
        print(f"  Warning: could not fetch {name} ({e})")
    return articles


def build_user_prompt(articles):
    today = datetime.now().strftime("%B %d, %Y")
    lines = [
        f"Today is {today}.",
        "",
        f"Below are {len(articles)} AI news articles from the past 7 days.",
        "Select the 5 most significant stories, prioritising model releases and capability breakthroughs.",
        "Even controversial stories (government bans, regulation) should be framed around the achievement.",
        "",
        "Return ONLY a valid JSON object — no markdown fences, no extra text — matching this schema exactly:",
        "",
        '{',
        '  "subject": "This Week in AI — <5-7 word catchy headline>",',
        '  "intro": "<One energetic sentence setting the tone for the week>",',
        '  "stories": [',
        '    {',
        '      "title": "<story headline>",',
        '      "source": "<publication name>",',
        '      "glance": "<2-3 sentence punchy summary focused on achievement and why it matters>",',
        '      "deep_p1": "<paragraph: what happened, who, what it can do, what makes it remarkable>",',
        '      "deep_p2": "<paragraph: what this unlocks for businesses, what changes, what to watch>"',
        '    }',
        '  ]',
        '}',
        "",
        "─── ARTICLES ───",
    ]
    for i, a in enumerate(articles, 1):
        lines.append(f"\n[{i}] {a['date']} | {a['source']}")
        lines.append(f"Title: {a['title']}")
        if a["summary"]:
            lines.append(f"Excerpt: {a['summary']}")
    return "\n".join(lines)


# ─── Plain-text renderer ────────────────────────────────────────────────────

def render_text(data, today):
    lines = [
        f"Subject: {data['subject']}",
        "",
        "Hi team,",
        "",
        data["intro"],
        "",
        "━" * 38,
        "TOP 5 AI STORIES AT A GLANCE",
        "━" * 38,
        "",
    ]
    for i, s in enumerate(data["stories"], 1):
        lines += [f"{i}. {s['title']}", s["glance"], ""]

    lines += ["━" * 38, "DEEP DIVE — THE FULL STORY", "━" * 38, ""]
    for i, s in enumerate(data["stories"], 1):
        lines += [f"{i}. {s['title']}", s["deep_p1"], "", s["deep_p2"], ""]

    lines += ["━" * 38, "", "Stay curious, stay ahead. See you next week!"]
    return "\n".join(lines)


# ─── HTML renderer ──────────────────────────────────────────────────────────

ACCENT   = "#00d4ff"
PURPLE   = "#a78bfa"
BG_MAIN  = "#0a0e1a"
BG_CARD  = "#111827"
BG_CARD2 = "#0f172a"
TEXT     = "#e2e8f0"
MUTED    = "#94a3b8"
BORDER   = "#1e293b"


def story_number_badge(n):
    return (
        f'<td width="48" valign="top" style="padding:0 14px 0 0">'
        f'<div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,{ACCENT},{PURPLE});'
        f'text-align:center;line-height:36px;font-size:15px;font-weight:700;color:#0a0e1a;font-family:Arial,sans-serif">'
        f'{n}</div></td>'
    )


def glance_card(n, story):
    modal_id = f"modal-{n}"
    return f"""
    <tr>
      <td style="padding:0 0 16px 0">
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background:{BG_CARD};border-radius:10px;border-left:3px solid {ACCENT}">
          <tr>
            <td style="padding:20px 22px">
              <table cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  {story_number_badge(n)}
                  <td valign="middle">
                    <p onclick="openModal('{modal_id}')" style="margin:0;font-size:16px;font-weight:700;color:{ACCENT};font-family:Arial,sans-serif;line-height:1.3;cursor:pointer">{story['title']} <span style="font-size:12px;opacity:0.6">&#8599;</span></p>
                  </td>
                </tr>
                <tr><td colspan="2" style="padding-top:10px">
                  <p style="margin:0;font-size:14px;color:{MUTED};font-family:Arial,sans-serif;line-height:1.6">{story['glance']}</p>
                </td></tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def story_modal(n, story):
    modal_id = f"modal-{n}"
    return f"""
<div id="{modal_id}" class="modal" onclick="if(event.target===this)closeModal('{modal_id}')">
  <div class="modal-content">
    <button class="modal-close" onclick="closeModal('{modal_id}')">&times;</button>
    <p style="margin:0 0 8px 0;font-size:11px;color:{PURPLE};font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:1px">{story['source']}</p>
    <h2 style="margin:0 0 20px 0;font-size:20px;font-weight:700;color:{TEXT};font-family:Arial,sans-serif;line-height:1.3">{story['title']}</h2>
    <p style="margin:0 0 14px 0;font-size:14px;color:{TEXT};font-family:Arial,sans-serif;line-height:1.7">{story['deep_p1']}</p>
    <p style="margin:0;font-size:14px;color:{MUTED};font-family:Arial,sans-serif;line-height:1.7">{story['deep_p2']}</p>
  </div>
</div>"""


def section_header(title, icon):
    return f"""
    <tr>
      <td style="padding:0 0 20px 0">
        <table cellpadding="0" cellspacing="0" border="0" width="100%">
          <tr>
            <td style="border-top:1px solid {BORDER};padding-top:28px">
              <p style="margin:0;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:{ACCENT};font-family:Arial,sans-serif;font-weight:700">{icon}&nbsp;&nbsp;{title}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def render_html(data, today):
    glance_rows = "".join(glance_card(i + 1, s) for i, s in enumerate(data["stories"]))
    modals      = "".join(story_modal(i + 1, s) for i, s in enumerate(data["stories"]))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{data['subject']}</title>
<style>
  .modal {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.75);
    z-index: 1000;
    align-items: center;
    justify-content: center;
    padding: 16px;
  }}
  .modal.active {{ display: flex; }}
  .modal-content {{
    background: {BG_CARD2};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 32px;
    max-width: 600px;
    width: 100%;
    max-height: 80vh;
    overflow-y: auto;
    position: relative;
  }}
  .modal-close {{
    position: absolute;
    top: 14px;
    right: 18px;
    background: none;
    border: none;
    color: {MUTED};
    font-size: 26px;
    cursor: pointer;
    line-height: 1;
  }}
  .modal-close:hover {{ color: #fff; }}
</style>
</head>
<body style="margin:0;padding:0;background-color:#060912;font-family:Arial,Helvetica,sans-serif">

<!-- Outer wrapper -->
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#060912;min-height:100vh">
<tr><td align="center" style="padding:32px 16px">

<!-- Email container -->
<table width="620" cellpadding="0" cellspacing="0" border="0" style="max-width:620px;width:100%">

  <!-- ── HEADER ── -->
  <tr>
    <td style="background:linear-gradient(135deg,#0d1433 0%,#1a0a2e 50%,#0d2040 100%);border-radius:14px 14px 0 0;padding:40px 36px 36px;border-bottom:2px solid {ACCENT}">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td>
            <p style="margin:0 0 6px 0;font-size:10px;letter-spacing:4px;text-transform:uppercase;color:{PURPLE};font-family:Arial,sans-serif">Weekly Briefing &nbsp;&#9679;&nbsp; {today}</p>
            <h1 style="margin:0;font-size:28px;font-weight:800;color:#ffffff;font-family:Arial,sans-serif;line-height:1.2">
              <span style="color:{ACCENT}">This Week</span> in AI
            </h1>
            <p style="margin:12px 0 0 0;font-size:14px;color:{MUTED};font-family:Arial,sans-serif;line-height:1.5">{data['intro']}</p>
          </td>
          <td width="60" align="right" valign="top">
            <div style="font-size:40px;line-height:1">&#129302;</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- ── BODY ── -->
  <tr>
    <td style="background:{BG_MAIN};padding:28px 32px 8px;border-left:1px solid {BORDER};border-right:1px solid {BORDER}">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">

        {section_header("Top 5 Stories at a Glance — click a title for the full story", "&#9889;")}
        {glance_rows}

      </table>
    </td>
  </tr>

  <!-- ── FOOTER ── -->
  <tr>
    <td style="background:linear-gradient(135deg,#0d1433,#0d2040);border-radius:0 0 14px 14px;padding:28px 36px;border-top:1px solid {BORDER};border-left:1px solid {BORDER};border-right:1px solid {BORDER};border-bottom:1px solid {BORDER}">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td>
            <p style="margin:0 0 4px 0;font-size:15px;font-weight:700;color:{TEXT};font-family:Arial,sans-serif">Stay curious, stay ahead.</p>
            <p style="margin:0;font-size:13px;color:{MUTED};font-family:Arial,sans-serif">See you next week. &#128640;</p>
          </td>
          <td align="right">
            <p style="margin:0;font-size:10px;color:#334155;font-family:Arial,sans-serif">AI News Digest</p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>

{modals}

<script>
  function openModal(id) {{
    document.getElementById(id).classList.add('active');
    document.body.style.overflow = 'hidden';
  }}
  function closeModal(id) {{
    document.getElementById(id).classList.remove('active');
    document.body.style.overflow = '';
  }}
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{
      document.querySelectorAll('.modal.active').forEach(function(m) {{
        m.classList.remove('active');
      }});
      document.body.style.overflow = '';
    }}
  }});
</script>
</body>
</html>"""


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    api_key  = os.environ.get("ANTHROPIC_API_KEY")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    print("Fetching AI news from sources...")
    all_articles = []
    for name, url, ai_filter in RSS_FEEDS:
        found = fetch_rss(name, url, ai_filter, cutoff)
        label = f"{len(found)} articles" + (" (AI-filtered)" if ai_filter else "")
        print(f"  {name}: {label}")
        all_articles.extend(found)

    all_articles.sort(key=lambda a: a["ts"], reverse=True)
    seen, unique = set(), []
    for a in all_articles:
        k = a["title"].lower().strip()
        if k not in seen:
            seen.add(k)
            unique.append(a)

    if not unique:
        print("\nNo articles found in the past 7 days.")
        sys.exit(1)

    print(f"\nTotal: {len(unique)} unique articles. Sending to Claude...\n")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs)

    response = client.messages.create(
        model="eu.anthropic.claude-opus-4-6-v1",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(unique)}],
    )

    raw = response.content[0].text.strip()
    # Strip accidental markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: Claude didn't return valid JSON.\n{e}\n\nRaw output:\n{raw}")
        sys.exit(1)

    today = datetime.now().strftime("%B %d, %Y")
    date_slug = datetime.now().strftime("%Y-%m-%d")

    txt_file  = f"ai_digest_{date_slug}.txt"
    html_file = f"ai_digest_{date_slug}.html"

    txt = render_text(data, today)
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(txt)

    html = render_html(data, today)
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(txt)
    print(f"\n--- Text saved to {txt_file}")
    print(f"--- HTML saved to {html_file}")


if __name__ == "__main__":
    main()
