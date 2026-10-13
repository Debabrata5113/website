
import sqlite3

conn = sqlite3.connect("mobile_store.db")

conn.execute("""
    UPDATE admins
    SET username = ?, password = ?
    WHERE id = (
        SELECT id FROM admins
        ORDER BY id ASC
        LIMIT 1
    )
""", ("admin", "1234"))

conn.commit()

admin = conn.execute("""
    SELECT id, username
    FROM admins
    WHERE username = ?
""", ("admin",)).fetchone()

if admin:
    print("Admin reset successful!")
    print("Username: admin")
    print("Password: 1234")
else:
    print("No admin account found.")

conn.close()
