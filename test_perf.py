import sqlite3
import time

db = sqlite3.connect('resources/dictionary.db')

def time_query(name, query, args=()):
    start = time.time()
    res = db.execute(query, args).fetchall()
    end = time.time()
    print(f"[{name}] Found {len(res)} results. Time: {end - start:.4f}s")

# 1. ORDER BY RANDOM test
time_query(
    "Examples (ORDER BY RANDOM)", 
    "SELECT chinese, english FROM sentences WHERE chinese LIKE ? ORDER BY RANDOM() LIMIT 5",
    ('%我喜欢%',)
)

time_query(
    "Examples (LIMIT first, no random)", 
    "SELECT chinese, english FROM sentences WHERE chinese LIKE ? LIMIT 50",
    ('%我喜欢%',)
)

# 2. LIKE with OR test
time_query(
    "Search LIKE OR",
    "SELECT * FROM dictionary WHERE traditional LIKE ? OR simplified LIKE ? OR pinyin_clean LIKE ?",
    ('shi%', 'shi%', 'shi%')
)

time_query(
    "Search UNION",
    '''
    SELECT * FROM dictionary WHERE traditional LIKE ?
    UNION
    SELECT * FROM dictionary WHERE simplified LIKE ?
    UNION
    SELECT * FROM dictionary WHERE pinyin_clean LIKE ?
    ''',
    ('shi%', 'shi%', 'shi%')
)

# 3. FTS test
time_query(
    "FTS No Limit",
    """
    SELECT d.id, f.rank as fts_rank
    FROM dictionary d
    JOIN dictionary_fts f ON d.id = f.rowid
    WHERE dictionary_fts MATCH ? 
    ORDER BY rank 
    """,
    ('"the"',)
)

time_query(
    "FTS With Limit",
    """
    SELECT d.id, f.rank as fts_rank
    FROM dictionary d
    JOIN dictionary_fts f ON d.id = f.rowid
    WHERE dictionary_fts MATCH ? 
    ORDER BY rank 
    LIMIT 200
    """,
    ('"the"',)
)
