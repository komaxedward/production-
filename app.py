from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, make_response
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
from werkzeug.utils import secure_filename
from io import BytesIO
from datetime import datetime, timedelta
from pytz import timezone
import pytz
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://inventory_95cp_user:d3PMapaPFsDCDreuAKfxQlIX9DhagDsY@dpg-ctifm9ggph6c73864kn0-a.oregon-postgres.render.com/inventory_95cp'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
db = SQLAlchemy(app)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_code = db.Column(db.String(100), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    product_type = db.Column(db.String(100), nullable=False)
    image_url = db.Column(db.String(200))
    quantity = db.Column(db.Integer, default=0)
    material_code = db.Column(db.String(100))


class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_code = db.Column(db.String(100), nullable=False)
    material_name = db.Column(db.String(100), nullable=False)
    material_type = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=0)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False)
    time = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.Column(db.String(100), nullable=False)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Check user credentials
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session.permanent = True
            session['username'] = user.username
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')

    return render_template('login.html')


@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        search_query = request.form.get('search_query')
        if search_query:
            codes = [code.strip() for code in search_query.split(',')]
            products = Product.query.filter(Product.product_code.in_(codes)).all()
            materials = Material.query.filter(Material.material_code.in_(codes)).all()
        else:
            products = Product.query.all()
            materials = Material.query.all()
    else:
        products = Product.query.all()
        materials = Material.query.all()

    return render_template('dashboard.html', products=products, materials=materials)


@app.route('/add_material', methods=['POST'])
def add_material():
    material_code = request.form.get('material_code')
    material_name = request.form.get('material_name')
    material_type = request.form.get('material_type')

    new_material = Material(
        material_code=material_code,
        material_name=material_name,
        material_type=material_type,
    )
    db.session.add(new_material)
    db.session.commit()

    flash('Material added successfully!')
    return redirect(url_for('dashboard'))


@app.route('/associate_material', methods=['POST'])
def associate_material():
    product_code = request.form.get('product_code')
    material_code = request.form.get('material_code')

    product = Product.query.filter_by(product_code=product_code).first()
    if product:
        product.material_code = material_code
        db.session.commit()
        flash('Material associated successfully!')
    else:
        flash('Product not found!')

    return redirect(url_for('dashboard'))


@app.route('/import_excel', methods=['POST'])
def import_excel():
    file = request.files['file']
    if file:
        filename = secure_filename(file.filename)
        file_path = f'static/uploads/{filename}'
        file.save(file_path)

        # 读取产品数据
        product_df = pd.read_excel(file_path, sheet_name='产品')
        for _, row in product_df.iterrows():
            product = Product.query.filter_by(product_code=row['产品号码']).first()
            if not product:
                new_product = Product(
                    product_code=row['产品号码'],
                    product_name=row['产品名称'],
                    product_type=row['产品类型'],
                    quantity=row['产品数量'],
                    material_code=row['关联的原材料号码']
                )
                db.session.add(new_product)

        # 读取原材料数据
        material_df = pd.read_excel(file_path, sheet_name='原材料')
        for _, row in material_df.iterrows():
            material = Material.query.filter_by(material_code=row['原材料号码']).first()
            if not material:
                new_material = Material(
                    material_code=row['原材料号码'],
                    material_name=row['原材料名称'],
                    material_type=row['原材料类型'],
                    quantity=row['原材料数量']
                )
                db.session.add(new_material)

        db.session.commit()
        flash('Data imported successfully!')

    return redirect(url_for('dashboard'))


@app.route('/batch_material_inbound', methods=['GET', 'POST'])
def batch_material_inbound():
    if request.method == 'POST':
        material_codes = request.form.getlist('material_code[]')
        quantities = request.form.getlist('quantity[]', type=int)

        for material_code, quantity in zip(material_codes, quantities):
            material = Material.query.filter_by(material_code=material_code).first()
            if material:
                material.quantity += quantity
                transaction = Transaction(
                    number=material.material_code,
                    name=material.material_name,
                    type=material.material_type,
                    quantity=quantity,
                    transaction_type='入库',
                    user=session.get('username', 'unknown')  # Use logged-in user
                )
                db.session.add(transaction)
            else:
                flash(f'Material with code {material_code} not found!')

        db.session.commit()
        flash('Materials updated successfully!')
        return redirect(url_for('dashboard'))

    return render_template('batch_material_inbound.html')


@app.route('/get_material/<material_code>', methods=['GET'])
def get_material(material_code):
    material = Material.query.filter_by(material_code=material_code).first()
    if material:
        return {
            'material_name': material.material_name,
            'material_type': material.material_type
        }
    return {}


@app.route('/batch_product_inbound', methods=['GET', 'POST'])
def batch_product_inbound():
    if request.method == 'POST':
        product_codes = request.form.getlist('product_code[]')
        quantities = request.form.getlist('quantity[]', type=int)
        material_quantities = request.form.getlist('material_quantity[]', type=int)

        for product_code, quantity, material_quantity in zip(product_codes, quantities, material_quantities):
            product = Product.query.filter_by(product_code=product_code).first()
            if product:
                product.quantity += quantity
                transaction = Transaction(
                    number=product.product_code,
                    name=product.product_name,
                    type=product.product_type,
                    quantity=quantity,
                    transaction_type='入库',
                    user=session.get('username', 'unknown')
                )
                db.session.add(transaction)

                if product.material_code:
                    material = Material.query.filter_by(material_code=product.material_code).first()
                    if material:
                        material.quantity -= material_quantity
                        material_transaction = Transaction(
                            number=material.material_code,
                            name=material.material_name,
                            type=material.material_type,
                            quantity=material_quantity,
                            transaction_type='出库',
                            user=session.get('username', 'unknown')
                        )
                        db.session.add(material_transaction)
            else:
                flash(f'Product with code {product_code} not found!')

        db.session.commit()
        flash('Products and materials updated successfully!')
        return redirect(url_for('dashboard'))

    return render_template('batch_product_inbound.html')


@app.route('/batch_product_outbound', methods=['GET', 'POST'])
def batch_product_outbound():
    if request.method == 'POST':
        product_codes = request.form.getlist('product_code[]')
        quantities = request.form.getlist('quantity[]', type=int)

        for product_code, quantity in zip(product_codes, quantities):
            product = Product.query.filter_by(product_code=product_code).first()
            if product:
                product.quantity -= quantity
                transaction = Transaction(
                    number=product.product_code,
                    name=product.product_name,
                    type=product.product_type,
                    quantity=quantity,
                    transaction_type='出库',
                    user=session.get('username', 'unknown')  # Use logged-in user
                )
                db.session.add(transaction)
            else:
                flash(f'Product with code {product_code} not found!')

        db.session.commit()
        flash('Products updated successfully!')
        return redirect(url_for('dashboard'))

    return render_template('batch_product_outbound.html')


@app.route('/export_excel', methods=['GET'])
def export_excel():
    # Query data from the database
    products = Product.query.all()
    materials = Material.query.all()
    transactions = Transaction.query.all()

    # Timezone conversion
    utc = pytz.utc
    beijing_tz = timezone('Asia/Shanghai')

    # Create dataframes
    product_data = {
        '产品号码': [p.product_code for p in products],
        '产品名称': [p.product_name for p in products],
        '产品类型': [p.product_type for p in products],
        '产品数量': [p.quantity for p in products],
        '关联的原材料号码': [p.material_code for p in products]
    }
    material_data = {
        '原材料号码': [m.material_code for m in materials],
        '原材料名称': [m.material_name for m in materials],
        '原材料类型': [m.material_type for m in materials],
        '原材料数量': [m.quantity for m in materials]
    }
    transaction_data = {
        '号码': [t.number for t in transactions],
        '名称': [t.name for t in transactions],
        '类型': [t.type for t in transactions],
        '交易数量': [t.quantity for t in transactions],
        '交易类型': [t.transaction_type for t in transactions],
        '时间': [t.time.replace(tzinfo=utc).astimezone(beijing_tz).strftime('%Y-%m-%d %H:%M:%S') for t in transactions],
        '交易人员': [t.user for t in transactions]
    }

    # Create Excel writer
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')

    # Write dataframes to Excel
    pd.DataFrame(product_data).to_excel(writer, sheet_name='产品', index=False)
    pd.DataFrame(material_data).to_excel(writer, sheet_name='原材料', index=False)
    pd.DataFrame(transaction_data).to_excel(writer, sheet_name='交易信息', index=False)

    writer.close()
    output.seek(0)

    return send_file(output, download_name='inventory.xlsx', as_attachment=True)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        admin_username = request.form.get('admin_username')
        admin_password = request.form.get('admin_password')
        new_username = request.form.get('new_username')
        new_password = request.form.get('new_password')

        # Check admin credentials
        if admin_username == 'admin' and admin_password == 'password':  # Replace with secure check
            # Check if the new username already exists
            if User.query.filter_by(username=new_username).first():
                flash('Username already exists!')
            else:
                # Create new user
                new_user = User(username=new_username, password=new_password)
                db.session.add(new_user)
                db.session.commit()
                flash('User registered successfully!')
                return redirect(url_for('login'))
        else:
            flash('Invalid admin credentials!')

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('login'))


@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(port=5000)
