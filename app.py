
from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import hashlib
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timezone, timedelta

DB_FILE = "database.db"

def init_db():
    if not os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Tabelle für Nutzer
        c.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
        ''')

        # Tabelle für Produkte
        c.execute('''
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            image TEXT
        )
        ''')

        # Tabelle für Warenkorb
        c.execute('''
        CREATE TABLE cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
        ''')

        # Tabelle für Bestellungen
        c.execute('''
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_ids TEXT,
            total REAL,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        ''')

        # Tabelle für Bewertungen
        c.execute('''
        CREATE TABLE reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            user_id INTEGER,
            rating INTEGER,
            comment TEXT,
            created_at TEXT,
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        ''')

        conn.commit()
        conn.close()
        print("Datenbank erstellt!")



app = Flask(__name__)
app.secret_key = 'geheim123'

# --- Upload-Konfiguration ---
UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- DB Verbindung ---
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- Startseite ---
@app.route('/')
def index():
    db = get_db()
    products = db.execute('SELECT * FROM products').fetchall()
    db.close()
    return render_template('index.html', products=products)

# --- Produkt-Detailseite ---
@app.route('/product/<int:id>')
def product(id):
    db = get_db()

    product = db.execute(
        'SELECT * FROM products WHERE id=?',
        (id,)
    ).fetchone()

    reviews = db.execute("""
        SELECT r.rating, r.comment, r.created_at, u.username
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.product_id=?
        ORDER BY r.created_at DESC
    """, (id,)).fetchall()

    db.close()

    return render_template(
        'product.html',
        product=product,
        reviews=reviews
    )


@app.route('/product/<int:product_id>/review', methods=['POST'])
def add_review(product_id):
    if 'user_id' not in session:
        return redirect('/login')

    rating = int(request.form.get('rating'))
    comment = request.form.get('comment')
    user_id = session['user_id']
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO reviews (product_id, user_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
              (product_id, user_id, rating, comment, created_at))
    conn.commit()
    conn.close()

    return redirect(f'/product/{product_id}')



# --- Kunden-Warenkorb hinzufügen ---
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if not session.get('user_id'):
        return redirect('/login')
    user_id = session['user_id']
    db = get_db()
    item = db.execute("SELECT * FROM cart_items WHERE user_id=? AND product_id=?", (user_id, product_id)).fetchone()
    if item:
        db.execute("UPDATE cart_items SET quantity = quantity + 1 WHERE id=?", (item['id'],))
    else:
        db.execute("INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, 1)", (user_id, product_id))
    db.commit()
    db.close()
    return redirect('/')

# --- Warenkorb anzeigen ---
@app.route('/cart')
def cart():
    if not session.get('user_id'):
        return redirect('/login')
    user_id = session['user_id']
    db = get_db()
    items = db.execute("""
        SELECT ci.id, p.id as product_id, p.name, p.price, p.image, ci.quantity
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.user_id=?
    """, (user_id,)).fetchall()
    total = sum(item['price'] * item['quantity'] for item in items)
    db.close()
    return render_template('cart.html', cart_items=items, total=total)

# --- Warenkorb bearbeiten (entfernen, Menge erhöhen/reduzieren) ---
@app.route('/remove_from_cart/<int:item_id>')
def remove_from_cart(item_id):
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    db.execute("DELETE FROM cart_items WHERE id=?", (item_id,))
    db.commit()
    db.close()
    return redirect('/cart')

@app.route('/cart/increase/<int:item_id>')
def increase_quantity(item_id):
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    db.execute("UPDATE cart_items SET quantity = quantity + 1 WHERE id=?", (item_id,))
    db.commit()
    db.close()
    return redirect('/cart')

@app.route('/cart/decrease/<int:item_id>')
def decrease_quantity(item_id):
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    item = db.execute("SELECT quantity FROM cart_items WHERE id=?", (item_id,)).fetchone()
    if item and item['quantity'] > 1:
        db.execute("UPDATE cart_items SET quantity = quantity - 1 WHERE id=?", (item_id,))
    else:
        db.execute("DELETE FROM cart_items WHERE id=?", (item_id,))
    db.commit()
    db.close()
    return redirect('/cart')

# --- Checkout ---
from datetime import datetime, timezone, timedelta

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if not session.get('user_id'):
        return redirect('/login')  # Nur eingeloggte Nutzer dürfen zur Kasse

    db = get_db()

    # Warenkorb laden und mit Produktdetails verbinden
    cart_items = db.execute("""
        SELECT c.id as cart_id, c.quantity, p.id as product_id, p.name, p.price
        FROM cart_items c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    """, (session['user_id'],)).fetchall()

    # Gesamtpreis berechnen
    total = sum(item['price'] * item['quantity'] for item in cart_items)

    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']
        city = request.form['city']

        # Produkt-IDs + Mengen als String speichern, z.B. "1:2,3:1"
        product_ids = ",".join(f"{item['product_id']}:{item['quantity']}" for item in cart_items)

        # Deutsche Zeit berechnen
        de_time = datetime.now(timezone(timedelta(hours=1)))  # UTC+1
        created_at = de_time.strftime("%Y-%m-%d %H:%M:%S")

        # Bestellung in DB speichern
        db.execute(
            'INSERT INTO orders (user_id, product_ids, total, created_at) VALUES (?, ?, ?, ?)',
            (session['user_id'], product_ids, total, created_at)
        )
        db.commit()

        # Warenkorb leeren
        db.execute("DELETE FROM cart_items WHERE user_id=?", (session['user_id'],))
        db.commit()
        db.close()

        return render_template('order_success.html', total=total, name=name)

    db.close()
    return render_template('checkout.html', cart_items=cart_items, total=total)


# --- Admin Login ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == "admin" and password == "geheim123":
            session['admin'] = True
            return redirect('/admin')
        return render_template('admin_login.html', error="Falsche Zugangsdaten!")
    return render_template('admin_login.html')

# --- Admin Dashboard ---
@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect('/admin/login')
    return render_template('admin.html')

# --- Admin Produkte verwalten ---
@app.route('/admin/products')
def admin_products():
    if not session.get('admin'):
        return redirect('/admin/login')
    db = get_db()
    products = db.execute("SELECT * FROM products").fetchall()
    db.close()
    return render_template("admin_products.html", products=products)

# --- Admin Produkt hinzufügen (mit Bild-Upload) ---
@app.route("/admin/add-product", methods=["GET", "POST"])
def admin_add_product():
    if not session.get('admin'):
        return redirect('/admin/login')
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        price = float(request.form['price'])

        file = request.files.get('image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        else:
            filename = ''  # Kein Bild hochgeladen

        db = get_db()
        db.execute('INSERT INTO products (name, description, price, image) VALUES (?, ?, ?, ?)',
                   (name, description, price, filename))
        db.commit()
        db.close()
        return redirect('/admin/products')
    return render_template('admin_add_product.html')

# --- Admin Produkt bearbeiten ---
@app.route('/admin/edit/<int:id>', methods=["GET", "POST"])
def admin_edit(id):
    if not session.get('admin'):
        return redirect('/admin/login')
    db = get_db()
    if request.method == "POST":
        name = request.form['name']
        description = request.form.get('description', '')
        price = float(request.form['price'])

        file = request.files.get('image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        else:
            # Bild nicht geändert, altes beibehalten
            old_product = db.execute("SELECT image FROM products WHERE id=?", (id,)).fetchone()
            filename = old_product['image']

        db.execute("""
            UPDATE products
            SET name=?, description=?, price=?, image=?
            WHERE id=?
        """, (name, description, price, filename, id))
        db.commit()
        db.close()
        return redirect('/admin/products')

    product = db.execute("SELECT * FROM products WHERE id=?", (id,)).fetchone()
    db.close()
    return render_template("admin_edit.html", product=product)

# --- Admin Produkt löschen ---
@app.route('/admin/delete-product/<int:id>')
def admin_delete(id):
    if not session.get('admin'):
        return redirect('/admin/login')
    db = get_db()
    db.execute("DELETE FROM products WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect('/admin/products')

@app.route('/admin/orders') 
def admin_orders():
    if not session.get('admin'):
        return redirect('/admin/login')
    db = get_db()
    orders = db.execute("""
        SELECT o.id, o.user_id, u.username, o.product_ids, o.total, o.created_at
        FROM orders o
        JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC
    """).fetchall()
    db.close()
    return render_template('admin_orders.html', orders=orders)

# --- Admin Logout ---
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/')

# --- Kunden Registrierung ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                       (username, email, hashed_pw))
            db.commit()
            db.close()
            return redirect('/login')
        except sqlite3.IntegrityError:
            db.close()
            return render_template('register.html', error="Benutzername oder E-Mail existiert bereits.")
    return render_template('register.html')

# --- Kunden Login ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email=? AND password=?', (email, hashed_pw)).fetchone()
        db.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect('/')
        return render_template('login.html', error="E-Mail oder Passwort falsch.")
    return render_template('login.html')

# --- Kunden Logout ---
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect('/')

if __name__ == '__main__':
    init_db() 
    app.run(debug=True)
=======
from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import hashlib
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timezone, timedelta


app = Flask(__name__)
app.secret_key = 'geheim123'

# --- Upload-Konfiguration ---
UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- DB Verbindung ---
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- Startseite ---
@app.route('/')
def index():
    db = get_db()
    products = db.execute('SELECT * FROM products').fetchall()
    db.close()
    return render_template('index.html', products=products)

# --- Produkt-Detailseite ---
@app.route('/product/<int:id>')
def product(id):
    db = get_db()

    product = db.execute(
        'SELECT * FROM products WHERE id=?',
        (id,)
    ).fetchone()

    reviews = db.execute("""
        SELECT r.rating, r.comment, r.created_at, u.username
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.product_id=?
        ORDER BY r.created_at DESC
    """, (id,)).fetchall()

    db.close()

    return render_template(
        'product.html',
        product=product,
        reviews=reviews
    )


@app.route('/product/<int:product_id>/review', methods=['POST'])
def add_review(product_id):
    if 'user_id' not in session:
        return redirect('/login')

    rating = int(request.form.get('rating'))
    comment = request.form.get('comment')
    user_id = session['user_id']
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO reviews (product_id, user_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
              (product_id, user_id, rating, comment, created_at))
    conn.commit()
    conn.close()

    return redirect(f'/product/{product_id}')



# --- Kunden-Warenkorb hinzufügen ---
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if not session.get('user_id'):
        return redirect('/login')
    user_id = session['user_id']
    db = get_db()
    item = db.execute("SELECT * FROM cart_items WHERE user_id=? AND product_id=?", (user_id, product_id)).fetchone()
    if item:
        db.execute("UPDATE cart_items SET quantity = quantity + 1 WHERE id=?", (item['id'],))
    else:
        db.execute("INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, 1)", (user_id, product_id))
    db.commit()
    db.close()
    return redirect('/')

# --- Warenkorb anzeigen ---
@app.route('/cart')
def cart():
    if not session.get('user_id'):
        return redirect('/login')
    user_id = session['user_id']
    db = get_db()
    items = db.execute("""
        SELECT ci.id, p.id as product_id, p.name, p.price, p.image, ci.quantity
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.user_id=?
    """, (user_id,)).fetchall()
    total = sum(item['price'] * item['quantity'] for item in items)
    db.close()
    return render_template('cart.html', cart_items=items, total=total)

# --- Warenkorb bearbeiten (entfernen, Menge erhöhen/reduzieren) ---
@app.route('/remove_from_cart/<int:item_id>')
def remove_from_cart(item_id):
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    db.execute("DELETE FROM cart_items WHERE id=?", (item_id,))
    db.commit()
    db.close()
    return redirect('/cart')

@app.route('/cart/increase/<int:item_id>')
def increase_quantity(item_id):
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    db.execute("UPDATE cart_items SET quantity = quantity + 1 WHERE id=?", (item_id,))
    db.commit()
    db.close()
    return redirect('/cart')

@app.route('/cart/decrease/<int:item_id>')
def decrease_quantity(item_id):
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    item = db.execute("SELECT quantity FROM cart_items WHERE id=?", (item_id,)).fetchone()
    if item and item['quantity'] > 1:
        db.execute("UPDATE cart_items SET quantity = quantity - 1 WHERE id=?", (item_id,))
    else:
        db.execute("DELETE FROM cart_items WHERE id=?", (item_id,))
    db.commit()
    db.close()
    return redirect('/cart')

# --- Checkout ---
from datetime import datetime, timezone, timedelta

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if not session.get('user_id'):
        return redirect('/login')  # Nur eingeloggte Nutzer dürfen zur Kasse

    db = get_db()

    # Warenkorb laden und mit Produktdetails verbinden
    cart_items = db.execute("""
        SELECT c.id as cart_id, c.quantity, p.id as product_id, p.name, p.price
        FROM cart_items c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    """, (session['user_id'],)).fetchall()

    # Gesamtpreis berechnen
    total = sum(item['price'] * item['quantity'] for item in cart_items)

    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']
        city = request.form['city']

        # Produkt-IDs + Mengen als String speichern, z.B. "1:2,3:1"
        product_ids = ",".join(f"{item['product_id']}:{item['quantity']}" for item in cart_items)

        # Deutsche Zeit berechnen
        de_time = datetime.now(timezone(timedelta(hours=1)))  # UTC+1
        created_at = de_time.strftime("%Y-%m-%d %H:%M:%S")

        # Bestellung in DB speichern
        db.execute(
            'INSERT INTO orders (user_id, product_ids, total, created_at) VALUES (?, ?, ?, ?)',
            (session['user_id'], product_ids, total, created_at)
        )
        db.commit()

        # Warenkorb leeren
        db.execute("DELETE FROM cart_items WHERE user_id=?", (session['user_id'],))
        db.commit()
        db.close()

        return render_template('order_success.html', total=total, name=name)

    db.close()
    return render_template('checkout.html', cart_items=cart_items, total=total)


# --- Admin Login ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == "admin" and password == "geheim123":
            session['admin'] = True
            return redirect('/admin')
        return render_template('admin_login.html', error="Falsche Zugangsdaten!")
    return render_template('admin_login.html')

# --- Admin Dashboard ---
@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect('/admin/login')
    return render_template('admin.html')

# --- Admin Produkte verwalten ---
@app.route('/admin/products')
def admin_products():
    if not session.get('admin'):
        return redirect('/admin/login')
    db = get_db()
    products = db.execute("SELECT * FROM products").fetchall()
    db.close()
    return render_template("admin_products.html", products=products)

# --- Admin Produkt hinzufügen (mit Bild-Upload) ---
@app.route("/admin/add-product", methods=["GET", "POST"])
def admin_add_product():
    if not session.get('admin'):
        return redirect('/admin/login')
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        price = float(request.form['price'])

        file = request.files.get('image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        else:
            filename = ''  # Kein Bild hochgeladen

        db = get_db()
        db.execute('INSERT INTO products (name, description, price, image) VALUES (?, ?, ?, ?)',
                   (name, description, price, filename))
        db.commit()
        db.close()
        return redirect('/admin/products')
    return render_template('admin_add_product.html')

# --- Admin Produkt bearbeiten ---
@app.route('/admin/edit/<int:id>', methods=["GET", "POST"])
def admin_edit(id):
    if not session.get('admin'):
        return redirect('/admin/login')
    db = get_db()
    if request.method == "POST":
        name = request.form['name']
        description = request.form.get('description', '')
        price = float(request.form['price'])

        file = request.files.get('image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        else:
            # Bild nicht geändert, altes beibehalten
            old_product = db.execute("SELECT image FROM products WHERE id=?", (id,)).fetchone()
            filename = old_product['image']

        db.execute("""
            UPDATE products
            SET name=?, description=?, price=?, image=?
            WHERE id=?
        """, (name, description, price, filename, id))
        db.commit()
        db.close()
        return redirect('/admin/products')

    product = db.execute("SELECT * FROM products WHERE id=?", (id,)).fetchone()
    db.close()
    return render_template("admin_edit.html", product=product)

# --- Admin Produkt löschen ---
@app.route('/admin/delete-product/<int:id>')
def admin_delete(id):
    if not session.get('admin'):
        return redirect('/admin/login')
    db = get_db()
    db.execute("DELETE FROM products WHERE id=?", (id,))
    db.commit()
    db.close()
    return redirect('/admin/products')

@app.route('/admin/orders') 
def admin_orders():
    if not session.get('admin'):
        return redirect('/admin/login')
    db = get_db()
    orders = db.execute("""
        SELECT o.id, o.user_id, u.username, o.product_ids, o.total, o.created_at
        FROM orders o
        JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC
    """).fetchall()
    db.close()
    return render_template('admin_orders.html', orders=orders)

# --- Admin Logout ---
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/')

# --- Kunden Registrierung ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                       (username, email, hashed_pw))
            db.commit()
            db.close()
            return redirect('/login')
        except sqlite3.IntegrityError:
            db.close()
            return render_template('register.html', error="Benutzername oder E-Mail existiert bereits.")
    return render_template('register.html')

# --- Kunden Login ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email=? AND password=?', (email, hashed_pw)).fetchone()
        db.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect('/')
        return render_template('login.html', error="E-Mail oder Passwort falsch.")
    return render_template('login.html')

# --- Kunden Logout ---
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
>>>>>>> 7c3aad4739261c395a6da0c26d4dd84acc5fad7a
