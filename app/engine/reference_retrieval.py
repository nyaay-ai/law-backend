from app.api.indian_kanoon import IndianKanoonAPI
from app.core.vector_db import VectorStore
from app.schemas.legal_context import DraftContext, LegalContext


class ReferenceRetrieval:
    def __init__(self):
        self.store = VectorStore()

    async def retrieve_references(self, ctx: DraftContext) -> LegalContext:
        print(
            f"retrieve_references::Starting reference retrieval for draft context: {ctx.draft_type}, {ctx.legal_issue} in {ctx.jurisdiction} {ctx.court_type}"
        )
        query = (
            f"{ctx.draft_type.replace('_', ' ')} "
            f"{ctx.jurisdiction.replace('_', ' ')} "
            f"{ctx.court_type.replace('_', ' ')} "
            f"{ctx.legal_issue}"
        )

        # query = " ".join(part for part in query_parts if part).strip()

        draft_type = ctx.draft_type

        has_docs = self.store.collection_has_docs(draft_type)

        if not has_docs:
            raw_docs = await IndianKanoonAPI().search_query(query, draft_type)
            print(
                f"retrieve_references::Indian Kanoon API returned {len(raw_docs)} documents for query '{query}'.",
                raw_docs,
            )

            docs_to_store = []
            if raw_docs:
                new_raw_docs = raw_docs[:5]
                for doc in new_raw_docs:
                    print(
                        f"retrieve_references::Fetching full document for doc_id: {doc.doc_id}"
                    )
                    full_doc = await IndianKanoonAPI().get_document(doc.doc_id)
                    print(
                        f"retrieve_references::Fetched document content for doc_id: {doc.doc_id}, length: {len(full_doc.doc)}"
                    )

                    new_doc = {
                        "doc_id": full_doc.doc_id,
                        "title": full_doc.title,
                        "full_text": full_doc.doc,
                        "date": full_doc.published_date,
                        "num_cites": full_doc.num_cites,
                        "docsource": full_doc.doc_source,
                        "citations": doc.citations,
                    }
                    docs_to_store.append(new_doc)

                chunks = self.store.chunk_documents(
                    docs_to_store, draft_type=draft_type, jurisdiction=ctx.jurisdiction
                )
                self.store.upsert_documents(chunks)

        results = self.store.query(query, draft_type=draft_type, k=5)

        references = [ref for ref, score in results]

        print(
            f"retrieve_references::Reference retrieval for query '{query}' returned {len(references)} references.",
            references,
        )

        response = LegalContext(
            references=references,
            cache_hit=has_docs,
            draft_context_id="",
            query_used=query,
        )

        print(f"retrieve_references::response:{response}")

        return response
