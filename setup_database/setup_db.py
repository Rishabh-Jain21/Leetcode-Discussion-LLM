import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_NAME = "leetcode_discussions.db"


def get_db_path():
    os.makedirs(DB_DIR, exist_ok=True)
    return os.path.join(DB_DIR, DB_NAME)


def get_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # ---------------------------------------------------------------
    # 1. raw_discussions  (replaces data.json / data_merged.json)
    #    Stores discussion metadata from LeetCode API.
    #    Used by merge_topics (topic_id + updated_at) and by
    #    Filter.transform() which reads title, slug, summary,
    #    createdAt, updatedAt, tags, topicId.
    #    tags_json stores the raw tags array as JSON text since
    #    the code only flattens them to lowercase strings.
    # ---------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_discussions (
            topic_id    INTEGER PRIMARY KEY,
            uuid        TEXT NOT NULL,
            title       TEXT NOT NULL,
            slug        TEXT NOT NULL,
            summary     TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            tags_json   TEXT DEFAULT '[]'
        )
    """)

    # ---------------------------------------------------------------
    # 2. updated_raw_nodes  (replaces updated.json)
    #    Changed nodes from the latest API merge.
    #    Consumed by Filter.transform_updates() which reads
    #    the same fields as transform().
    #    Cleared and repopulated on each extraction run.
    # ---------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS updated_raw_nodes (
            topic_id    INTEGER PRIMARY KEY,
            title       TEXT,
            slug        TEXT,
            summary     TEXT,
            created_at  TEXT,
            updated_at  TEXT,
            tags_json   TEXT DEFAULT '[]'
        )
    """)

    # ---------------------------------------------------------------
    # 3. company_discussions  (replaces data/{company}/{company}.json)
    #    Transformed & filtered discussions per company.
    #    Output of Filter.company_filter_data() + save_company_data().
    #    Isolated per company via composite PK (company_name, topic_id).
    #    tags_json stores the flattened lowercase tag strings as JSON
    #    array, used for keyword matching in company_filter_data().
    # ---------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS company_discussions (
            company_name    TEXT NOT NULL,
            topic_id        INTEGER NOT NULL,
            title           TEXT NOT NULL,
            summary         TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            tags_json       TEXT DEFAULT '[]',
            url             TEXT NOT NULL,
            PRIMARY KEY (company_name, topic_id)
        )
    """)

    # ---------------------------------------------------------------
    # 4. company_discussion_content
    #    (replaces data/{company}/{company}_content.json)
    #    Full discussion content fetched per topic.
    #    Output of Discussion.get_all_discussions / _updates.
    #    Isolated per company.
    #    assets_urls_json / other_urls_json store URL arrays as JSON
    #    (from extract_and_group_urls).
    # ---------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS company_discussion_content (
            company_name        TEXT NOT NULL,
            topic_id            INTEGER NOT NULL,
            content             TEXT,
            contains_url        INTEGER DEFAULT 0,
            assets_urls_json    TEXT DEFAULT '[]',
            other_urls_json     TEXT DEFAULT '[]',
            updated_at          TEXT NOT NULL,
            PRIMARY KEY (company_name, topic_id),
            FOREIGN KEY (company_name, topic_id)
                REFERENCES company_discussions(company_name, topic_id)
        )
    """)

    # ---------------------------------------------------------------
    # 5. company_pending_updates
    #    (replaces data/{company}/updates.json)
    #    Tracks topics that need content (re-)fetched.
    #    Rows are deleted after Discussion.save_data() succeeds
    #    (mirrors the os.remove("updates.json") logic).
    #    Isolated per company.
    # ---------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS company_pending_updates (
            company_name    TEXT NOT NULL,
            topic_id        INTEGER NOT NULL,
            updated_at      TEXT NOT NULL,
            PRIMARY KEY (company_name, topic_id)
        )
    """)

    # ---------------------------------------------------------------
    # Indexes for the query patterns used in the codebase
    # ---------------------------------------------------------------

    # merge_topics compares on updated_at
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_raw_disc_updated
        ON raw_discussions(updated_at)
    """)

    # Filter.company_filter_data reads all rows for a company
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_disc_company
        ON company_discussions(company_name)
    """)

    # merge_topics_items compares on (company, updated_at)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_disc_updated
        ON company_discussions(company_name, updated_at)
    """)

    # Discussion loads content per company
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_content_company
        ON company_discussion_content(company_name)
    """)

    # Discussion loads pending updates per company
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_pending_company
        ON company_pending_updates(company_name)
    """)

    conn.commit()
    conn.close()
    print(f"Database created at: {get_db_path()}")


if __name__ == "__main__":
    create_tables()
