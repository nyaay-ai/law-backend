from app.api.indian_kanoon import IndianKanoonAPI
from app.core.vector_db import VectorStore
from app.schemas.legal_context import DraftContext, LegalContext


class ReferenceRetrieval:
    def __init__(self):
        self.store = VectorStore()

    async def retrieve_references(self, ctx: DraftContext) -> LegalContext:
        query = (
            f"{ctx.draft_type.value.replace('_', ' ')}"
            f"{ctx.jurisdiction.value.replace('_', ' ')}"
            f"{ctx.court_type.value.replace('_', ' ')}"
            f"{ctx.legal_issue}"
        ).strip()

        draft_type = ctx.draft_type.value

        has_docs = self.store.has_documents(draft_type)

        if not has_docs:
            raw_docs = await IndianKanoonAPI().search_query(query, draft_type)

            if raw_docs:
                chunks = self.store.chunk_documents(
                    raw_docs, draft_type=draft_type, jurisdiction=ctx.jurisdiction.value
                )
                self.store.upsert_documents(chunks)

        results = self.store.query(query, draft_type=draft_type, k=5)

        references = [ref for ref, score in results]

        return LegalContext(
            references=references,
            cache_hit=has_docs,
            draft_context_id="",
            query_used=query,
        )
