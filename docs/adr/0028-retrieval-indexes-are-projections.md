# Retrieval Indexes Are Projections

FundOps will treat search, semantic retrieval, embeddings, vector indexes, and Archive Q&A retrieval helpers as rebuildable projections over retained evidence, source records, workflow evidence bundles, and completed artifacts. Retrieval indexes may help find candidate sources, but they should not become the source of truth for facts, citations, memory, or historical workflow outputs.

Archive Q&A should ground claims in stable evidence, source, bundle, or artifact identifiers. This keeps retrieval technology replaceable as chunking strategies, embedding models, FTS indexes, or vector stores change, and it ensures index deletion or rebuilds do not cause data loss.
