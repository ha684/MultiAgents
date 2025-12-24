import asyncio

from src.services.web_search.firecrawl_service import FireCrawlService

firecrawl_service = FireCrawlService()

result = asyncio.run(
    firecrawl_service.search(query="Current intersting news in Vietnam?")
)
print(result)
