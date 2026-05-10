import logging
import asyncio
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def _extract_structured_text(soup: BeautifulSoup) -> str:
    """Extract text while preserving table structure as Markdown."""
    # Process tables first
    for table in soup.find_all("table"):
        markdown_table = []
        for row in table.find_all("tr"):
            cells = [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
            if cells:
                markdown_table.append("| " + " | ".join(cells) + " |")
        
        # Replace table with its markdown string
        if markdown_table:
            table_text = "\n" + "\n".join(markdown_table) + "\n"
            table.replace_with(table_text)

    # Remove noise
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """Try DuckDuckGo HTML search (no API key, scrapes HTML endpoint)."""
    results = []
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=HEADERS,
            timeout=10,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        for result in soup.select(".result__body")[:max_results]:
            title_el = result.select_one(".result__title a")
            snippet_el = result.select_one(".result__snippet")
            if title_el and snippet_el:
                href = title_el.get("href", "")
                # DDG uses redirect links — extract real URL
                if "uddg=" in href:
                    from urllib.parse import unquote, urlparse, parse_qs
                    qs = parse_qs(urlparse(href).query)
                    href = unquote(qs.get("uddg", [""])[0])
                results.append({
                    "title": title_el.get_text(strip=True),
                    "href": href,
                    "body": snippet_el.get_text(strip=True),
                })
    except Exception as e:
        logger.warning(f"DuckDuckGo HTML search failed: {e}")
    return results


def _search_wikipedia_rest(query: str, max_results: int = 4) -> list[dict]:
    """Use Wikipedia's REST summary API — more reliable than opensearch."""
    results = []
    try:
        # Step 1: search for page titles via the search API
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": max_results,
                "format": "json",
            },
            headers=HEADERS,
            timeout=10,
        )
        data = resp.json()
        search_hits = data.get("query", {}).get("search", [])

        for hit in search_hits:
            title = hit["title"]
            try:
                ext_resp = requests.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "titles": title,
                        "prop": "extracts",
                        "exsentences": 20,
                        "explaintext": True,
                        "format": "json",
                    },
                    headers=HEADERS,
                    timeout=10,
                )
                pages = ext_resp.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    extract = page.get("extract", "")
                    if extract and len(extract) > 50:
                        url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                        results.append({
                            "title": title,
                            "href": url,
                            "body": extract[:2500],
                        })
            except Exception as inner_e:
                logger.debug(f"Wikipedia extract failed for {title}: {inner_e}")

    except Exception as e:
        logger.error(f"Wikipedia REST search failed: {e}")
    return results


def _search_google_news_rss(query: str, max_results: int = 4) -> list[dict]:
    """Scrape Google News RSS as a third-tier fallback — no key needed."""
    results = []
    try:
        rss_url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(rss_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")[:max_results]
        for item in items:
            title = item.find("title")
            desc  = item.find("description")
            link  = item.find("link")
            if title and desc:
                body = BeautifulSoup(desc.get_text(), "html.parser").get_text(strip=True)
                results.append({
                    "title": title.get_text(strip=True),
                    "href":  link.get_text(strip=True) if link else "",
                    "body":  body[:800],
                })
    except Exception as e:
        logger.error(f"Google News RSS fallback failed: {e}")
    return results


async def _fetch_and_extract(url: str) -> str:
    """Fetch a page and extract structured text."""
    try:
        resp = await asyncio.to_thread(requests.get, url, headers=HEADERS, timeout=10)
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            soup = BeautifulSoup(resp.text, "html.parser")
            return _extract_structured_text(soup)
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
    return ""


async def search_web(query: str, max_results: int = 5) -> tuple[list[str], list[str]]:
    """
    Tries DuckDuckGo HTML → Wikipedia REST API → Google News RSS.
    Visits the top links to extract full structured content (tables preserved).
    Returns (doc_texts, sources).
    """
    # Try DDG HTML first
    results = await asyncio.to_thread(_search_duckduckgo, query, max_results)
    source_label = "DuckDuckGo"

    if not results:
        logger.warning("DuckDuckGo HTML search returned no results. Trying Wikipedia REST API...")
        results = await asyncio.to_thread(_search_wikipedia_rest, query, max_results)
        source_label = "Wikipedia"

    if not results:
        logger.warning("Wikipedia fallback returned no results. Trying Google News RSS...")
        results = await asyncio.to_thread(_search_google_news_rss, query, max_results)
        source_label = "Google News RSS"

    if not results:
        logger.error("All web search sources exhausted — no results found.")
        return [], []

    # Visit top 3 results to get FULL content (important for tables/fees)
    full_docs = []
    final_sources = []
    
    # We take top 3 for full crawl to balance speed and depth
    top_results = results[:3]
    
    tasks = [_fetch_and_extract(r["href"]) for r in top_results]
    extracted_texts = await asyncio.gather(*tasks)

    for i, text in enumerate(extracted_texts):
        if text and len(text) > 200:
            full_docs.append(text[:5000]) # Cap at 5k chars per doc
            final_sources.append(top_results[i]["href"])
        else:
            # Fallback to snippet if fetch failed or content was too short
            full_docs.append(top_results[i]["body"])
            final_sources.append(top_results[i]["href"])

    logger.info(f"Web search ({source_label}) → {len(full_docs)} results for: {query}")
    return full_docs, final_sources
