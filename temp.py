from langchain_scrapeless import ScrapelessUniversalScrapingTool

tool = ScrapelessUniversalScrapingTool()
# Example: fetch page and extract image URLs
response = tool.run({
    "url": "https://example.com/some-page",
    "outputs": ["images", "links"]
})
print(response.get("images"))  # list of image URLs found
