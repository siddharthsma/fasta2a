# Library imports
import httpx
from typing import List, Optional
from pydantic import HttpUrl, ValidationError

# Local imports
from smarta2a.utils.types import AgentCard

class AgentDiscoveryManager:
    """Centralized service for discovering agents through multiple methods"""
    
    def __init__(
        self,
        agent_cards: Optional[List[AgentCard]] = None,
        agent_base_urls: Optional[List[HttpUrl]] = None,
        discovery_endpoint: Optional[HttpUrl] = None,
        timeout: float = 5.0,
        retries: int = 2
    ):
        self.explicit_cards = agent_cards or []
        self.agent_base_urls = agent_base_urls or []
        self.discovery_endpoint = discovery_endpoint
        self.timeout = timeout
        self.retries = retries
        self.discovered_cards: List[AgentCard] = []

    async def discover_agents(self) -> List[AgentCard]:
        """Discover agents through all configured methods"""
        self.discovered_cards = []
        
        # 1. Add explicit cards first
        self.discovered_cards.extend(self.explicit_cards)
        
        # 2. Discover via base URLs
        if self.agent_base_urls:
            base_url_cards = await self._discover_via_base_urls()
            self.discovered_cards.extend(base_url_cards)
        
        # 3. Discover via central endpoint
        if self.discovery_endpoint:
            endpoint_cards = await self._discover_via_endpoint()
            self.discovered_cards.extend(endpoint_cards)
        
        return self.discovered_cards

    async def _discover_via_base_urls(self) -> List[AgentCard]:
        """Discover agents from provided base URLs"""
        cards = []
        client = httpx.AsyncClient()
        
        try:
            for base_url in self.agent_base_urls:
                try:
                    agent_url = f"{base_url}/.well-known/agent.json"
                    card = await self._fetch_agent_card(client, agent_url)
                    cards.append(card)
                except Exception:
                    pass
        finally:
            await client.aclose()
            
        return cards

    async def _discover_via_endpoint(self) -> List[AgentCard]:
        """Discover agents through a centralized endpoint"""
        client = httpx.AsyncClient()
        cards = []
        
        try:
            # Fetch service registry
            try:
                response = await client.get(
                    str(self.discovery_endpoint),
                    timeout=self.timeout
                )
                response.raise_for_status()
                services = response.json()["services"]
            except Exception:
                return []

            # Fetch all discovered agent cards
            for service in services:
                try:
                    agent_url = f"{service['base_url']}/.well-known/agent.json"
                    card = await self._fetch_agent_card(client, agent_url)
                    cards.append(card)
                except Exception:
                    pass
        finally:
            await client.aclose()
            
        return cards

    async def _fetch_agent_card(self, client: httpx.AsyncClient, url: str) -> AgentCard:
        """Fetch and validate a single agent.json"""
        try:
            response = await client.get(
                url,
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "AgentDiscovery/1.0"}
            )
            response.raise_for_status()
            
            # Validate content type
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                raise ValueError(f"Unexpected Content-Type: {content_type}")
                
            data = response.json()

            # Enforce required 'url' field
            if "url" not in data:
                raise ValueError("AgentCard requires 'url' field in agent.json")
                
            return AgentCard(**data)
            
        except ValidationError as e:
            raise
        except Exception as e:
            raise