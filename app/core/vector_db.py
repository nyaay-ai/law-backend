import hashlib

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.schemas.legal_context import LegalReference, ReferenceSource

splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=100,
    separators=["\n\n", "\n", "। ", ". ", " ", ""],
)

MAX_CHUNKS_PER_DOC = 30
BATCH_SIZE = 500


class VectorStore:
    def __init__(self):
        # self._embeddings = OllamaEmbeddings(
        #     model="nomic-embed-text", base_url=settings.OLLAMA_BASE_URL
        # )
        # self._store = Chroma(
        #     collection_name=settings.CHROMA_COLLECTION,
        #     embedding_function=self._embeddings,
        #     client_settings={
        #         "chroma_server_host": settings.CHROMA_HOST,
        #         "chroma_server_http_port": str(settings.CHROMA_PORT),
        #     },
        #     collection_metadata={"hf:space_type": "cosine"},
        # )
        # 1. Properly initialize the Embedding Model
        self._embeddings = OllamaEmbeddings(
            model="nomic-embed-text", base_url=settings.OLLAMA_BASE_URL
        )

        # 2. Use HttpClient for Docker-to-Docker communication
        # This bypasses the 'dict' attribute error entirely
        self.client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(allow_reset=True, anonymized_telemetry=False),
        )

        # 3. Connect the LangChain wrapper to the existing client
        self._store = Chroma(
            client=self.client,
            collection_name=settings.CHROMA_COLLECTION,
            embedding_function=self._embeddings,
            collection_metadata={
                "hnsw:space": "cosine"
            },  # Fix: 'hnsw:space' is the correct key
        )

    def upsert_documents(self, chunks: list[dict]) -> None:
        """
        chunks: list of {id, text, metadata}
        Called after IK fetch — stores all chunks from all 5 docs.
        """
        if not chunks:
            return

        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i : i + BATCH_SIZE]
            self._store.add_texts(
                texts=[c["text"] for c in batch],
                ids=[c["id"] for c in batch],
                metadatas=[c["metadata"] for c in batch],
            )

    def query(
        self, query: str, draft_type: str, k: int = 5
    ) -> list[tuple[LegalReference, float]]:
        results = self._store.similarity_search_with_relevance_scores(
            query, k=k, filter={"draft_type": draft_type}
        )
        return [
            (
                LegalReference(
                    doc_id=doc.metadata.get("doc_id", ""),
                    title=doc.metadata.get("title", ""),
                    text=doc.page_content,
                    court=doc.metadata.get("court"),
                    date=doc.metadata.get("date"),
                    citation=doc.metadata.get("citation"),
                    score=round(score, 4),
                    source=ReferenceSource(doc.metadata.get("source", "cache")),
                ),
                score,
            )
            for doc, score in results
        ]

    def collection_has_docs(self, draft_type: str) -> bool:
        """
        Quick check before querying — avoids querying an empty
        or unpopulated collection for this draft type.
        """
        try:
            result = self._store._collection.get(
                where={"draft_type": draft_type}, limit=1
            )
            return len(result["ids"]) > 0
        except Exception:
            return False

    def chunk_documents(
        self, documents: list[dict], draft_type: str, jurisdiction: str
    ) -> list[dict]:
        """
        Takes raw IK documents, chunks their full text, returns
        flat list of {id, text, metadata} ready for ChromaDB upsert.
        """
        chunks = []

        for doc in documents:
            doc_chunks = splitter.split_text(doc["full_text"])
            doc_chunks = doc_chunks[:MAX_CHUNKS_PER_DOC]

            for i, chunk_text in enumerate(doc_chunks):
                # Deterministic chunk ID — same doc + same chunk index = same ID
                # This means re-fetching the same IK doc never creates duplicates
                chunk_id = hashlib.md5(f"{doc['doc_id']}_{i}".encode()).hexdigest()

                chunks.append(
                    {
                        "id": chunk_id,
                        "text": chunk_text,
                        "metadata": {
                            "doc_id": doc["doc_id"],
                            "title": doc["title"],
                            "court": doc["docsource"] or "",
                            "date": doc["date"] or "",
                            "citation": doc["citations"] or "",
                            "draft_type": draft_type,
                            "jurisdiction": jurisdiction or "",
                            "chunk_index": i,
                            "source": ReferenceSource.INDIAN_KANOON.value,
                        },
                    }
                )

        return chunks
