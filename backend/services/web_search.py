"""
Web search integration for online mode.
Uses Serper API (primary) w/ DuckDuckGo fallback.
"""
import httpx
import os
from typing import Optional
import random
import re


class WebSearchClient:
    """Web search client w/ Serper API + DuckDuckGo fallback."""

    def __init__(self):
        self.serper_api_key = os.getenv("SERPER_API_KEY", "5f508568f0c8e57e9642645bef75f15e67cbd6bb")
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Search web & return latest results.
        Tries Serper API first, falls back to DuckDuckGo.
        
        Returns:
            list of dicts w/ keys: title, url, snippet
        """
        if self.serper_api_key:
            try:
                results = await self._serper_search(query, max_results)
                if results:
                    print(f"[WebSearch] Serper API: {len(results)} results")
                    return results
            except Exception as e:
                print(f"[WebSearch] Serper API failed: {e}, falling back to DuckDuckGo")
        
        try:
            results = await self._duckduckgo_search(query, max_results)
            print(f"[WebSearch] DuckDuckGo: {len(results)} results")
            return results
        except Exception as e:
            print(f"[WebSearch] DuckDuckGo failed: {e}")
            return []

    async def _serper_search(self, query: str, max_results: int) -> list[dict]:
        """Search using Serper API (Google results)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": self.serper_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "q": query,
                    "num": max_results,
                },
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("organic", [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            
            return results

    async def _duckduckgo_search(self, query: str, max_results: int) -> list[dict]:
        """Search using DuckDuckGo HTML (fallback)."""
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": random.choice(self.user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "DNT": "1",
                "Connection": "keep-alive",
            }
        ) as client:
            response = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": "", "kl": "us-en"},
            )
            response.raise_for_status()
            
            html = response.text
            results = []
            
            result_blocks = re.findall(
                r'<div class="result[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
                html,
                re.DOTALL
            )
            
            for block in result_blocks[:max_results]:
                title_match = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
                if not title_match:
                    continue
                
                url = title_match.group(1)
                title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()
                
                if "uddg=" in url:
                    url_match = re.search(r'uddg=([^&]+)', url)
                    if url_match:
                        from urllib.parse import unquote
                        url = unquote(url_match.group(1))
                
                snippet_match = re.search(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
                snippet = ""
                if snippet_match:
                    snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
                
                if title and url:
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet or title,
                    })
            
            return results

    async def close(self):
        pass


web_search_client = WebSearchClient()
