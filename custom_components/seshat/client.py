"""Small authenticated client. Never follow redirects with credentials."""

import asyncio

import aiohttp


class Client:
    def __init__(self, session: aiohttp.ClientSession, url: str, key: str):
        self.session, self.url = session, url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {key}"}

    async def check(self):
        async with self.session.get(
            f"{self.url}/settings",
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=10),
            allow_redirects=False,
        ) as response:
            response.raise_for_status()
            if response.status != 200:
                raise ValueError("Unexpected API response")
            return await response.json()

    async def recognize(self, content: bytes, mime: str) -> dict:
        for attempt in range(3):
            async with self.session.post(
                f"{self.url}/recognize",
                data=content,
                headers={**self.headers, "Content-Type": mime},
                timeout=aiohttp.ClientTimeout(total=45),
                allow_redirects=False,
            ) as response:
                if response.status == 429 and attempt < 2:
                    await response.read()
                else:
                    response.raise_for_status()
                    if response.status != 200:
                        raise ValueError("Unexpected API response")
                    result = await response.json()
                    if not isinstance(result.get("faces"), list) or "best_match" not in result:
                        raise ValueError("Invalid recognition response")
                    return result
            await asyncio.sleep(1 + attempt)
        raise RuntimeError("Recognition retry exhausted")
