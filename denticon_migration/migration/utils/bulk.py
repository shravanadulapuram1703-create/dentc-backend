"""
migration/utils/bulk.py
-----------------------
Batched INSERT helpers built on psycopg2.extras.execute_values.

Why this exists
    Row-by-row ``cur.execute()`` over a *remote* Postgres makes million-row
    steps take hours: one network round-trip per row. ``execute_values`` sends
    rows in pages of N, cutting round-trips by ~Nx (typically 20-50x faster on
    a remote Cloud SQL instance).

Usage (fire-and-forget, e.g. ON CONFLICT DO NOTHING):
    buf = BulkBuffer(conn, "patient_payments", COLS,
                     conflict="ON CONFLICT (id) DO NOTHING", label="payments")
    for row in rows:
        buf.add((db_pk, pat_id, ...))
    buf.flush()                       # final partial batch
    print(buf.inserted)               # rows sent to DB

Usage (need generated ids back, e.g. serial PK + ON CONFLICT DO UPDATE):
    buf = BulkBuffer(conn, "insurance_plans", COLS,
                     conflict="ON CONFLICT (legacy_id) DO UPDATE SET ...",
                     returning="id, legacy_id",
                     dedup_index=COLS.index("legacy_id"),   # avoid dup key in one stmt
                     label="insurance_plans")
    for row in rows:
        buf.add((...))
    buf.flush()
    plan_map = {str(legacy): pk for pk, legacy in buf.returned}
"""

from psycopg2.extras import execute_values


def _dedup(rows, key_idx):
    """
    Keep the LAST row per conflict key (matches row-by-row upsert "last write
    wins" semantics). Required for ON CONFLICT DO UPDATE: Postgres raises
    "ON CONFLICT DO UPDATE command cannot affect row a second time" when one
    statement contains two rows with the same conflict key.

    ``key_idx`` is an int or a tuple of ints indexing into each row tuple.
    ``None`` disables dedup (safe for DO NOTHING).
    """
    if key_idx is None:
        return rows
    if isinstance(key_idx, int):
        key_idx = (key_idx,)
    seen = {}
    for r in rows:
        k = tuple(r[i] for i in key_idx)
        seen[k] = r
    return list(seen.values())


class BulkBuffer:
    """
    Accumulates row tuples and flushes them to Postgres in batches via
    execute_values, committing after each flush so a failure never loses more
    than one batch.
    """

    def __init__(self, conn, table, columns, *,
                 conflict="", returning=None, dedup_index=None,
                 template=None, flush_every=20000, page_size=2000, label=""):
        self.conn = conn
        self.cur = conn.cursor()
        self.table = table
        self.columns = list(columns)
        self.returning = returning
        self.dedup_index = dedup_index
        # Optional per-row VALUES template for execute_values, e.g.
        # "(%s,%s,COALESCE(%s,NOW()))". When None, execute_values builds the
        # default "(%s,%s,...)" from the tuple length.
        self.template = template
        self.flush_every = flush_every
        self.page_size = page_size
        self.label = label

        self._buf = []
        self.inserted = 0      # rows sent to DB across all flushes (post-dedup)
        self.returned = []     # accumulated RETURNING rows (if returning set)

        cols = ", ".join(self.columns)
        tail = f" {conflict}" if conflict else ""
        ret = f" RETURNING {returning}" if returning else ""
        self._sql = f"INSERT INTO {table} ({cols}) VALUES %s{tail}{ret}"

        # Dirty legacy data sometimes exceeds a column's varchar(n). Capture each
        # mapped column's max length once so flush() can truncate over-long strings
        # instead of crashing the whole batch.
        self._limits: dict[int, int] = {}
        try:
            self.cur.execute(
                "SELECT column_name, character_maximum_length FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s "
                "AND character_maximum_length IS NOT NULL",
                (table,),
            )
            colmax = {r[0]: r[1] for r in self.cur.fetchall()}
            for i, col in enumerate(self.columns):
                if col in colmax:
                    self._limits[i] = colmax[col]
        except Exception:
            self.conn.rollback()

    def _cap(self, row):
        """Truncate over-long string values to their column's varchar(n) limit."""
        if not self._limits:
            return row
        out = None
        for i, n in self._limits.items():
            v = row[i]
            if isinstance(v, str) and len(v) > n:
                if out is None:
                    out = list(row)
                out[i] = v[:n]
        return tuple(out) if out is not None else row

    def add(self, values):
        """Queue one row (tuple/list matching ``columns``). Auto-flushes at flush_every."""
        self._buf.append(tuple(values))
        if len(self._buf) >= self.flush_every:
            self.flush()

    def flush(self):
        """Send the queued rows now and commit. Returns rows fetched this flush."""
        if not self._buf:
            return []
        rows = _dedup(self._buf, self.dedup_index)
        if self._limits:
            rows = [self._cap(r) for r in rows]
        if self.returning:
            got = execute_values(
                self.cur, self._sql, rows, template=self.template,
                page_size=self.page_size, fetch=True,
            )
            self.returned.extend(got)
        else:
            execute_values(
                self.cur, self._sql, rows, template=self.template,
                page_size=self.page_size,
            )
            got = []
        self.conn.commit()
        self.inserted += len(rows)
        self._buf = []
        if self.label:
            print(f"    ...{self.inserted:,} {self.label} written")
        return got
