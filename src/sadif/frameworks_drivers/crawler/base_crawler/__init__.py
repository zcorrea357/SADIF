import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from requests import RequestException

from sadif.config.sadif_config import SadifConfiguration
from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.sadif_yara.yara_compiler import SadifYaraCompiler
from sadif.frameworks_drivers.web.authenticator.basic_auth_strategy import BasicAuthStrategy
from sadif.frameworks_drivers.web.authenticator.bearer_auth_strategy import BearerAuthStrategy
from sadif.frameworks_drivers.web.authenticator.digest_auth_strategy import DigestAuthStrategy

CRAWLABLE_SCHEMES = ("http", "https")


class BaseCrawler:
    """
    Base class for performing website crawling, with support for authentication,
    link extraction, content analysis with YARA, and log management.

    Parameters
    ----------
    base_url : str
        Base URL to start crawling.
    depth : int
        Maximum crawling depth.
    proxy : Optional[str], default None
        Proxy to be used in HTTP requests.
    timeout : int, default 10
        Maximum time (in seconds) for HTTP requests.
    db_client : Optional[MongoClient], default None
        MongoDB client for storing crawling results. If None,
        it connects to the configured ``MONGODB_URL``.

    Attributes
    ----------
    base_url : str
        Base URL for crawling.
    depth : int
        Maximum depth for crawling.
    session : requests.Session
        HTTP session for making requests.
    proxy : Optional[str]
        Proxy used in requests.
    timeout : int
        Timeout for requests.
    client : MongoClient
        MongoDB client for database operations.
    yara_compiler : SadifYaraCompiler
        YARA compiler for content analysis.
    visited_urls : Set[str]
        Set of already visited URLs.
    log_manager : LogManager
        Log manager for recording crawler activities.
    module_name : str
        Module or class name.
    log_message : str
        Log message for initialization.
    yara_matches : List[Dict[str, Any]]
        List of matches found by YARA analysis.
    error_urls : Set[str]
        URLs that answered with an HTTP error status (>= 400) or failed; their
        content is neither analyzed nor followed.
    """

    def __init__(
        self,
        base_url: str,
        depth: int,
        proxy: str | None = None,
        timeout: int = 10,
        db_client: MongoClient | None = None,
    ):
        """
        Initializes the crawler instance with basic configurations and database connection.
        """

        self.base_url = base_url
        self.depth = depth
        self.session = requests.Session()
        self.proxy = proxy
        self.timeout = timeout
        self.client = (
            db_client
            if db_client is not None
            else MongoClient(SadifConfiguration().get_configuration("MONGODB_URL"))
        )
        self.yara_compiler = SadifYaraCompiler(self.client)
        self.visited_urls = set()
        self.error_urls = set()
        self._visited_lock = threading.Lock()
        self._yara_lock = threading.Lock()
        self.log_manager = LogManager()
        self.module_name = self.__class__.__name__
        self.log_message = f"{self.module_name} initialized with base_url: {base_url}"
        self.log_manager.log("info", self.log_message, "crawler")
        self.yara_matches = []

    def authenticate(self, auth_details: dict[str, str]) -> None:
        """
        Performs authentication on the target website, if necessary.

        Parameters
        ----------
        auth_details : Dict[str, str]
            Details required for authentication: ``{"token": ...}`` (bearer),
            ``{"username": ..., "password": ...}`` (basic) or the same with
            ``"type": "digest"``. ``"type"`` may also be ``"basic"`` or ``"bearer"``.

        Raises
        ------
        ValueError
            If the details do not describe a supported authentication.
        """

        auth_type = (auth_details.get("type") or "").lower()
        if not auth_type:
            auth_type = "bearer" if auth_details.get("token") else "basic"
        if auth_type == "bearer" and auth_details.get("token"):
            strategy = BearerAuthStrategy(auth_details["token"])
        elif (
            auth_type in ("basic", "digest")
            and auth_details.get("username")
            and auth_details.get("password") is not None
        ):
            strategy_class = DigestAuthStrategy if auth_type == "digest" else BasicAuthStrategy
            strategy = strategy_class(auth_details["username"], auth_details["password"])
        else:
            self.log_manager.log(
                "error", f"Invalid authentication details for {self.base_url}.", "security"
            )
            msg = "auth_details must contain 'token' or 'username' and 'password'."
            raise ValueError(msg)
        self.session = strategy.authenticate(self.session)
        self.log_manager.log("info", f"Authentication ({auth_type}) configured.", "security")

    def crawl(self, url: str, current_depth: int = 0) -> None:
        """
        Executes the crawling process starting from a specific URL,
        while respecting the defined maximum depth and avoiding repeated URLs.

        Parameters
        ----------
        url : str
            Initial URL for crawling.
        current_depth : int, default 0
            Current depth of crawling.
        """

        url = self.normalize_link(url, url)
        with self._visited_lock:
            if current_depth > self.depth or url in self.visited_urls:
                self.log_manager.log(
                    "warning", f"URL already visited or depth exceeded: {url}", "crawler"
                )
                return
            self.visited_urls.add(url)
        try:
            response = self.session.get(
                url, proxies={"http": self.proxy, "https": self.proxy}, timeout=self.timeout
            )
            if response.status_code >= 400:
                self.error_urls.add(url)
                self.log_manager.log(
                    "warning",
                    f"HTTP {response.status_code} while crawling {url}. Skipping...",
                    "network",
                )
                return
            self.log_manager.log("info", f"Successfully crawled: {url}", "crawler")

            # Chamada automática para analyze_content
            self.analyze_content(response.text, url)

            # Continuação do processo de crawling para links encontrados na página
            content_type = response.headers.get("Content-Type", "text/html")
            if current_depth < self.depth and "html" in content_type:
                links = self.extract_links(response.content, url)
                with self._visited_lock:
                    links = {link for link in links if link not in self.visited_urls}
                if links:
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = [
                            executor.submit(self.crawl, link, current_depth + 1)
                            for link in sorted(links)
                        ]
                        for future in as_completed(futures):
                            future.result()  # Aguarda a conclusão de todas as solicitações
        except RequestException as e:
            # Registra e ignora todos os erros de solicitação com um log de aviso
            self.error_urls.add(url)
            self.log_manager.log(
                "warning",
                f"Request error occurred while crawling {url}: {e}. Skipping...",
                "network",
            )

    def extract_links(self, content: str | bytes, current_url: str) -> set[str]:
        """
        Extracts links from a web page.

        Parameters
        ----------
        content : str | bytes
            HTML content of the page.
        current_url : str
            Current URL to be used for normalizing relative links.

        Returns
        -------
        Set[str]
            Set of extracted and normalized http(s) URLs from the page (``mailto:``,
            ``javascript:``, empty and fragment-only links are ignored).
        """

        soup = BeautifulSoup(content, "html.parser")
        links = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href or href.startswith("#"):
                continue
            link = self.normalize_link(href, current_url)
            if urlparse(link).scheme in CRAWLABLE_SCHEMES:
                links.add(link)
        return links

    def normalize_link(self, link: str, current_url: str) -> str:
        """
        Normalizes a relative or absolute link based on the current URL.

        Parameters
        ----------
        link : str
            Link to be normalized.
        current_url : str
            Current URL for resolving relative links.

        Returns
        -------
        str
            Normalized URL (absolute, without the ``#fragment``).
        """

        link = link.strip()
        if urlparse(link).scheme == "":
            link = urljoin(current_url, link)
        return urldefrag(link)[0]

    def analyze_content(self, text: str, url: str) -> list[dict[str, Any]]:
        """
        Analyzes the content of a web page using YARA rules.

        Parameters
        ----------
        text : str
            Textual content of the page for analysis.
        url : str
            URL of the page being analyzed.

        Returns
        -------
        List[Dict[str, Any]]
            List of dictionaries containing details of the found matches
            (``yara_match_condition`` is the matched ``yara.StringMatch``).
        """

        results = []
        if not self.yara_compiler or not text:
            return results

        # O compilador guarda metadados das regras na instância: serializa o uso entre threads
        with self._yara_lock:
            matches = self.yara_compiler.match_text(text)
        for match in matches:
            rule_name = match["rule_name"]
            client_name = match["client_name"]
            yara_match_condition = match["yara_match"]
            rule_type = match["yara_rule_type"]

            if client_name:
                match_result = {
                    "rule_name": rule_name,
                    "yara_match_condition": yara_match_condition,
                    "link_match": url,
                    "client_match": client_name,
                    "rule_type": rule_type,
                }
                results.append(match_result)
                self.yara_matches.append(match_result)  # Add the match to the all_matches list

        return results

    def get_yara_matches(self) -> list[dict[str, Any]]:
        """
        Returns all YARA matches found during crawling.

        Returns
        -------
        List[Dict[str, Any]]
            List of YARA matches.
        """

        return self.yara_matches
