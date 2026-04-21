import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.schemas.legal_context import DocumentContent, LegalSearch

BASE_URL = "https://api.indiankanoon.org/"

HEADERS = {
    "Authorization": f"Token {settings.INDIAN_KANOON_API_KEY}",
    "Accept": "application/json",
}


class IndianKanoonAPI:
    async def search_query(self, query: str, draft_type: str) -> list[LegalSearch]:
        params = {
            "inputQuery": query,
            "maxpages": 50,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}search/", headers=HEADERS, params=params
            )
            response.raise_for_status()
            data = response.json()
            results = []
            for doc in data.get("docs", []):
                results.append(
                    LegalSearch(
                        doc_id=doc.get("tid", ""),
                        title=doc.get("title", ""),
                        fragment=doc.get("fragment", ""),
                        doc_source=doc.get("docsource", ""),
                    )
                )
            return results

    async def get_document(self, doc_id: str) -> DocumentContent:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}doc/{doc_id}", headers=HEADERS)
            response.raise_for_status()
            data = response.json()
            return DocumentContent(
                doc_id=data.get("tid", ""),
                title=data.get("title", ""),
                doc=self.extract_plain_text(data.get("doc", "")),
                published_date=data.get("publishdate", None),
                num_cites=data.get("numcites", None),
                doc_source=data.get("docsource", ""),
            )

    def extract_plain_text(self, html: str) -> str:
        """Extract clean plain text from HTML content."""
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return text
