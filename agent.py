"""Task-automation agent: web search (DuckDuckGo) -> 3-bullet brief (Gemini)."""
import logging
import os
import re
import sys
import time

APP_VERSION = "1.0"

# ---------- logging: goes to stdout so Docker / Hugging Face / Render show it ----------
logger = logging.getLogger("agent")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# Tried in order; if one is unavailable / out of quota the next one is used.
MODEL_CANDIDATES = [
    m for m in [os.getenv("GEMINI_MODEL"), "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-2.5-flash"] if m
]
MAX_TOPIC_CHARS = 200

SYSTEM_PROMPT = (
    "You are a careful research assistant. You will receive a topic and raw web search results. "
    "Write a brief of EXACTLY three bullet points using only the information in the results. "
    "Rules: each bullet is 1-2 sentences and starts with '- '; cover three different aspects "
    "(for example what is new, why it matters, what to watch next); include a concrete fact or number "
    "when the results contain one; do not invent facts; no introduction, no conclusion, no extra text."
)
HUMAN_PROMPT = "Topic: {topic}\n\nSearch results:\n{results}\n\nWrite the three-bullet brief now."


# ----------------------------- Stage 1: search -----------------------------
def format_results(hits):
    """Turn a list of search hits (dicts) into plain text."""
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] {h.get('title', '')}\n{h.get('body', '')}\nSource: {h.get('href') or h.get('url', '')}")
    return "\n\n".join(blocks)


def search_web(topic, max_results=6):
    """Query DuckDuckGo (with fallback methods) and return the raw results as text."""
    try:
        from ddgs import DDGS  # new package name
    except ImportError:
        from duckduckgo_search import DDGS  # old package name

    # Quotes/apostrophes (e.g. "India's") can make a search return nothing -> strip them.
    query = re.sub("['\u2019]s\\b", "", topic)  # India's -> India
    query = re.sub("[\"'\u2018\u2019\u201c\u201d]", "", query).strip()
    short_query = " ".join(query.split()[:4])
    strategies = [
        ("text", lambda d, q: d.text(q, max_results=max_results, region="wt-wt")),
        ("text/bing", lambda d, q: d.text(q, max_results=max_results, backend="bing")),
        ("text/brave", lambda d, q: d.text(q, max_results=max_results, backend="brave")),
        ("news", lambda d, q: d.news(q, max_results=max_results)),
    ]
    last_error = None
    for q in dict.fromkeys([query, short_query]):
        for name, fn in strategies:
            try:
                with DDGS() as ddgs:
                    hits = list(fn(ddgs, q))
                if hits:
                    logger.info("search OK via %s | query=%r | %d hits", name, q, len(hits))
                    return format_results(hits)
                last_error = RuntimeError("no results")
            except Exception as exc:  # rate limit, no results, network
                last_error = exc
            logger.warning("search via %s failed for %r: %s", name, q, str(last_error)[:150])
            time.sleep(1)
    raise RuntimeError(f"Web search failed with every method. Last error: {last_error}")


# --------------------------- Stage 2: summarize ----------------------------
def _to_text(content):
    """Gemini may return a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type", "text") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def extract_bullets(text):
    """Pull bullet items out of model text (handles -, *, bullet dots, 1. and wrapped lines)."""
    bullets = []
    for line in text.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^\s*(?:[-*\u2022]|\d+[.)])\s+(.*\S)\s*$", line)
        if m:
            bullets.append(m.group(1).strip())
        elif bullets:  # wrapped continuation of the previous bullet
            bullets[-1] += " " + line.strip()
    return bullets


def _call_gemini(topic, results, temperature):
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set. Add it as an environment variable / secret.")

    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)])
    last_error = None
    for model in MODEL_CANDIDATES:
        try:
            llm = ChatGoogleGenerativeAI(
                model=model, temperature=temperature, google_api_key=api_key, max_retries=1
            )
            reply = (prompt | llm).invoke({"topic": topic, "results": results})
            logger.info("model used: %s", model)
            return _to_text(reply.content)
        except Exception as exc:
            last_error = exc
            logger.warning("model %s failed: %s", model, str(exc)[:200])
    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")


def summarize(topic, results, temperature=0.3):
    """Return exactly three '- ' bullets."""
    bullets = []
    for attempt in (1, 2):
        bullets = extract_bullets(_call_gemini(topic, results, temperature))
        if len(bullets) >= 3:
            break
        logger.warning("model returned %d bullets (attempt %d), retrying", len(bullets), attempt)
    if len(bullets) < 3:
        raise RuntimeError("The model did not return three bullet points.")
    return "\n".join(f"- {b}" for b in bullets[:3])


# ------------------------------ Workflow -----------------------------------
def run_workflow(topic, temperature=0.3, progress=print):
    """search -> summarize, with progress messages and logging. Input: just the topic."""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("Please enter a topic.")
    if len(topic) > MAX_TOPIC_CHARS:
        raise ValueError(f"Topic is too long (max {MAX_TOPIC_CHARS} characters).")

    logger.info("request received | topic=%r | temperature=%s", topic, temperature)
    start = time.perf_counter()
    try:
        progress("\U0001F50E Stage 1/2: searching the web...")
        raw = search_web(topic)
        progress(f"   search finished ({len(raw)} characters of results)")
        progress("\U0001F4DD Stage 2/2: summarizing with Gemini...")
        brief = summarize(topic, raw, temperature)
        progress("\u2705 Workflow complete.")
    except Exception:
        logger.exception("request FAILED | topic=%r | after %.2fs", topic, time.perf_counter() - start)
        raise
    logger.info("request OK | topic=%r | time_taken=%.2fs", topic, time.perf_counter() - start)
    return brief
