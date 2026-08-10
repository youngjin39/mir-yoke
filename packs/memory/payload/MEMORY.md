# Local Memory Pack

Tracked project files remain canonical. `.mir/memory.db` is a local, rebuildable query index and
must not become the only copy of durable knowledge.

- Ingest only changed durable paths during ordinary work.
- Debounce repeated edits before indexing.
- Treat ordinary ingestion failure as a warning unless the local contract says otherwise.
- Run strict doctor and synchronization checks at closeout or release gates that select them.
