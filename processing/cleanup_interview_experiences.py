from setup_database.setup_db import get_connection


def cleanup_all():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM interview_experiences")
    count = cursor.fetchone()[0]
    cursor.execute("DELETE FROM interview_experiences")
    conn.commit()
    conn.close()
    print(f"Deleted {count} rows from interview_experiences")


if __name__ == "__main__":
    cleanup_all()
