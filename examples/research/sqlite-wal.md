# SQLite Write-Ahead Logging

In WAL mode, writers append changes to the write-ahead log. A commit is recorded in the WAL, so readers can continue reading from their own snapshots while a writer is active. SQLite still allows only one writer at a time.

A checkpoint copies committed changes back to the database file. A long-lived reader can prevent a checkpoint from progressing past the reader's end mark and may cause the WAL file to grow.

WAL normally requires all participating processes to be on the same host because they share a memory-backed wal-index. This makes local storage an important consideration when choosing a journal mode.

Source: SQLite documentation, https://sqlite.org/wal.html
