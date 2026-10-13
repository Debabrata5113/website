import sqlite3

conn = sqlite3.connect("mobile_store.db")
cursor = conn.cursor()

cursor.execute("SELECT * FROM products")
products = cursor.fetchall()

print("PRODUCTS IN DATABASE:")

for product in products:
    print(product)

conn.close()
