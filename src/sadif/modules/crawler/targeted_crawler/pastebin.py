from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from pymongo import MongoClient
from requests import RequestException

from sadif.frameworks_drivers.crawler.base_crawler import BaseCrawler


class PastebinPLCrawler(BaseCrawler):
    """
    A crawler for Pastebin.pl, inheriting from BaseCrawler, to fetch and analyze pastes.

    This crawler navigates through Pastebin.pl lists, extracts pastes, and optionally
    analyzes their content.

    Attributes
    ----------
    base_url : str
        The base URL to start crawling from.
    depth : int
        The maximum depth to crawl.
    proxy : str, optional
        A proxy URL to be used for requests.
    timeout : int
        The timeout for requests in seconds.
    db_client : MongoClient, optional
        The database client for storing crawl results.

    Methods
    -------
    __init__(self, base_url="https://pastebin.pl/lists", depth=1, proxy=None, timeout=10, db_client=None)
        Initializes the crawler with the base URL, crawl depth, proxy, timeout, and database client.

    extract_pastes(self, content, current_url)
        Extracts pastes from a Pastebin.pl list page.

    crawl(self, url, current_depth=0)
        Recursively crawls the given URL to the specified depth, extracts pastes, and analyzes their content.

    analyze_paste(self, paste_url)
        Analyzes the content of a single paste. This method is intended to be overridden by subclasses
        to implement specific analysis logic.
    """

    def __init__(
        self,
        base_url: str = "https://pastebin.pl/lists",
        depth: int = 1,
        proxy: str | None = None,
        timeout: int = 10,
        db_client: MongoClient | None = None,
    ) -> None:
        """
        Initializes the PastebinPLCrawler instance with base URL, crawl depth, proxy,
        timeout, and an optional MongoDB client for storing results.

        Parameters
        ----------
        base_url : str
            The starting URL for the crawl.
        depth : int
            Maximum crawl depth.
        proxy : Optional[str]
            Proxy configuration for requests.
        timeout : int
            Timeout for HTTP requests in seconds.
        db_client : Optional[MongoClient]
            MongoDB client for storing crawl results.
        """
        super().__init__(base_url, depth, proxy, timeout, db_client)
        self.found_pastes: list[dict[str, str]] = []
        self.paste_analysis: dict[str, list[dict[str, Any]]] = {}

    def extract_pastes(self, content: bytes, current_url: str) -> list[dict[str, str]]:
        """
        Extracts paste URLs and titles from the HTML content of a Pastebin.pl list page.

        Parameters
        ----------
        content : bytes
            The HTML content of the page.
        current_url : str
            The URL of the page being processed.

        Returns
        -------
        List[Dict[str, str]]
            A list of dictionaries, each containing the 'url' and 'title' of a paste
            (each paste URL appears only once).
        """
        soup = BeautifulSoup(content, "html.parser")
        pastes = []
        seen = set()
        for paste_link in soup.find_all("a", href=True):
            if "/view/" in paste_link["href"]:  # Identify paste links
                full_url = self.normalize_link(paste_link["href"], current_url)
                if full_url in seen:
                    continue
                seen.add(full_url)
                title = paste_link.text.strip()
                pastes.append({"url": full_url, "title": title})
        return pastes

    def extract_list_pages(self, content: bytes, current_url: str) -> set[str]:
        """
        Extracts the links to other list pages (e.g. pagination) of the same site.

        Parameters
        ----------
        content : bytes
            The HTML content of the page.
        current_url : str
            The URL of the page being processed.

        Returns
        -------
        Set[str]
            URLs on the same host as ``base_url`` whose path is the list path.
        """
        base = urlparse(self.base_url)
        list_pages = set()
        for link in self.extract_links(content, current_url):
            parsed = urlparse(link)
            if parsed.netloc == base.netloc and parsed.path.rstrip("/") == base.path.rstrip("/"):
                list_pages.add(link)
        return list_pages

    def crawl(self, url: str, current_depth: int = 0) -> None:
        """
        Crawls pages from Pastebin.pl, extracts pastes, and optionally analyzes them.
        This method manages recursion based on the specified depth and keeps track of visited URLs.

        Parameters
        ----------
        url : str
            The URL to crawl.
        current_depth : int
            The current depth of the crawl.

        Notes
        -----
        The found pastes are stored in ``found_pastes`` and the non-empty analysis
        results in ``paste_analysis`` (``{paste_url: matches}``). List pages that
        link to other list pages of the same site (pagination) are followed while
        ``current_depth < depth``.
        """
        url = self.normalize_link(url, url)
        with self._visited_lock:
            if current_depth > self.depth or url in self.visited_urls:
                return
            self.visited_urls.add(url)
        try:
            response = self.session.get(
                url, proxies={"http": self.proxy, "https": self.proxy}, timeout=self.timeout
            )
            if response.status_code >= 400:
                self.error_urls.add(url)
                self.log_manager.log(
                    "warning", f"HTTP {response.status_code} while crawling {url}.", "network"
                )
                return
            pastes = self.extract_pastes(response.content, url)
            with self._visited_lock:
                pastes = [paste for paste in pastes if paste["url"] not in self.visited_urls]
                self.visited_urls.update(paste["url"] for paste in pastes)
            self.found_pastes.extend(pastes)
            self.log_manager.log("info", f"{len(pastes)} paste(s) found at {url}", "crawler")
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_paste = {
                    executor.submit(self.analyze_paste, paste["url"]): paste for paste in pastes
                }
                for future in as_completed(future_to_paste):
                    paste = future_to_paste[future]  # Get the paste corresponding to this future
                    paste_analysis = future.result()
                    if paste_analysis:  # If there's anything significant found in the analysis
                        self.paste_analysis[paste["url"]] = paste_analysis
                        self.log_manager.log(
                            "info",
                            f"{len(paste_analysis)} match(es) in paste {paste['url']}",
                            "crawler",
                        )
            if current_depth < self.depth:
                for list_page in sorted(self.extract_list_pages(response.content, url)):
                    self.crawl(list_page, current_depth + 1)
        except RequestException as e:
            self.error_urls.add(url)
            self.log_manager.log("warning", f"Error crawling {url}: {e}", "network")

    def analyze_paste(self, paste_url: str) -> Any | None:
        """
        Analyzes the content of a single paste. This method can be overridden to implement
        specific analysis, such as applying Yara rules or keyword searching.

        Parameters
        ----------
        paste_url : str
            The URL of the paste to analyze.

        Returns
        -------
        Optional[Any]
            The result of the analysis, which could be a list of matches, a boolean value,
            or any other data structure depending on the implementation.

        Notes
        -----
        Request errors and HTTP error statuses are logged and return None.
        """
        try:
            response = self.session.get(
                paste_url, proxies={"http": self.proxy, "https": self.proxy}, timeout=self.timeout
            )
        except RequestException as e:
            self.error_urls.add(paste_url)
            self.log_manager.log("warning", f"Error analyzing paste {paste_url}: {e}", "network")
            return None
        if response.status_code >= 400:
            self.error_urls.add(paste_url)
            self.log_manager.log(
                "warning", f"HTTP {response.status_code} for paste {paste_url}.", "network"
            )
            return None
        # Here, we could apply the Yara rules or any other analysis
        return self.analyze_content(response.text, paste_url)
