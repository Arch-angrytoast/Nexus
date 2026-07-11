import aiohttp
import os
import urllib.parse

async def fetch_giphy_gifs(search_term: str) -> list[str]:
    """Fetches the top 10 GIFs for a search term from Giphy."""
    api_key = os.getenv("GIPHY_API_KEY")
    if not api_key or api_key == "your_giphy_api_key_here":
        # Fallback to empty list if API key is not configured to avoid crashing.
        return []

    encoded_term = urllib.parse.quote(search_term)
    url = f"https://api.giphy.com/v1/gifs/search?api_key={api_key}&q={encoded_term}&limit=10&rating=r"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                print(f"Failed to fetch from Giphy API: {response.status}")
                return []

            data = await response.json()
            results = data.get("data", [])

            gif_urls = []
            for item in results:
                try:
                    # Extract the original size GIF url
                    gif_url = item["images"]["original"]["url"]
                    gif_urls.append(gif_url)
                except KeyError:
                    continue

            return gif_urls
