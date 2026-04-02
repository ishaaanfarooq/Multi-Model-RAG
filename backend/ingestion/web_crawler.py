import asyncio
import re
from urllib.parse import urljoin, urlparse
from typing import AsyncGenerator
import json
import logging

import requests
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

class WebCrawler:
    """
    A BFS-based website crawler that extracts text content from web pages,
    chunks it, and returns LangChain Document objects ready for FAISS ingestion.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MultiModelRAG-Crawler/1.0 (Educational Project)"
        })

    def _get_base_domain(self, url: str) -> str:
        """Extract the base domain to restrict crawling to same-domain links."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _is_valid_url(self, url: str, base_domain: str) -> bool:
        """Check if a URL is valid and belongs to the same domain."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            if not url.startswith(base_domain):
                return False
            # Skip common non-content URLs
            skip_extensions = (
                ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg",
                ".css", ".js", ".ico", ".woff", ".woff2", ".ttf",
                ".mp4", ".mp3", ".zip", ".tar", ".gz",
            )
            if any(parsed.path.lower().endswith(ext) for ext in skip_extensions):
                return False
            # Skip fragments and mailto
            if parsed.fragment and not parsed.path:
                return False
            return True
        except Exception:
            return False

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """Extract clean, visible text from a BeautifulSoup parsed page."""
        # Remove script, style, nav, footer, header elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            element.decompose()

        # Get text content
        text = soup.get_text(separator="\n", strip=True)
        
        # Clean up excessive whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = "\n".join(lines)
        
        # Remove lines that are too short to be meaningful content (e.g. Nav elements)
        meaningful_lines = [line for line in text.split("\n") if len(line) > 15 or line.endswith((".", "!", "?", ":", ","))]
        
        return "\n".join(meaningful_lines)

    def _extract_links(self, soup: BeautifulSoup, current_url: str, base_domain: str) -> list[str]:
        """Extract all valid same-domain links from the page."""
        links = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            # Resolve relative URLs
            absolute_url = urljoin(current_url, href)
            # Remove fragments
            absolute_url = absolute_url.split("#")[0].rstrip("/")
            if self._is_valid_url(absolute_url, base_domain) and absolute_url not in links:
                links.append(absolute_url)
        return links

    def _fetch_page(self, url: str) -> tuple[str | None, str | None]:
        """Fetch a single page. Returns (html_content, error)."""
        try:
            response = self.session.get(url, timeout=10, allow_redirects=True)
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return None, f"Non-HTML content type: {content_type}"
            response.raise_for_status()
            return response.text, None
        except requests.RequestException as e:
            return None, str(e)

    def crawl_sync(self, start_url: str, max_pages: int = 20, max_depth: int = 2) -> list[Document]:
        """
        Synchronous BFS crawl. Returns list of LangChain Documents.
        """
        base_domain = self._get_base_domain(start_url)
        visited = set()
        # Queue: (url, depth)
        queue = [(start_url.rstrip("/"), 0)]
        all_documents = []

        while queue and len(visited) < max_pages:
            url, depth = queue.pop(0)
            
            if url in visited:
                continue
            if depth > max_depth:
                continue

            visited.add(url)

            html, error = self._fetch_page(url)
            if error or not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else url
            text = self._extract_text(soup)

            if len(text) < 200:
                try:
                    jina_resp = requests.get(f"https://r.jina.ai/{url}", timeout=15)
                    if jina_resp.ok and len(jina_resp.text) > len(text):
                        text = jina_resp.text
                        first_line = text.split("\n")[0]
                        if first_line.startswith("Title: "):
                            title = first_line.replace("Title: ", "").strip()
                except Exception:
                    pass

            if len(text) < 50:
                # Skip pages with very little content
                continue

            # Chunk the text
            chunks = self.text_splitter.split_text(text)
            for i, chunk in enumerate(chunks):
                doc = Document(
                    page_content=chunk,
                    metadata={
                        "source": url,
                        "title": title,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                    },
                )
                all_documents.append(doc)

            # Discover new links (only if we haven't hit max depth)
            if depth < max_depth:
                new_links = self._extract_links(soup, url, base_domain)
                for link in new_links:
                    if link not in visited:
                        queue.append((link, depth + 1))

        return all_documents

    async def crawl_stream(
        self, start_url: str, max_pages: int = 20, max_depth: int = 2
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that yields SSE-formatted JSON events during crawling.
        Also ingests documents into the provided vector_db at the end.
        Returns the documents list via the final event.
        """
        base_domain = self._get_base_domain(start_url)
        visited = set()
        queue = [(start_url.rstrip("/"), 0)]
        all_documents = []
        pages_crawled = 0

        def emit(status, page_url="", pages_done=0, total_found=0, message="", documents=None):
            data = {
                "status": status,
                "page_url": page_url,
                "pages_done": pages_done,
                "total_found": total_found,
                "message": message,
            }
            if documents is not None:
                data["total_chunks"] = documents
            return json.dumps(data)

        yield emit("started", start_url, 0, 1, f"Starting crawl of {start_url}")

        while queue and len(visited) < max_pages:
            url, depth = queue.pop(0)
            
            if url in visited:
                continue
            if depth > max_depth:
                continue

            visited.add(url)
            pages_crawled += 1

            yield emit("crawling", url, pages_crawled, len(queue) + pages_crawled, f"Fetching: {url}")
            
            # Run blocking I/O in thread pool
            html, error = await asyncio.to_thread(self._fetch_page, url)
            
            if error or not html:
                yield emit("page_error", url, pages_crawled, len(queue) + pages_crawled, f"Skipped: {error}")
                continue

            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else url
            text = self._extract_text(soup)

            if len(text) < 200:
                try:
                    jina_resp = await asyncio.to_thread(requests.get, f"https://r.jina.ai/{url}", timeout=15)
                    if jina_resp.ok and len(jina_resp.text) > len(text):
                        text = jina_resp.text
                        first_line = text.split("\n")[0]
                        if first_line.startswith("Title: "):
                            title = first_line.replace("Title: ", "").strip()
                except Exception as e:
                    logger.warning(f"Jina fallback failed for {url}: {e}")

            if len(text) < 50:
                yield emit("page_skip", url, pages_crawled, len(queue) + pages_crawled, f"Skipped (low content): {title}")
                continue

            chunks = self.text_splitter.split_text(text)
            for i, chunk in enumerate(chunks):
                doc = Document(
                    page_content=chunk,
                    metadata={
                        "source": url,
                        "title": title,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                    },
                )
                all_documents.append(doc)

            yield emit("page_done", url, pages_crawled, len(queue) + pages_crawled, f"Crawled: {title} ({len(chunks)} chunks)")

            if depth < max_depth:
                new_links = self._extract_links(soup, url, base_domain)
                added = 0
                for link in new_links:
                    if link not in visited:
                        queue.append((link, depth + 1))
                        added += 1
                if added > 0:
                    yield emit("links_found", url, pages_crawled, len(queue) + pages_crawled, f"Discovered {added} new links")

            # Small delay to be polite to servers
            await asyncio.sleep(0.3)

        yield emit("completed", start_url, pages_crawled, pages_crawled, f"Crawl complete! {pages_crawled} pages, {len(all_documents)} chunks", len(all_documents))
