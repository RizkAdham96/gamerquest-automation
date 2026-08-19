import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from groq import Groq


# =========================================================
# CONFIGURATION
# =========================================================

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]

DRAFTS_FOLDER = Path("drafts")
STATE_FOLDER = Path("state")
TAVILY_STATE_FILE = STATE_FOLDER / "tavily_usage.json"

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

TAVILY_MONTHLY_SAFETY_LIMIT = 900
MAX_TAVILY_SEARCHES_PER_RUN = 1

SEARCH_QUERY = (
    "latest important video game news today "
    "game announcements releases major updates DLC hardware "
    "PlayStation Xbox Nintendo PC Steam gaming industry "
    "developers publishers"
)

MAX_RESULTS = 15

MIN_SOURCE_TEXT_LENGTH = 800
MAX_SOURCE_TEXT_LENGTH = 30000


# =========================================================
# OFFICIAL SOURCE DOMAINS
# =========================================================

OFFICIAL_DOMAIN_KEYWORDS = [
    "playstation.com",
    "xbox.com",
    "nintendo.com",
    "steampowered.com",
    "steamcommunity.com",
    "ea.com",
    "ubisoft.com",
    "rockstargames.com",
    "2k.com",
    "epicgames.com",
    "activision.com",
    "blizzard.com",
    "bethesda.net",
    "square-enix.com",
    "bandainamcoent.com",
    "capcom.com",
    "sega.com",
    "konami.com",
    "riotgames.com",
    "playvalorant.com",
    "leagueoflegends.com",
    "jagex.com",
    "warframe.com",
    "digitalextremes.com",
    "cdprojektred.com",
    "cyberpunk.net",
    "thewitcher.com",
]


# =========================================================
# BASIC HELPERS
# =========================================================

def get_domain(url):
    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .replace("www.", "")
        )
    except Exception:
        return ""


def looks_official(url):
    domain = get_domain(url)

    return any(
        keyword in domain
        for keyword in OFFICIAL_DOMAIN_KEYWORDS
    )


def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text[:80]


def strip_code_fences(text):
    text = text.strip()

    text = re.sub(
        r"^```(?:html|markdown|md)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    return text.strip()


def normalize_words(text):
    words = re.findall(
        r"[a-zA-Z0-9À-ÿ]+",
        text.lower()
    )

    stopwords = {
        "the", "and", "for", "from", "with",
        "this", "that", "into", "new", "news",
        "game", "games", "gaming", "video",
        "update", "reveals", "revealed",
        "announces", "announced",
    }

    return [
        word
        for word in words
        if len(word) >= 3
        and word not in stopwords
    ]


# =========================================================
# PERSISTENT TAVILY CREDIT COUNTER
# =========================================================

def current_month():
    return datetime.now(
        timezone.utc
    ).strftime("%Y-%m")


def load_tavily_state():
    STATE_FOLDER.mkdir(
        exist_ok=True
    )

    month = current_month()

    default_state = {
        "month": month,
        "searches_used": 0
    }

    if not TAVILY_STATE_FILE.exists():
        return default_state

    try:
        state = json.loads(
            TAVILY_STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return default_state

    if state.get("month") != month:
        return default_state

    return {
        "month": month,
        "searches_used": int(
            state.get(
                "searches_used",
                0
            )
        )
    }


def save_tavily_state(state):
    STATE_FOLDER.mkdir(
        exist_ok=True
    )

    TAVILY_STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2
        ),
        encoding="utf-8"
    )


def check_monthly_credit_safety():
    state = load_tavily_state()

    used = state["searches_used"]

    print("")
    print(
        f"GamerQuest Tavily counter: "
        f"{used} / "
        f"{TAVILY_MONTHLY_SAFETY_LIMIT}"
    )

    if used >= TAVILY_MONTHLY_SAFETY_LIMIT:
        print("")
        print("===================================")
        print("TAVILY MONTHLY SAFETY STOP")
        print("===================================")
        print(
            "No more Tavily searches will be "
            "performed this month."
        )
        sys.exit(0)

    return state


def record_tavily_search(state):
    state["searches_used"] += 1

    save_tavily_state(
        state
    )

    print(
        f"Recorded Tavily search. "
        f"Monthly count: "
        f"{state['searches_used']} / "
        f"{TAVILY_MONTHLY_SAFETY_LIMIT}"
    )


# =========================================================
# DUPLICATE CHECK
# =========================================================

def source_already_used(source_url):
    if not DRAFTS_FOLDER.exists():
        return False

    for draft_file in DRAFTS_FOLDER.glob("*.md"):
        try:
            text = draft_file.read_text(
                encoding="utf-8"
            )

            if source_url in text:
                return True

        except Exception as error:
            print(
                f"Could not read "
                f"{draft_file}: {error}"
            )

    return False


def get_recent_source_domains():
    if not DRAFTS_FOLDER.exists():
        return []

    domains = []

    files = sorted(
        DRAFTS_FOLDER.glob("*.md"),
        reverse=True
    )

    for draft_file in files[:12]:
        try:
            text = draft_file.read_text(
                encoding="utf-8"
            )

            urls = re.findall(
                r'https?://[^\s<>"\']+',
                text
            )

            for url in urls:
                domain = get_domain(url)

                if (
                    domain
                    and domain not in domains
                ):
                    domains.append(domain)

        except Exception:
            continue

    return domains[:10]


# =========================================================
# ONE TAVILY SEARCH ONLY
# =========================================================

def search_gaming_news():
    state = check_monthly_credit_safety()

    searches_this_run = 0

    if (
        searches_this_run
        >= MAX_TAVILY_SEARCHES_PER_RUN
    ):
        raise RuntimeError(
            "Per-run Tavily limit reached."
        )

    print("")
    print("===================================")
    print("SEARCHING GAMING NEWS")
    print("===================================")
    print(
        "Tavily searches allowed this run: 1"
    )

    response = requests.post(
        TAVILY_SEARCH_URL,
        headers={
            "Authorization":
                f"Bearer {TAVILY_API_KEY}",
            "Content-Type":
                "application/json",
        },
        json={
            "query": SEARCH_QUERY,
            "search_depth": "basic",
            "topic": "news",
            "time_range": "day",
            "max_results": MAX_RESULTS,
            "include_answer": False,
            "include_raw_content": "text",
            "auto_parameters": False,
        },
        timeout=60,
    )

    searches_this_run += 1

    response.raise_for_status()

    record_tavily_search(
        state
    )

    data = response.json()

    results = data.get(
        "results",
        []
    )

    if not results:
        print(
            "No gaming news results found."
        )
        sys.exit(0)

    print(
        f"Tavily returned "
        f"{len(results)} candidates."
    )

    clean_results = []

    for result in results:

        title = (
            result
            .get("title", "")
            .strip()
        )

        url = (
            result
            .get("url", "")
            .strip()
        )

        if not title or not url:
            continue

        if source_already_used(url):
            print(
                f"Duplicate skipped: "
                f"{title}"
            )
            continue

        clean_results.append(
            result
        )

    if not clean_results:
        print(
            "All returned stories "
            "were already processed."
        )
        sys.exit(0)

    return clean_results


# =========================================================
# SELECT BEST STORY
# =========================================================

def select_best_story(results):
    client = Groq(
        api_key=GROQ_API_KEY
    )

    recent_domains = (
        get_recent_source_domains()
    )

    candidates = ""

    for index, result in enumerate(
        results,
        start=1
    ):

        content = (
            result.get(
                "content",
                ""
            )
            or result.get(
                "raw_content",
                ""
            )
            or ""
        )

        candidates += f"""

CANDIDATE {index}

TITLE:
{result.get('title', '')}

DOMAIN:
{get_domain(result.get('url', ''))}

URL:
{result.get('url', '')}

DATE:
{result.get('published_date', '')}

SEARCH SCORE:
{result.get('score', '')}

OFFICIAL DOMAIN:
{"YES" if looks_official(result.get('url', '')) else "NO"}

CONTENT:
{content[:1800]}

-------------------------------------
"""

    prompt = f"""
You are editor-in-chief of GamerQuest FR.

Choose ONE story worth covering today
for a French gaming audience.

RECENTLY USED SOURCE DOMAINS:

{recent_domains}

CANDIDATES:

{candidates}

SELECTION PRIORITIES:

1. Importance to gamers.
2. Recency.
3. Reliability.
4. Concrete information available.
5. Source diversity.
6. Potential usefulness to French readers.

PREFER:

- major game announcements
- releases
- important updates
- substantial DLC
- gameplay reveals
- hardware news
- official release dates
- acquisitions
- major industry developments
- meaningful platform announcements

AVOID:

- obvious rumors
- leaks
- affiliate content
- SEO spam
- low-quality blogs
- generic homepages
- category pages
- tiny patches
- weak opinion pieces
- clickbait
- stories with almost no factual detail

IMPORTANT:

Do NOT automatically pick PlayStation.

Do NOT automatically pick an official source
if a reputable publication has the stronger story.

If two candidates are equally strong,
prefer the domain GamerQuest has used less recently.

Return ONLY the candidate number.
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",

        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict "
                    "gaming-news editor."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        temperature=0.1,
    )

    answer = (
        response
        .choices[0]
        .message
        .content
        .strip()
    )

    match = re.search(
        r"\d+",
        answer
    )

    if not match:
        raise RuntimeError(
            f"Could not parse "
            f"story selection: {answer}"
        )

    number = int(
        match.group()
    )

    if (
        number < 1
        or number > len(results)
    ):
        raise RuntimeError(
            "Groq selected an invalid candidate."
        )

    story = results[
        number - 1
    ]

    print("")
    print(
        "SELECTED STORY:"
    )

    print(
        story.get(
            "title",
            ""
        )
    )

    print(
        story.get(
            "url",
            ""
        )
    )

    return story


# =========================================================
# EXTRACT SOURCE PAGE
# =========================================================

def extract_page(story):
    raw_content = (
        story.get(
            "raw_content",
            ""
        )
        or ""
    )

    if (
        len(raw_content)
        >= MIN_SOURCE_TEXT_LENGTH
    ):

        print(
            "Using article content "
            "returned by Tavily."
        )

        return raw_content[
            :MAX_SOURCE_TEXT_LENGTH
        ]

    print(
        "Fetching selected page directly..."
    )

    response = requests.get(
        story["url"],

        timeout=30,

        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; "
                "GamerQuestFR/1.0; "
                "editorial research)"
            )
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    for element in soup([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "form",
        "noscript",
    ]):
        element.decompose()

    article = soup.find(
        "article"
    )

    if article:
        text = article.get_text(
            separator="\n",
            strip=True
        )
    else:
        text = soup.get_text(
            separator="\n",
            strip=True
        )

    return text[
        :MAX_SOURCE_TEXT_LENGTH
    ]


# =========================================================
# SOURCE VALIDATION — GATE 1
# =========================================================

def validate_source(
    story,
    source_text
):
    print("")
    print(
        "VALIDATING SOURCE..."
    )

    url = (
        story.get(
            "url",
            ""
        )
        .strip()
    )

    title = (
        story.get(
            "title",
            ""
        )
        .strip()
    )

    parsed = urlparse(
        url
    )

    path = (
        parsed
        .path
        .strip("/")
    )

    if not path:
        print(
            "SOURCE REJECTED: homepage."
        )
        return False

    generic_paths = {
        "news",
        "gaming",
        "games",
        "articles",
        "latest",
        "home",
        "category",
    }

    if path.lower() in generic_paths:
        print(
            "SOURCE REJECTED: "
            "generic landing page."
        )
        return False

    if (
        len(source_text)
        < MIN_SOURCE_TEXT_LENGTH
    ):
        print(
            "SOURCE REJECTED: "
            "not enough article text."
        )
        return False

    title_words = normalize_words(
        title
    )

    unique_words = set(
        title_words
    )

    if not unique_words:
        print(
            "SOURCE REJECTED: "
            "title could not be analyzed."
        )
        return False

    body_lower = (
        source_text
        .lower()
    )

    matched = sum(
        1
        for word in unique_words
        if word in body_lower
    )

    ratio = (
        matched
        / max(
            len(unique_words),
            1
        )
    )

    print(
        "Title/body keyword match: "
        f"{ratio:.2f}"
    )

    if ratio < 0.35:
        print(
            "SOURCE REJECTED: "
            "title and article do not match."
        )
        return False

    client = Groq(
        api_key=GROQ_API_KEY
    )

    prompt = f"""
Validate this web source before GamerQuest
is allowed to write a news article.

SEARCH TITLE:

{title}

URL:

{url}

EXTRACTED PAGE:

{source_text[:9000]}

The page is VALID only if:

- it clearly represents the same specific
  story as the search title;
- it is an article or specific announcement;
- it contains coherent information
  about that story.

INVALID if:

- homepage
- category page
- general news index
- unrelated content
- multiple unrelated stories mixed together
- title and page discuss different subjects
- page extraction is unreliable

Return exactly:

VALID

or

INVALID
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",

        messages=[
            {
                "role": "system",
                "content": (
                    "Validate sources "
                    "conservatively."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        temperature=0,
    )

    verdict = (
        response
        .choices[0]
        .message
        .content
        .strip()
        .upper()
    )

    print(
        f"Semantic source verdict: "
        f"{verdict}"
    )

    if verdict != "VALID":
        print(
            "SOURCE REJECTED."
        )
        return False

    print(
        "SOURCE VALIDATION PASSED."
    )

    return True


# =========================================================
# FIND MATCHING OFFICIAL SOURCE
# =========================================================

def find_matching_official_source(
    selected_story,
    all_results
):
    official_candidates = [
        result
        for result in all_results
        if looks_official(
            result.get(
                "url",
                ""
            )
        )
    ]

    if not official_candidates:
        return None

    client = Groq(
        api_key=GROQ_API_KEY
    )

    candidates = ""

    for index, result in enumerate(
        official_candidates,
        start=1
    ):

        content = (
            result.get(
                "content",
                ""
            )
            or result.get(
                "raw_content",
                ""
            )
            or ""
        )

        candidates += f"""

OFFICIAL CANDIDATE {index}

TITLE:
{result.get('title', '')}

URL:
{result.get('url', '')}

CONTENT:
{content[:1400]}

-----------------------------------
"""

    prompt = f"""
The selected GamerQuest discovery story is:

TITLE:
{selected_story.get('title', '')}

URL:
{selected_story.get('url', '')}

Possible official sources found inside
THE SAME Tavily search:

{candidates}

Determine whether one candidate clearly
covers the SAME announcement/event.

Do NOT guess.

If one clearly matches, return its number.

Otherwise return:

NONE
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",

        messages=[
            {
                "role": "system",
                "content": (
                    "Match primary sources "
                    "very conservatively."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        temperature=0,
    )

    answer = (
        response
        .choices[0]
        .message
        .content
        .strip()
    )

    if "NONE" in answer.upper():
        return None

    match = re.search(
        r"\d+",
        answer
    )

    if not match:
        return None

    number = int(
        match.group()
    )

    if (
        number < 1
        or number > len(
            official_candidates
        )
    ):
        return None

    return official_candidates[
        number - 1
    ]


# =========================================================
# GENERATE ARTICLE
# =========================================================

def generate_article(
    story,
    source_text,
    official_story=None,
    official_text=""
):
    print("")
    print(
        "GENERATING GAMERQUEST ARTICLE..."
    )

    client = Groq(
        api_key=GROQ_API_KEY
    )

    official_section = ""

    if (
        official_story
        and official_text
    ):
        official_section = f"""

OFFICIAL VERIFICATION SOURCE:

TITLE:
{official_story.get('title', '')}

URL:
{official_story.get('url', '')}

CONTENT:
{official_text}

"""

    prompt = f"""
You are a rigorous journalist for GamerQuest FR.

Create an ORIGINAL French gaming-news article.

================================================
DISCOVERY SOURCE
================================================

TITLE:
{story.get('title', '')}

DOMAIN:
{get_domain(story.get('url', ''))}

URL:
{story.get('url', '')}

DATE:
{story.get('published_date', '')}

CONTENT:
{source_text}


{official_section}


================================================
FACTUAL PRIORITY
================================================

If an official source is provided,
it is authoritative for:

- dates
- platforms
- editions
- pricing
- availability
- game features
- technical specifications
- names
- developers
- publishers

If the secondary source conflicts with
the official source:

USE THE OFFICIAL SOURCE.

If NO official source exists:

Use ONLY claims directly supported by
the discovery source.


================================================
HIGH-RISK CLAIM VERIFICATION
================================================

The following claims require EXTRA CAUTION:

- release dates
- early-access dates
- Xbox Game Pass availability
- PlayStation Plus availability
- Nintendo Switch Online availability
- subscription-service availability
- prices
- editions
- pre-order bonuses
- platforms
- physical editions
- regional availability
- exclusivity
- free-to-play status


IF AN OFFICIAL VERIFICATION SOURCE IS PROVIDED:

You may state these claims as facts ONLY when
the official source supports them.

If the discovery source and official source conflict,
the OFFICIAL SOURCE always wins.


IF NO OFFICIAL VERIFICATION SOURCE IS PROVIDED:

A high-risk claim coming only from a secondary source
must NOT be presented as an independently confirmed fact.

Instead, explicitly attribute it to the source.

Examples:

WRONG:
"The game will launch day one on Xbox Game Pass."

CORRECT:
"Selon IGN, le jeu devrait rejoindre Xbox Game Pass
dès son lancement."

WRONG HEADLINE:
"RuneScape Dragonwilds arrives on Game Pass day one"

SAFER HEADLINE:
"RuneScape Dragonwilds sortira le 15 septembre"

Do NOT build the headline primarily around an
unverified high-risk claim.

Do NOT put an unverified high-risk claim in the excerpt
without explicit attribution.

If reliable attribution would make the article confusing,
simply omit the claim.


OFFICIAL CONFIRMATION LANGUAGE:

Never use phrases such as:

- "Jagex confirme"
- "Sony confirme"
- "Microsoft confirme"
- "Nintendo confirme"
- "le studio confirme"
- "l'éditeur confirme"

unless the supplied official source actually confirms
that specific claim.

A secondary publication reporting something does NOT
count as confirmation from the developer, publisher,
platform holder or manufacturer.


================================================
NEVER INVENT
================================================

Never invent:

- release dates
- prices
- platforms
- multiplayer
- single-player
- technical specifications
- gameplay mechanics
- quotes
- sales numbers
- reviews
- player reactions
- availability
- developer intentions
- geographic availability

Do NOT use your memory.


================================================
INTERPRETATION SAFETY
================================================

Never reinterpret branded terminology.

If the source names something like:

Cap Breakers

retain the official term unless
the source itself explains its meaning.

Never guess.


================================================
EDITORIAL RULES
================================================

- Write natural professional French.
- Do not copy source paragraphs.
- Do not imitate the publication's style.
- No clickbait.
- No filler.
- No invented conclusion.
- Use meaningful H2 headings.
- Use bullet lists only when useful.
- Preserve official names.
- Be geographically precise.
- Accuracy beats length.
- If information is limited,
  write a shorter article.

Normally target 400–700 words.

Use 250–400 words when the source
does not justify more.


================================================
SOURCE TRANSPARENCY
================================================

At the end, naturally cite/link
the discovery source.

If an official verification source
was used, also identify it.


================================================
RETURN EXACTLY
================================================

TITLE: [French headline]

EXCERPT: [20–35 word factual summary]

CATEGORY: [one of: Actualités, Guides, Sélections, Tests & Avis]

TAGS: [3–6 comma-separated useful tags]

CONTENT:
[HTML only. No markdown code fences.]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",

        messages=[
            {
                "role": "system",
                "content": (
                    "You are a conservative French "
                    "gaming journalist. "
                    "Accuracy always beats completeness."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        temperature=0.15,
    )

    return (
        response
        .choices[0]
        .message
        .content
    )


# =========================================================
# PARSE ARTICLE
# =========================================================

def parse_article(text):
    text = strip_code_fences(
        text
    )

    try:

        title = (
            text
            .split("TITLE:", 1)[1]
            .split("EXCERPT:", 1)[0]
            .strip()
        )

        excerpt = (
            text
            .split("EXCERPT:", 1)[1]
            .split("CATEGORY:", 1)[0]
            .strip()
        )

        category = (
            text
            .split("CATEGORY:", 1)[1]
            .split("TAGS:", 1)[0]
            .strip()
        )

        tags = (
            text
            .split("TAGS:", 1)[1]
            .split("CONTENT:", 1)[0]
            .strip()
        )

        content = (
            text
            .split("CONTENT:", 1)[1]
            .strip()
        )

    except Exception:

        raise RuntimeError(
            "Generated article "
            "could not be parsed."
        )

    content = strip_code_fences(
        content
    )

    allowed_categories = {
        "Actualités",
        "Guides",
        "Sélections",
        "Tests & Avis",
    }

    if category not in allowed_categories:
        category = "Actualités"

    if (
        not title
        or not excerpt
        or not content
    ):
        raise RuntimeError(
            "Generated article is missing "
            "required fields."
        )

    return (
        title,
        excerpt,
        category,
        tags,
        content
    )


# =========================================================
# FACT CHECK — GATE 2
# =========================================================

def fact_check_draft(
    title,
    excerpt,
    content,
    source_text,
    story,
    official_text=""
):
    print("")
    print(
        "RUNNING FINAL FACT CHECK..."
    )

    client = Groq(
        api_key=GROQ_API_KEY
    )

    verification_source = ""

    if official_text:

        verification_source = f"""

OFFICIAL VERIFICATION SOURCE:

{official_text}

"""

    prompt = f"""
You are GamerQuest's final fact-checker.

Compare the GENERATED ARTICLE
against the supplied source material.

DISCOVERY SOURCE:

{source_text}


{verification_source}


GENERATED TITLE:

{title}


GENERATED EXCERPT:

{excerpt}


GENERATED ARTICLE:

{content}


================================================
CHECK EVERY MATERIAL CLAIM
================================================

Look specifically for:

- wrong dates
- invented dates
- wrong platforms
- invented platforms
- wrong prices
- invented multiplayer
- invented single-player
- wrong game features
- invented features
- incorrect branded terminology
- invented technical specifications
- unsupported availability
- invented quotes
- wrong names
- stronger claims than the source supports


================================================
HIGH-RISK CLAIM AUDIT
================================================

High-risk claims include:

- release dates
- early-access dates
- subscription availability
- Xbox Game Pass
- PlayStation Plus
- prices
- editions
- platforms
- physical releases
- pre-order bonuses
- exclusivity
- regional availability

If an official verification source exists:

Verify every high-risk claim against that official source.

If the official source contradicts the discovery source,
REJECT the draft unless the article follows the official
source.


If NO official verification source exists:

High-risk claims from the secondary discovery source
must be clearly attributed to that source.

Example:

"Selon IGN..."

is acceptable.

Presenting the same secondary-source claim as independently
confirmed fact is NOT acceptable.

The TITLE and EXCERPT must also follow this rule.

REJECT the article if its headline presents an unverified
high-risk secondary-source claim as confirmed fact.

Also REJECT statements such as:

"Jagex confirme..."
"Sony confirme..."
"Microsoft confirme..."
"Nintendo confirme..."

when no supplied official source supports that attribution.


================================================
VERDICT
================================================

If EVERY material factual claim is
supported by the supplied evidence,
return exactly:

APPROVED


If ANY material claim is unsupported,
return:

REJECTED

Then briefly list the problematic claims.


Do not approve something merely because
it sounds plausible.
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",

        messages=[
            {
                "role": "system",
                "content": (
                    "You are an extremely conservative "
                    "gaming fact-checker."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        temperature=0,
    )

    verdict = (
        response
        .choices[0]
        .message
        .content
        .strip()
    )

    print("")
    print(
        "FACT CHECK RESULT:"
    )

    print(
        verdict
    )

    return (
        verdict
        .upper()
        .startswith(
            "APPROVED"
        )
    )


# =========================================================
# SAVE APPROVED DRAFT
# =========================================================

def save_draft(
    title,
    excerpt,
    category,
    tags,
    content,
    story,
    official_story=None
):

    DRAFTS_FOLDER.mkdir(
        exist_ok=True
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d-%H%M"
    )

    filename = (
        DRAFTS_FOLDER
        / f"{timestamp}-{slugify(title)}.md"
    )

    verification = (
        "No matching official source "
        "was found in the same search."
    )

    if official_story:

        verification = (
            f"{official_story.get('title', '')}\n\n"
            f"{official_story.get('url', '')}"
        )

    markdown = f"""# {title}

## Excerpt

{excerpt}

## Category

{category}

## Tags

{tags}

## Article

{content}

## Discovery source

{get_domain(story.get('url', ''))}

## Source title

{story.get('title', '')}

## Source URL

{story.get('url', '')}

## Source date

{story.get('published_date', '')}

## Verification source

{verification}

## Validation

Source validation: PASSED

Fact-check: PASSED

## Status

DRAFT - HUMAN REVIEW REQUIRED BEFORE PUBLISHING
"""

    filename.write_text(
        markdown,
        encoding="utf-8"
    )

    print("")
    print("===================================")
    print("APPROVED DRAFT CREATED")
    print("===================================")
    print(filename)


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "==================================="
    )

    print(
        "GamerQuest Automation V6"
    )

    print(
        "==================================="
    )

    results = search_gaming_news()

    story = select_best_story(
        results
    )

    source_text = extract_page(
        story
    )

    if not validate_source(
        story,
        source_text
    ):

        print("")
        print(
            "Automation stopped safely."
        )

        print(
            "No article created."
        )

        sys.exit(0)

    official_story = (
        find_matching_official_source(
            story,
            results
        )
    )

    official_text = ""

    if official_story:

        print("")
        print(
            "OFFICIAL MATCH FOUND:"
        )

        print(
            official_story.get(
                "url",
                ""
            )
        )

        official_text = extract_page(
            official_story
        )

    else:

        print("")
        print(
            "No matching official source "
            "found in the same Tavily search."
        )

    generated = generate_article(
        story,
        source_text,
        official_story,
        official_text
    )

    (
        title,
        excerpt,
        category,
        tags,
        content
    ) = parse_article(
        generated
    )

    approved = fact_check_draft(
        title,
        excerpt,
        content,
        source_text,
        story,
        official_text
    )

    if not approved:

        print("")
        print(
            "Draft rejected by fact-check."
        )

        print(
            "Nothing was saved."
        )

        sys.exit(0)

    save_draft(
        title,
        excerpt,
        category,
        tags,
        content,
        story,
        official_story
    )

    print("")
    print(
        "Automation completed successfully."
    )


if __name__ == "__main__":
    main()
