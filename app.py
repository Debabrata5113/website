from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "mobile_store_secret_key_2026"
DATABASE = "mobile_store.db"

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn
# Create banner table if it does not exist
def create_banners_table():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS banners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subtitle TEXT,
            image TEXT NOT NULL,
            button_text TEXT DEFAULT 'Shop Now',
            link TEXT DEFAULT '/products',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


create_banners_table()




def admin_required():

    if not session.get('admin_id'):
        return False

    return True

@app.route('/')
def home():
    return render_template('index.html')




@app.route('/products')
def products():

    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    sort = request.args.get('sort', '').strip()

    conn = get_db_connection()

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND LOWER(product_name) LIKE LOWER(?)"
        params.append('%' + search + '%')

    if category:
        query += " AND category = ?"
        params.append(category)

    if sort == 'low':
        query += " ORDER BY price ASC"
    elif sort == 'high':
        query += " ORDER BY price DESC"
    else:
        query += " ORDER BY id DESC"

    products = conn.execute(query, params).fetchall()

    categories = conn.execute("""
        SELECT DISTINCT category
        FROM products
        WHERE category IS NOT NULL AND category != ''
        ORDER BY category
    """).fetchall()

    conn.close()

    return render_template(
        'product.html',
        products=products,
        categories=categories,
        search=search,
        selected_category=category,
        selected_sort=sort
    )


@app.route('/add-to-cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):

    # User login check
    if not session.get('user_id'):
        flash('Please login first!', 'danger')
        return redirect('/login')

    user_id = session['user_id']

    conn = get_db_connection()

    # Check product
    product = conn.execute(
        "SELECT * FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()

    if product is None:
        conn.close()
        flash('Product not found!', 'danger')
        return redirect('/products')

    # Check stock
    if product['stock'] <= 0:
        conn.close()
        flash('This product is out of stock!', 'danger')
        return redirect('/products')

    # Check if product already in cart
    existing_item = conn.execute("""
        SELECT * FROM cart
        WHERE user_id = ? AND product_id = ?
    """, (
        user_id,
        product_id
    )).fetchone()

    if existing_item:

        # Increase quantity
        new_quantity = existing_item['quantity'] + 1

        # Don't exceed stock
        if new_quantity > product['stock']:
            conn.close()
            flash('You cannot add more than available stock!', 'warning')
            return redirect('/products')

        conn.execute("""
            UPDATE cart
            SET quantity = ?
            WHERE id = ?
        """, (
            new_quantity,
            existing_item['id']
        ))

    else:

        # Add new item
        conn.execute("""
            INSERT INTO cart
            (user_id, product_id, quantity)
            VALUES (?, ?, 1)
        """, (
            user_id,
            product_id
        ))

    conn.commit()
    conn.close()

    flash('Product added to cart!', 'success')

    return redirect('/cart')

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():

    if not session.get('user_id'):
        flash('Please login first!', 'danger')
        return redirect('/login')

    user_id = session['user_id']

    conn = get_db_connection()

    cart_items = conn.execute("""
        SELECT
            cart.product_id,
            cart.quantity,
            products.product_name,
            products.price,
            products.stock,
            products.image
        FROM cart
        JOIN products
            ON cart.product_id = products.id
        WHERE cart.user_id = ?
    """, (user_id,)).fetchall()

    if not cart_items:
        conn.close()
        flash('Your cart is empty!', 'warning')
        return redirect('/cart')

    total = sum(
        item['price'] * item['quantity']
        for item in cart_items
    )

    if request.method == 'POST':

        customer_name = request.form.get(
            'customer_name', ''
        ).strip()

        phone = request.form.get(
            'phone', ''
        ).strip()

        address = request.form.get(
            'address', ''
        ).strip()

        if not customer_name or not phone or not address:
            conn.close()
            flash('Please fill in all checkout fields!', 'danger')
            return redirect('/checkout')

        if any(item['stock'] < item['quantity'] for item in cart_items):
            conn.close()
            flash(
                'Some products have insufficient stock. Please update your cart.',
                'warning'
            )
            return redirect('/cart')

        conn.close()

        return render_template(
            'checkout.html',
            cart_items=cart_items,
            total=total,
            customer_name=customer_name,
            phone=phone,
            address=address
        )

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    conn.close()

    return render_template(
        'checkout.html',
        cart_items=cart_items,
        total=total,
        customer_name=user['name'] if user else '',
        phone=user['phone'] if user else '',
        address=''
    )

@app.route('/login', methods=['GET', 'POST'])
def login():

    if session.get('user_id'):
        return redirect('/dashboard')

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()

        user = conn.execute("""
            SELECT * FROM users
            WHERE email = ? AND password = ?
        """, (
            email,
            password
        )).fetchone()

        conn.close()

        if user:

            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']

            return redirect('/dashboard')

        else:

            flash(
                'Invalid email or password!',
                'danger'
            )

    return render_template('login.html')

@app.route('/logout')
def logout():

    session.clear()

    flash('You have been logged out successfully!', 'success')

    return redirect('/login')
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():

    # যদি Admin আগে থেকেই login করা থাকে
    if session.get('admin_id'):
        return redirect('/admin/dashboard')

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()

        admin = conn.execute("""
            SELECT * FROM admins
            WHERE username = ? AND password = ?
        """, (
            username,
            password
        )).fetchone()

        conn.close()

        # Login successful
        if admin:

            session['admin_id'] = admin['id']
            session['admin_username'] = admin['username']

            return redirect('/admin/dashboard')

        # Login failed
        else:

            flash('Invalid username or password!', 'danger')

    return render_template('admin_login.html')
@app.route('/admin/logout')
def admin_logout():

    session.clear()

    flash('You have been logged out successfully!', 'success')

    return redirect('/admin/login')


@app.route('/admin/dashboard')
def admin_dashboard():

    if not admin_required():
        flash('Please login first!', 'danger')
        return redirect('/admin/login')

    conn = get_db_connection()

    # Total Products
    total_products = conn.execute("""
        SELECT COUNT(*) FROM products
    """).fetchone()[0]

    # Total Orders
    total_orders = conn.execute("""
        SELECT COUNT(*) FROM orders
    """).fetchone()[0]

    # Total Customers
    total_customers = conn.execute("""
        SELECT COUNT(*) FROM users
    """).fetchone()[0]

    # This Month Revenue
    # COD order-সহ সব non-cancelled order-এর amount
    # এই মাসের তারিখ অনুযায়ী হিসাব করার জন্য
    # orders table-এ date column জানা প্রয়োজন।
    # তাই আপাতত মোট non-cancelled order amount দেখানো হচ্ছে।
    
    total_revenue = conn.execute("""
        SELECT COALESCE(SUM(total_amount), 0)
        FROM orders
        WHERE LOWER(order_status) = 'delivered'
        """).fetchone()[0]


    # Recent Orders
    recent_orders = conn.execute("""
        SELECT *
        FROM orders
        ORDER BY id DESC
        LIMIT 5
    """).fetchall()

    # Recent Customers
    recent_customers = conn.execute("""
        SELECT id, name, email, phone
        FROM users
        ORDER BY id DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    return render_template(
        'admin_dashboard.html',
        total_products=total_products,
        total_orders=total_orders,
        total_customers=total_customers,
        total_revenue=total_revenue,
        recent_orders=recent_orders,
        recent_customers=recent_customers
    )





@app.route('/admin/profile', methods=['GET', 'POST'])
def admin_profile():

    # Login না থাকলে login page-এ পাঠাবে
    if not session.get('admin_id'):
        return redirect('/admin/login')

    conn = get_db_connection()

    admin = conn.execute(
        "SELECT * FROM admins WHERE id = ?",
        (session['admin_id'],)
    ).fetchone()

    if admin is None:
        conn.close()
        session.clear()
        return redirect('/admin/login')

    if request.method == 'POST':

        new_username = request.form['username']
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # বর্তমান password check
        if current_password != admin['password']:

            flash('Current password is incorrect!', 'danger')

        # নতুন password দুইবার same কিনা
        elif new_password and new_password != confirm_password:

            flash('New passwords do not match!', 'danger')

        else:

            # Password change না করলে পুরোনো password থাকবে
            password_to_save = admin['password']

            if new_password:
                password_to_save = new_password

            try:

                conn.execute("""
                    UPDATE admins
                    SET username = ?, password = ?
                    WHERE id = ?
                """, (
                    new_username,
                    password_to_save,
                    session['admin_id']
                ))

                conn.commit()

                # Session-এর username update
                session['admin_username'] = new_username

                flash('Admin profile updated successfully!', 'success')

            except sqlite3.IntegrityError:

                flash('This username is already taken!', 'danger')

        conn.close()

    else:
        conn.close()

    return render_template(
        'admin_profile.html',
        admin=admin
    )
@app.route('/admin/products')
def admin_products():

    if not admin_required():
        flash('Please login first!','danger')
        return redirect('/admin/login')

    conn = get_db_connection()

    products = conn.execute("""
        SELECT * FROM products
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        'admin_products.html',
        products=products
    )
@app.route('/admin/add-product', methods=['GET', 'POST'])
def add_product():

    if not admin_required():
        flash('Please login first!','danger')
        return redirect('/admin/login')

    if request.method == 'POST':

        product_name = request.form['product_name']
        category = request.form['category']
        price = request.form['price']
        stock = request.form['stock']
        description = request.form['description']

        image = request.files.get('image')

        image_filename = None

        if image and image.filename:

            image_filename = secure_filename(image.filename)

            image.save(
                os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    image_filename
                )
            )

        conn = get_db_connection()

        conn.execute("""
            INSERT INTO products
            (
                product_name,
                category,
                price,
                stock,
                description,
                image
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            product_name,
            category,
            price,
            stock,
            description,
            image_filename
        ))

        conn.commit()
        conn.close()

        return redirect('/admin/products')

    return render_template('add_product.html')
@app.route('/admin/edit-product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):

    if not admin_required():
        flash('Please login first!','danger')
        return redirect('admin/login')

    conn = get_db_connection()

    product = conn.execute(
        "SELECT * FROM products WHERE id = ?",
        (id,)
    ).fetchone()

    if product is None:
        conn.close()
        return "Product not found"

    if request.method == 'POST':

        product_name = request.form['product_name']
        category = request.form['category']
        price = request.form['price']
        stock = request.form['stock']
        description = request.form['description']

        image = request.files.get('image')

        image_filename = product['image']

        # নতুন image দিলে update হবে
        if image and image.filename:

            image_filename = secure_filename(image.filename)

            image.save(
                os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    image_filename
                )
            )

        conn.execute("""
            UPDATE products
            SET
                product_name = ?,
                category = ?,
                price = ?,
                stock = ?,
                description = ?,
                image = ?
            WHERE id = ?
        """, (
            product_name,
            category,
            price,
            stock,
            description,
            image_filename,
            id
        ))

        conn.commit()
        conn.close()

        return redirect('/admin/products')

    conn.close()

    return render_template(
        'edit_product.html',
        product=product
    )

@app.route('/admin/delete-product/<int:id>', methods=['POST'])
def delete_product(id):

    conn = get_db_connection()

    product = conn.execute(
        "SELECT * FROM products WHERE id = ?",
        (id,)
    ).fetchone()

    if product is None:
        conn.close()
        return "Product not found"

    # পুরোনো image থাকলে delete করার চেষ্টা করবে
    if product['image']:

        image_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            product['image']
        )

        if os.path.exists(image_path):
            os.remove(image_path)

    # Database থেকে product delete
    conn.execute(
        "DELETE FROM products WHERE id = ?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect('/admin/products')



@app.route('/admin/orders')
def admin_orders():

    if not admin_required():
        flash('Please login first!', 'danger')
        return redirect('/admin/login')

    conn = get_db_connection()

    orders = conn.execute("""
        SELECT *
        FROM orders
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        'admin_orders.html',
        orders=orders
    )



@app.route('/admin/order/update-status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):

    if not admin_required():
        flash('Please login first!', 'danger')
        return redirect('/admin/login')

    order_status = request.form.get('order_status')

    allowed_statuses = [
        'Pending',
        'Processing',
        'Shipped',
        'Delivered',
        'Cancelled'
    ]

    if order_status not in allowed_statuses:
        flash('Invalid order status!', 'danger')
        return redirect('/admin/orders')

    conn = get_db_connection()

    conn.execute(
        'UPDATE orders SET order_status = ? WHERE id = ?',
        (order_status, order_id)
    )

    conn.commit()
    conn.close()

    flash('Order status updated successfully!', 'success')
    return redirect('/admin/orders')

@app.route('/admin/order/<int:order_id>')
def admin_order_details(order_id):

    if not admin_required():
        flash('Please login first!', 'danger')
        return redirect('/admin/login')

    conn = get_db_connection()

    order = conn.execute("""
        SELECT *
        FROM orders
        WHERE id = ?
    """, (order_id,)).fetchone()

    if order is None:
        conn.close()
        flash('Order not found!', 'danger')
        return redirect('/admin/orders')

    order_items = conn.execute("""
        SELECT *
        FROM order_items
        WHERE order_id = ?
        ORDER BY id ASC
    """, (order_id,)).fetchall()

    conn.close()

    return render_template(
        'admin_order_details.html',
        order=order,
        order_items=order_items
    )


    conn = get_db_connection()

    order = conn.execute(
        "SELECT id FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    if order is None:
        conn.close()
        flash('Order not found!', 'danger')
        return redirect('/admin/orders')

    conn.execute("""
        UPDATE orders
        SET order_status = ?
        WHERE id = ?
    """, (new_status, order_id))

    conn.commit()
    conn.close()

    flash(f'Order #{order_id} status updated successfully!', 'success')
    return redirect('/admin/orders')



@app.route('/admin/customers')
def admin_customers():
    if not admin_required():
        flash('Please login first!', 'danger')
        return redirect('/admin/login')

    conn = get_db_connection()

    customers = conn.execute("""
        SELECT
            users.id,
            users.name,
            users.email,
            users.phone,
            COUNT(orders.id) AS total_orders
        FROM users
        LEFT JOIN orders ON users.id = orders.user_id
        GROUP BY
            users.id,
            users.name,
            users.email,
            users.phone
        ORDER BY users.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        'admin_customers.html',
        customers=customers
    )




@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Password check
        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect('/register')

        conn = get_db_connection()

        # Check email already exists
        existing_user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            conn.close()
            flash('This email is already registered!', 'danger')
            return redirect('/register')

        # Create user
        conn.execute("""
            INSERT INTO users
            (name, email, phone, password)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            email,
            phone,
            password
        ))

        conn.commit()
        conn.close()

        flash('Registration successful! Please login.', 'success')
        return redirect('/login')

    return render_template('register.html')
@app.route('/contact')
def contact():
    return render_template('contact.html')
@app.route('/product/<int:id>')
def product_details(id):

    conn = get_db_connection()

    product = conn.execute(
        "SELECT * FROM products WHERE id = ?",
        (id,)
    ).fetchone()

    conn.close()

    if product is None:
        return "Product not found"

    return render_template(
        'product_details.html',
        product=product
    )

@app.route('/cart')
def cart():

    # Login check
    if not session.get('user_id'):
        flash('Please login first!', 'danger')
        return redirect('/login')

    user_id = session['user_id']

    conn = get_db_connection()

    cart_items = conn.execute("""
        SELECT
            cart.id AS cart_id,
            cart.quantity,
            products.id AS product_id,
            products.product_name,
            products.price,
            products.image,
            products.stock
        FROM cart
        JOIN products
            ON cart.product_id = products.id
        WHERE cart.user_id = ?
        ORDER BY cart.id DESC
    """, (
        user_id,
    )).fetchall()

    conn.close()

    total = 0

    for item in cart_items:
        total += item['price'] * item['quantity']

    return render_template(
        'cart.html',
        cart_items=cart_items,
        total=total
    )

@app.route('/cart/update/<int:cart_id>', methods=['POST'])
def update_cart(cart_id):

    if not session.get('user_id'):
        flash('Please login first!', 'danger')
        return redirect('/login')

    user_id = session['user_id']

    try:
        quantity = int(request.form['quantity'])
    except (ValueError, TypeError):
        flash('Invalid quantity!', 'danger')
        return redirect('/cart')

    if quantity < 1:
        quantity = 1

    conn = get_db_connection()

    cart_item = conn.execute("""
        SELECT
            cart.id,
            cart.product_id,
            products.stock
        FROM cart
        JOIN products
            ON cart.product_id = products.id
        WHERE cart.id = ? AND cart.user_id = ?
    """, (
        cart_id,
        user_id
    )).fetchone()

    if cart_item is None:
        conn.close()
        flash('Cart item not found!', 'danger')
        return redirect('/cart')

    if quantity > cart_item['stock']:
        conn.close()
        flash(
            f"Only {cart_item['stock']} item(s) available in stock!",
            'warning'
        )
        return redirect('/cart')

    conn.execute("""
        UPDATE cart
        SET quantity = ?
        WHERE id = ? AND user_id = ?
    """, (
        quantity,
        cart_id,
        user_id
    ))

    conn.commit()
    conn.close()

    return redirect('/cart')

@app.route('/cart/remove/<int:cart_id>', methods=['POST'])
def remove_from_cart(cart_id):

    if not session.get('user_id'):
        flash('Please login first!', 'danger')
        return redirect('/login')

    user_id = session['user_id']

    conn = get_db_connection()

    conn.execute("""
        DELETE FROM cart
        WHERE id = ? AND user_id = ?
    """, (
        cart_id,
        user_id
    ))

    conn.commit()
    conn.close()

    flash('Product removed from cart!', 'success')

    return redirect('/cart')


@app.route('/place-order', methods=['POST'])
def place_order():

    if not session.get('user_id'):
        flash('Please login first!', 'danger')
        return redirect('/login')

    user_id = session['user_id']

    customer_name = request.form.get('customer_name', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()

    if not customer_name or not phone or not address:
        flash('Please fill in all checkout fields!', 'danger')
        return redirect('/checkout')

    conn = get_db_connection()

    try:
        conn.execute('BEGIN')

        cart_items = conn.execute("""
            SELECT
                cart.product_id,
                cart.quantity,
                products.product_name,
                products.price,
                products.stock
            FROM cart
            JOIN products ON cart.product_id = products.id
            WHERE cart.user_id = ?
        """, (user_id,)).fetchall()

        if not cart_items:
            conn.rollback()
            flash('Your cart is empty!', 'warning')
            return redirect('/cart')

        total = 0

        for item in cart_items:
            if item['quantity'] < 1 or item['quantity'] > item['stock']:
                conn.rollback()
                flash(
                    f"Insufficient stock for {item['product_name']}!",
                    'warning'
                )
                return redirect('/cart')

            total += item['price'] * item['quantity']

        order_cursor = conn.execute("""
            INSERT INTO orders (
                user_id,
                customer_name,
                phone,
                address,
                total_amount,
                payment_method,
                payment_status,
                order_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            customer_name,
            phone,
            address,
            total,
            'Cash On Delivery',
            'Pending',
            'Pending'
        ))

        order_id = order_cursor.lastrowid

        for item in cart_items:
            item_total = item['price'] * item['quantity']

            conn.execute("""
                INSERT INTO order_items (
                    order_id,
                    product_id,
                    product_name,
                    price,
                    quantity,
                    total
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                item['product_id'],
                item['product_name'],
                item['price'],
                item['quantity'],
                item_total
            ))

            conn.execute("""
                UPDATE products
                SET stock = stock - ?
                WHERE id = ? AND stock >= ?
            """, (
                item['quantity'],
                item['product_id'],
                item['quantity']
            ))

            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                raise ValueError(
                    f"Stock update failed for {item['product_name']}"
                )

        conn.execute(
            "DELETE FROM cart WHERE user_id = ?",
            (user_id,)
        )

        conn.commit()

        flash('Order placed successfully!', 'success')
        return redirect('/my-orders')

    except Exception as e:
        conn.rollback()
        print("ORDER ERROR:", e)
        flash('Could not place your order. Please try again.', 'danger')
        return redirect('/checkout')

    finally:
        conn.close()



@app.route('/wishlist')
def wishlist():
    if not session.get('user_id'):
        flash('Please login to view your wishlist!', 'warning')
        return redirect('/login')

    conn = get_db_connection()

    wishlist_products = conn.execute("""
        SELECT products.*
        FROM wishlist
        JOIN products ON wishlist.product_id = products.id
        WHERE wishlist.user_id = ?
        ORDER BY wishlist.id DESC
    """, (session['user_id'],)).fetchall()

    conn.close()

    return render_template(
        'wishlist.html',
        wishlist_products=wishlist_products
    )


@app.route('/remove-from-wishlist/<int:product_id>', methods=['POST'])
def remove_from_wishlist(product_id):
    if not session.get('user_id'):
        flash('Please login first!', 'warning')
        return redirect('/login')

    conn = get_db_connection()

    conn.execute(
        'DELETE FROM wishlist WHERE user_id = ? AND product_id = ?',
        (session['user_id'], product_id)
    )

    conn.commit()
    conn.close()

    flash('Product removed from wishlist!', 'success')
    return redirect('/wishlist')


@app.route('/add-to-wishlist/<int:product_id>', methods=['POST'])
def add_to_wishlist(product_id):
    if not session.get('user_id'):
        flash('Please login to add products to your wishlist!', 'warning')
        return redirect('/login')

    conn = get_db_connection()

    product = conn.execute(
        'SELECT id FROM products WHERE id = ?',
        (product_id,)
    ).fetchone()

    if product is None:
        conn.close()
        flash('Product not found!', 'danger')
        return redirect('/products')

    existing = conn.execute(
        'SELECT id FROM wishlist WHERE user_id = ? AND product_id = ?',
        (session['user_id'], product_id)
    ).fetchone()

    if existing:
        flash('Product is already in your wishlist!', 'info')
    else:
        conn.execute(
            'INSERT INTO wishlist (user_id, product_id) VALUES (?, ?)',
            (session['user_id'], product_id)
        )
        conn.commit()
        flash('Product added to wishlist successfully!', 'success')

    conn.close()
    return redirect('/wishlist')



@app.route('/dashboard')
def dashboard():

    if not session.get('user_id'):
        flash('Please login first!', 'danger')
        return redirect('/login')

    return render_template(
        'dashboard.html',
        user_name=session.get('user_name'),
        user_email=session.get('user_email')
    )


@app.route('/my-orders')
def my_orders():

    if not session.get('user_id'):
        flash('Please login first!', 'danger')
        return redirect('/login')

    user_id = session['user_id']

    conn = get_db_connection()

    orders = conn.execute("""
        SELECT *
        FROM orders
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        'my_orders.html',
        orders=orders
    )


# =========================
# ADMIN BANNER MANAGEMENT
# =========================

ALLOWED_BANNER_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


def allowed_banner_file(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower()
        in ALLOWED_BANNER_EXTENSIONS
    )


@app.route('/admin/banners')
def admin_banners():
    if not admin_required():
        flash('Please login first!', 'danger')
        return redirect('/admin/login')

    conn = get_db_connection()

    banners = conn.execute("""
        SELECT * FROM banners
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        'admin_banners.html',
        banners=banners
    )


@app.route('/admin/banners/add', methods=['GET', 'POST'])
def admin_add_banner():
    if not admin_required():
        flash('Please login first!', 'danger')
        return redirect('/admin/login')

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        subtitle = request.form.get('subtitle', '').strip()
        button_text = request.form.get('button_text', 'Shop Now').strip()
        link = request.form.get('link', '/products').strip()
        is_active = 1 if request.form.get('is_active') == '1' else 0
        image_file = request.files.get('image')

        if not title:
            flash('Please enter a banner title.', 'danger')
            return redirect('/admin/banners/add')

        if not image_file or not image_file.filename:
            flash('Please select a banner image.', 'danger')
            return redirect('/admin/banners/add')

        if not allowed_banner_file(image_file.filename):
            flash('Only PNG, JPG, JPEG, WEBP and GIF images are allowed.', 'danger')
            return redirect('/admin/banners/add')

        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        filename = secure_filename(image_file.filename)

        # Prevent overwriting an existing image
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{__import__('uuid').uuid4().hex[:8]}{ext.lower()}"

        image_file.save(
            os.path.join(app.config['UPLOAD_FOLDER'], filename)
        )

        conn = get_db_connection()

        conn.execute("""
            INSERT INTO banners
                (title, subtitle, image, button_text, link, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title,
            subtitle,
            filename,
            button_text or 'Shop Now',
            link or '/products',
            is_active
        ))

        conn.commit()
        conn.close()

        flash('Banner added successfully!', 'success')
        return redirect('/admin/banners')

    return render_template('admin_banner_form.html', banner=None)


@app.route('/admin/banners/edit/<int:banner_id>',
           methods=['GET', 'POST'])
def admin_edit_banner(banner_id):
    if not admin_required():
        flash('Please login first!', 'danger')
        return redirect('/admin/login')

    conn = get_db_connection()

    banner = conn.execute(
        "SELECT * FROM banners WHERE id = ?",
        (banner_id,)
    ).fetchone()

    conn.close()

    if banner is None:
        flash('Banner not found.', 'danger')
        return redirect('/admin/banners')

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        subtitle = request.form.get('subtitle', '').strip()
        button_text = request.form.get('button_text', 'Shop Now').strip()
        link = request.form.get('link', '/products').strip()
        is_active = 1 if request.form.get('is_active') == '1' else 0
        image_file = request.files.get('image')

        if not title:
            flash('Please enter a banner title.', 'danger')
            return redirect(f'/admin/banners/edit/{banner_id}')

        new_filename = banner['image']

        if image_file and image_file.filename:
            if not allowed_banner_file(image_file.filename):
                flash('Only PNG, JPG, JPEG, WEBP and GIF images are allowed.', 'danger')
                return redirect(f'/admin/banners/edit/{banner_id}')

            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

            filename = secure_filename(image_file.filename)
            name, ext = os.path.splitext(filename)
            new_filename = (
                f"{name}_{__import__('uuid').uuid4().hex[:8]}{ext.lower()}"
            )

            image_file.save(
                os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            )

        conn = get_db_connection()

        conn.execute("""
            UPDATE banners
            SET title = ?,
                subtitle = ?,
                image = ?,
                button_text = ?,
                link = ?,
                is_active = ?
            WHERE id = ?
        """, (
            title,
            subtitle,
            new_filename,
            button_text or 'Shop Now',
            link or '/products',
            is_active,
            banner_id
        ))

        conn.commit()
        conn.close()

        flash('Banner updated successfully!', 'success')
        return redirect('/admin/banners')

    return render_template(
        'admin_banner_form.html',
        banner=banner
    )


@app.route('/admin/banners/delete/<int:banner_id>',
           methods=['POST'])
def admin_delete_banner(banner_id):
    if not admin_required():
        flash('Please login first!', 'danger')
        return redirect('/admin/login')

    conn = get_db_connection()

    banner = conn.execute(
        "SELECT image FROM banners WHERE id = ?",
        (banner_id,)
    ).fetchone()

    if banner is None:
        conn.close()
        flash('Banner not found.', 'danger')
        return redirect('/admin/banners')

    conn.execute(
        "DELETE FROM banners WHERE id = ?",
        (banner_id,)
    )

    conn.commit()
    conn.close()

    # Remove the image belonging to this banner
    image_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        banner['image']
    )

    if os.path.isfile(image_path):
        os.remove(image_path)

    flash('Banner deleted successfully!', 'success')
    return redirect('/admin/banners')




if __name__ == '__main__':
    app.run(host="0.0.0.0",port=5000,debug=True)
