import aiohttp
import os

async def fetch_tenor_gifs(search_term: str) -> list[str]:
    """Fetches the top 10 GIFs for a search term from Tenor."""
    api_key = os.getenv("TENOR_API_KEY")
    if not api_key or api_key == "your_tenor_api_key_here":
        # Fallback to empty list if API key is not configured to avoid crashing.
        return []

    # Tenor V2 search API
    url = f"https://tenor.googleapis.com/v2/search?q={search_term}&key={api_key}&client_key=nexus_discord_bot&limit=10&media_filter=gif"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                print(f"Failed to fetch from Tenor API: {response.status}")
                return []

            data = await response.json()
            results = data.get("results", [])

            gif_urls = []
            for item in results:
                try:
                    # Extract the actual GIF url
                    gif_url = item["media_formats"]["gif"]["url"]
                    gif_urls.append(gif_url)
                except KeyError:
                    continue

            return gif_urls
