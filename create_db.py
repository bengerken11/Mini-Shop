import sqlite3

# Verbindung zur Datenbank (erstellt database.db automatisch)
conn = sqlite3.connect('database.db')
c = conn.cursor()

# Tabelle für User
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    email TEXT UNIQUE,
    password TEXT
)
''')

# Tabelle für Produkte
c.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    price REAL,
    image TEXT
)
''')

# Tabelle für Bestellungen
c.execute('''
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    product_ids TEXT,
    total REAL,
    created_at TEXT
)
''')

# Tabelle für gespeicherten Warenkorb 
c.execute('''
CREATE TABLE IF NOT EXISTS cart_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1
);
''') 

# Tabelle für Produkt-Bewertungen
c.execute('''
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT
)
''')


conn.commit()
conn.close()

print("Datenbank und Tabellen wurden erstellt!")
