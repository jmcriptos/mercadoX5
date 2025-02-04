import os
import logging
from datetime import datetime
from enum import Enum
from flask import Flask, json, render_template, request, redirect, url_for, jsonify, send_from_directory, make_response, flash, abort, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError, DatabaseError
from flask_migrate import Migrate
from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, SubmitField, StringField, DateField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo
from sqlalchemy import func
from functools import wraps
from datetime import datetime, timedelta

# Importaciones para manejo de usuarios
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Configuración de logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Definición de roles de usuario
class UserRole(Enum):
    ADMIN = 'admin'
    REGISTRO = 'registro'
    CONSULTA = 'consulta'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'caracas'

# Configuración de mensajes flash
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)

ENV = 'prod'

if ENV == 'dev':
    app.debug = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Casco2021*@localhost:5432/postgres'
else:
    app.debug = False
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("No database URL configured. Set DATABASE_URL environment variable.")
    db_url = db_url.replace('postgres://', 'postgresql://')
    if not db_url.endswith('?sslmode=require'):
        db_url += '?sslmode=require'
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Decoradores para control de acceso
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def registro_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_registro:
            flash('No tienes permisos para acceder a esta sección.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ----------------------------------------------------------------
# CONFIGURACIÓN DE FLASK-LOGIN
# ----------------------------------------------------------------
login = LoginManager(app)
login.login_view = 'login'

# ----------------------------------------------------------------
# MODELOS
# ----------------------------------------------------------------
class Store(db.Model):
    __tablename__ = 'store'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    address = db.Column(db.String(100), nullable=False)

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100))
    presentation = db.Column(db.String(100))
    distributor = db.Column(db.String(100))

class Price(db.Model):
    __tablename__ = 'price'
    id = db.Column(db.Integer, primary_key=True)
    price = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    presentation = db.Column(db.String(100))
    brand = db.Column(db.String(100))

    # Relaciones
    product = db.relationship('Product', backref='prices')
    store = db.relationship('Store', backref='prices')

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), nullable=False, default=UserRole.CONSULTA.value)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN.value  # Compara con 'admin'
    
    @property
    def is_registro(self):
        return self.role in [UserRole.ADMIN.value, UserRole.REGISTRO.value]  # Compara con ['admin', 'registro']

    def __repr__(self):
        return f'<User {self.username} (role: {self.role})>'

@login.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------------------------------------------------------
# FORMULARIOS
# ----------------------------------------------------------------
class PriceForm(FlaskForm):
    product = SelectField('Producto', validators=[DataRequired()])
    store = SelectField('Tienda', coerce=int, validators=[DataRequired()])
    price = DecimalField('Precio', validators=[DataRequired()])
    date = DateField('Fecha', format='%Y-%m-%d', validators=[DataRequired()])
    brand = SelectField('Marca', choices=[('', 'Seleccione una marca')], validators=[DataRequired()])
    submit = SubmitField('Enviar')

class RegistrationForm(FlaskForm):
    username = StringField('Nombre de usuario', validators=[DataRequired()])
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    password2 = PasswordField('Confirmar contraseña', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrarse')

class LoginForm(FlaskForm):
    username = StringField('Nombre de usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    remember_me = BooleanField('Recordarme')
    submit = SubmitField('Iniciar sesión')

class UserEditForm(FlaskForm):
    username = StringField('Nombre de usuario', validators=[DataRequired()])
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])
    role = SelectField('Rol', choices=[], validators=[DataRequired()])
    password = PasswordField('Nueva contraseña')
    password2 = PasswordField('Confirmar nueva contraseña', validators=[EqualTo('password')])
    submit = SubmitField('Guardar cambios')

# ----------------------------------------------------------------
# RUTAS DE ADMINISTRACIÓN
# ----------------------------------------------------------------
@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    return render_template('admin/panel.html')

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserEditForm(obj=user)
    form.role.choices = [(role.value, role.name) for role in UserRole]
    
    if form.validate_on_submit():
        try:
            user.username = form.username.data
            user.email = form.email.data
            user.role = form.role.data
            if form.password.data:
                user.set_password(form.password.data)
            
            db.session.commit()
            flash('Usuario actualizado exitosamente', 'success')
            return redirect(url_for('admin_users'))
        except IntegrityError:
            db.session.rollback()
            flash('Error: El nombre de usuario o correo ya están en uso', 'danger')
    
    return render_template('admin/edit_user.html', form=form, user=user)

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    if current_user.id == user_id:
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('admin_users'))
    
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('Usuario eliminado exitosamente', 'success')
    return redirect(url_for('admin_users'))

# ----------------------------------------------------------------
# RUTAS PÚBLICAS
# ----------------------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'GET':
        session.pop('_flashes', None)
        
    form = RegistrationForm()
    if form.validate_on_submit():  # Verifica si el formulario se envió y es válido
        try:
            # Verificar si el usuario o email ya existe
            existing_user = User.query.filter(
                (User.username == form.username.data) | 
                (User.email == form.email.data)
            ).first()
            
            if existing_user:
                if existing_user.username == form.username.data:
                    flash('El nombre de usuario ya está en uso.')
                else:
                    flash('El correo electrónico ya está en uso.')
                return render_template('register.html', form=form)
            
            # Crear nuevo usuario
            user = User(
                username=form.username.data,
                email=form.email.data,
                role=UserRole.CONSULTA.value
            )
            user.set_password(form.password.data)
            
            db.session.add(user)
            db.session.commit()
            flash('Te has registrado exitosamente. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar usuario: {str(e)}')
            return render_template('register.html', form=form)
        
    # Si hay errores en el formulario
    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'Error en {field}: {error}')
                
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Nombre de usuario o contraseña incorrectos.')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        flash('Has iniciado sesión correctamente.')
        return redirect(url_for('index'))
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión.')
    return redirect(url_for('login'))

# ----------------------------------------------------------------
# RUTAS PROTEGIDAS
# ----------------------------------------------------------------
@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/add_store', methods=['GET', 'POST'])
@login_required
@registro_required
def add_store():
    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']
        existing_store = Store.query.filter_by(name=name).first()
        if existing_store:
            error_message = "La tienda con ese nombre ya existe."
            return render_template('add_store.html', error_message=error_message)
        new_store = Store(name=name, address=address)
        db.session.add(new_store)
        try:
            db.session.commit()
            return redirect(url_for('stores'))
        except IntegrityError:
            db.session.rollback()
            error_message = "Ocurrió un error al intentar agregar la tienda."
            return render_template('add_store.html', error_message=error_message)
    return render_template('add_store.html')

@app.route('/stores', methods=['GET', 'POST'])
@login_required
def stores():
    stores_data = Store.query.order_by(Store.id).all()
    return render_template('stores.html', stores=stores_data)

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
@registro_required
def add_product():
    if request.method == 'POST':
        try:
            name = request.form['name'].strip()
            brand = request.form['brand'].strip()
            presentation = request.form['presentation'].strip()
            distributor = request.form['distributor'].strip()

            # Validación inicial
            if not name or not brand or not presentation:
                raise ValueError("Todos los campos marcados son requeridos.")

            # Verificar producto existente
            existing_product = Product.query.filter_by(
                name=name, 
                brand=brand,
                presentation=presentation
            ).first()
            
            if existing_product:
                raise ValueError(
                    f"Ya existe un producto '{name}' con la marca '{brand}' "
                    f"y presentación '{presentation}'."
                )

            new_product = Product(
                name=name,
                brand=brand,
                presentation=presentation,
                distributor=distributor
            )
            
            db.session.add(new_product)
            db.session.commit()
            
            flash('Producto agregado exitosamente', 'success')
            return redirect(url_for('products'))

        except ValueError as ve:
            flash(str(ve), 'error')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error al agregar producto: {str(e)}")
            flash('Error al agregar el producto', 'error')
    
    products = Product.query.order_by(Product.name).all()
    return render_template('add_product.html', products=products)

@app.route('/products', methods=['GET', 'POST'])
@login_required
def products():
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'id')
    page = request.args.get('page', 1, type=int)
    query = Product.query

    if search:
        query = query.filter(
            Product.name.ilike(f'%{search}%') |
            Product.brand.ilike(f'%{search}%') |
            Product.presentation.ilike(f'%{search}%') |
            Product.distributor.ilike(f'%{search}%')
        )
    if sort == 'name':
        query = query.order_by(Product.name)
    elif sort == 'brand':
        query = query.order_by(Product.brand)
    elif sort == 'presentation':
        query = query.order_by(Product.presentation)
    elif sort == 'distributor':
        query = query.order_by(Product.distributor)
    else:
        query = query.order_by(Product.id)
    products_pag = query.paginate(page=page, per_page=25)
    return render_template('products.html', products=products_pag, search=search, sort=sort)

@app.route('/export_products')
@login_required
def export_products():
    products_data = Product.query.all()
    csv_data = 'ID,Nombre,Marca,Presentación,Distribuidor\n'
    for product in products_data:
        csv_data += (
            f"{product.id},"
            f"{product.name},"
            f"{product.brand},"
            f"{product.presentation},"
            f"{product.distributor}\n"
        )
    response = make_response(csv_data)
    response.headers['Content-Disposition'] = 'attachment; filename=products.csv'
    response.mimetype = 'text/csv'
    return response

@app.route('/add_price', methods=['GET', 'POST'])
@login_required
@registro_required
def add_price():
    form = PriceForm()
    
    # Obtener nombres únicos de productos ordenados alfabéticamente
    unique_products = db.session.query(Product.name)\
        .distinct()\
        .order_by(Product.name)\
        .all()
    
    # Inicializar las choices para todos los SelectFields
    form.product.choices = [(name[0], name[0]) for name in unique_products]
    form.store.choices = [(st.id, st.name) for st in Store.query.order_by(Store.name).all()]
    form.brand.choices = [('', 'Seleccione una marca')]  # Opción por defecto
    
    if request.method == 'POST':
        try:
            # Obtener los datos del formulario
            product_name = request.form.get('product')
            brand = request.form.get('brand')
            store_id = request.form.get('store')
            presentation = request.form.get('presentation')
            price_value = request.form.get('price')
            date_value = request.form.get('date')
            
            # Validaciones básicas
            if not all([product_name, brand, store_id, presentation, price_value, date_value]):
                flash('Todos los campos son requeridos.')
                return render_template('add_price.html', form=form)
            
            # Obtener el producto
            product = Product.query.filter_by(name=product_name).first()
            if not product:
                flash('Producto no encontrado.')
                return render_template('add_price.html', form=form)

            # Crear el nuevo precio
            new_price = Price(
                product_id=product.id,
                brand=brand,
                store_id=int(store_id),
                presentation=presentation,
                price=float(price_value),
                date=datetime.strptime(date_value, '%Y-%m-%d')
            )
            
            db.session.add(new_price)
            db.session.commit()
            flash('Precio agregado exitosamente.')
            return redirect(url_for('prices'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al agregar precio: {str(e)}")
            flash('Error al agregar el precio. Por favor, intente nuevamente.')
            return render_template('add_price.html', form=form)
    
    return render_template('add_price.html', form=form)

@app.route('/get_product_details/<string:product_name>')
@login_required
def get_product_details(product_name):
    # Obtener marcas y presentaciones tanto de la tabla Product como de Price
    product_data = db.session.query(Product.brand, Product.presentation)\
        .filter(Product.name == product_name)\
        .distinct()\
        .all()
    
    price_data = db.session.query(Price.brand, Price.presentation)\
        .join(Product)\
        .filter(Product.name == product_name)\
        .distinct()\
        .all()
    
    # Combinar los datos en una estructura jerárquica
    brand_presentation_map = {}
    
    # Agregar datos de la tabla Product
    for brand, presentation in product_data:
        if brand and brand.strip():  # Verificar que la marca no esté vacía
            if brand not in brand_presentation_map:
                brand_presentation_map[brand] = set()
            if presentation and presentation.strip():
                brand_presentation_map[brand].add(presentation)
    
    # Agregar datos de la tabla Price
    for brand, presentation in price_data:
        if brand and brand.strip():
            if brand not in brand_presentation_map:
                brand_presentation_map[brand] = set()
            if presentation and presentation.strip():
                brand_presentation_map[brand].add(presentation)
    
    # Verificar si hay datos en el producto base
    product = Product.query.filter_by(name=product_name).first()
    if product and product.brand and product.brand.strip():
        if product.brand not in brand_presentation_map:
            brand_presentation_map[product.brand] = set()
        if product.presentation and product.presentation.strip():
            brand_presentation_map[product.brand].add(product.presentation)
    
    # Convertir a formato para JSON
    result = {
        'brands': sorted(brand_presentation_map.keys()),
        'presentationsByBrand': {
            brand: sorted(list(presentations))
            for brand, presentations in brand_presentation_map.items()
        }
    }
    
    # Agregar log para depuración
    app.logger.info(f"Product details for {product_name}: {result}")
    
    return jsonify(result)

@app.route('/add_price_form', methods=['GET'])
@login_required
@registro_required
def show_add_price_form():
    form = PriceForm()
    form.product.choices = [(prod.id, prod.name) for prod in Product.query.all()]
    form.store.choices = [(st.id, st.name) for st in Store.query.all()]
    brands = db.session.query(Product.brand).distinct().all()
    brand_choices = [(b[0], b[0]) for b in brands if b[0]]
    form.brand.choices = brand_choices
    return render_template('add_price.html', form=form)

@app.route('/prices', methods=['GET', 'POST'])
@login_required
def prices():
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'id')
    page = request.args.get('page', 1, type=int)
    query = Price.query
    if search:
        query = query.filter(
            Price.product.has(Product.name.ilike(f'%{search}%')) |
            Price.store.has(Store.name.ilike(f'%{search}%')) |
            Price.presentation.ilike(f'%{search}%') |
            Price.brand.ilike(f'%{search}%')
        )
    if sort == 'product':
        query = query.join(Product).order_by(Product.name)
    elif sort == 'store':
        query = query.join(Store).order_by(Store.name)
    elif sort == 'presentation':
        query = query.order_by(Price.presentation)
    elif sort == 'brand':
        query = query.order_by(Price.brand)
    elif sort == 'price':
        query = query.order_by(Price.price)
    elif sort == 'date':
        query = query.order_by(Price.date)
    else:
        query = query.order_by(Price.id)
    prices_pag = query.paginate(page=page, per_page=25)
    return render_template('prices.html', prices=prices_pag, search=search, sort=sort)

@app.route('/edit_price/<int:price_id>', methods=['GET', 'POST'])
@login_required
@admin_required  # Cambiado de registro_required a admin_required
def edit_price(price_id):
    # Verificación adicional de rol de administrador
    if not current_user.is_admin:
        flash('No tienes permisos para editar precios.', 'error')
        return redirect(url_for('prices'))

    price = Price.query.get_or_404(price_id)
    form = PriceForm()

    # Cargar las opciones para los SelectFields
    form.product.choices = [(p.name, p.name) for p in Product.query.order_by(Product.name).distinct()]
    form.store.choices = [(st.id, st.name) for st in Store.query.order_by(Store.name).all()]
    form.brand.choices = [('', 'Seleccione una marca')]

    if request.method == 'GET':
        # Prellenar el formulario con los datos existentes
        form.product.data = price.product.name
        form.store.data = price.store_id
        form.brand.data = price.brand
        form.presentation.data = price.presentation
        form.price.data = price.price
        form.date.data = price.date

    if request.method == 'POST':
        try:
            # Log de la acción
            app.logger.info(f"Usuario {current_user.username} está editando el precio ID: {price_id}")
            
            # Obtener el producto por nombre
            product = Product.query.filter_by(name=request.form.get('product')).first()
            if not product:
                flash('Producto no encontrado')
                return redirect(url_for('prices'))

            # Actualizar los campos
            price.product_id = product.id
            price.store_id = int(request.form.get('store'))
            price.brand = request.form.get('brand')
            price.presentation = request.form.get('presentation')
            price.price = float(request.form.get('price'))
            price.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')

            db.session.commit()
            
            # Log del éxito
            app.logger.info(f"Precio ID: {price_id} actualizado exitosamente por {current_user.username}")
            flash('Precio actualizado exitosamente')
            return redirect(url_for('prices'))
            
        except Exception as e:
            db.session.rollback()
            # Log del error
            app.logger.error(f"Error al actualizar precio ID: {price_id} - {str(e)}")
            flash(f'Error al actualizar el precio: {str(e)}')
            return redirect(url_for('edit_price', price_id=price_id))

    return render_template('edit_price.html', form=form, price=price)

@app.route('/delete_price/<int:price_id>', methods=['POST'])
@login_required
@admin_required
def delete_price(price_id):
    try:
        price = Price.query.get_or_404(price_id)
        db.session.delete(price)
        db.session.commit()
        flash('Precio eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error al eliminar precio: {str(e)}")
        flash('Error al eliminar el precio', 'error')
    
    return redirect(url_for('prices'))

@app.route('/export_prices')
@login_required
def export_prices():
    prices_data = Price.query.all()
    csv_data = 'ID,Producto,Marca,Tienda,Presentación,Precio,Fecha\n'
    for p in prices_data:
        csv_data += (
            f"{p.id},"
            f"{p.product.name},"
            f"{p.brand},"
            f"{p.store.name},"
            f"{p.presentation},"
            f"{p.price},"
            f"{p.date.strftime('%Y-%m-%d')}\n"
        )
    response = make_response(csv_data)
    response.headers['Content-Disposition'] = 'attachment; filename=prices.csv'
    response.mimetype = 'text/csv'
    return response

@app.route('/get_product_filters', methods=['GET'])
@login_required
def get_product_filters():
    product_name = request.args.get('product_name')
    if not product_name:
        return jsonify({'brands': [], 'presentations': []})
    brands = db.session.query(Price.brand).join(Product).filter(
        Product.name == product_name,
        Price.brand.isnot(None)
    ).distinct().all()
    presentations = db.session.query(Price.presentation).join(Product).filter(
        Product.name == product_name,
        Price.presentation.isnot(None)
    ).distinct().all()
    brands = [b[0] for b in brands if b[0]]
    presentations = [p[0] for p in presentations if p[0]]
    if not brands:
        product = Product.query.filter_by(name=product_name).first()
        if product and product.brand:
            brands = [product.brand]
    if not presentations:
        product = Product.query.filter_by(name=product_name).first()
        if product and product.presentation:
            presentations = [product.presentation]
    return jsonify({'brands': brands, 'presentations': presentations})

@app.route('/generate_graph', methods=['GET'])
@login_required
def show_generate_graph():
    try:
        # Obtener nombres únicos de productos
        products = [p[0] for p in db.session.query(Product.name)
                    .distinct().order_by(Product.name).all()]
        stores = Store.query.order_by(Store.name).all()
        all_brands = db.session.query(Price.brand).distinct().filter(Price.brand.isnot(None)).all()
        all_brands = [b[0] for b in all_brands]
        all_presentations = db.session.query(Price.presentation).distinct().filter(Price.presentation.isnot(None)).all()
        all_presentations = [p[0] for p in all_presentations]
        today = datetime.now().strftime('%Y-%m-%d')
        return render_template(
            'generate_graph.html',
            products=products,       # Ahora es una lista de nombres (str)
            stores=stores,
            all_brands=all_brands,
            all_presentations=all_presentations,
            today=today
        )
    except Exception as e:
        logger.error(f"Error in show_generate_graph: {str(e)}")
        return render_template('error.html', error="Error al cargar la página de gráficos")


@app.route('/graph', methods=['POST'])
@login_required
def generate_graph():
    try:
        form_data = {
            'start_date': request.form.get('start_date'),
            'end_date': request.form.get('end_date'),
            'product_name': request.form.get('product_name'),
            'brand': request.form.get('brand'),
            'store': request.form.get('store'),
            'presentation': request.form.get('presentation')
        }
        required_fields = ['start_date', 'end_date']
        for field in required_fields:
            if not form_data[field]:
                raise ValueError(f"Campo requerido faltante: {field}")
        query = (
            db.session.query(
                Price.date,
                Price.price,
                Store.name.label('store_name'),
                Price.brand,
                Product.name.label('product_name'),
                Price.presentation
            )
            .join(Product)
            .join(Store)
            .filter(Price.date.between(form_data['start_date'], form_data['end_date']))
        )
        if form_data['product_name'] and form_data['product_name'] != 'all':
            query = query.filter(Product.name == form_data['product_name'])
        if form_data['brand'] and form_data['brand'] != 'all':
            query = query.filter(Price.brand == form_data['brand'])
        if form_data['store'] and form_data['store'] != 'all':
            query = query.filter(Store.id == form_data['store'])
        if form_data['presentation'] and form_data['presentation'] != 'all':
            query = query.filter(Price.presentation == form_data['presentation'])
        query = query.order_by(Price.date)
        results = query.all()
        if not results:
            return jsonify({'error': 'No se encontraron datos con estos filtros'}), 404
        grouped_data = {}
        for row in results:
            if form_data['brand'] != 'all':
                key = row.store_name
                label = row.store_name
            else:
                key = f"{row.store_name}-{row.brand}"
                label = f"{row.store_name} - {row.brand}"
            if key not in grouped_data:
                grouped_data[key] = {
                    'dates': [],
                    'prices': [],
                    'label': label
                }
            grouped_data[key]['dates'].append(row.date.strftime('%Y-%m-%d'))
            grouped_data[key]['prices'].append(float(row.price))
        data_series = list(grouped_data.values())
        producto = form_data['product_name'] if form_data['product_name'] != 'all' else 'Todos los productos'
        marca = form_data['brand'] if form_data['brand'] != 'all' else 'Todas las marcas'
        presentacion = form_data['presentation'] if form_data['presentation'] != 'all' else 'Todas las presentaciones'
        titulo = f"{producto} | {marca} | {presentacion}"
        plot_data = {'title': titulo, 'data': data_series}
        return jsonify(plot_data)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Error en /graph: {e}")
        return jsonify({'error': 'Error al generar el gráfico'}), 500

@app.route('/show_graph')
@login_required
def show_graph():
    form_data = {
        "start_date": "2023-01-01",
        "end_date": "2025-01-31",
        "product_name": "Deviled Ham",
        "brand": "Underwood",
        "store": "all",
        "presentation": "120 g"
    }
    base_query = build_base_query(form_data)
    legend_group, legend_key = determine_legend_grouping(form_data, base_query)
    data_series = build_data_series(base_query, legend_group, legend_key)
    title_suffix = ""
    if form_data["brand"] != "all":
        title_suffix = f"\nMarca: {form_data['brand']}"
    elif form_data["store"] != "all":
        store_obj = Store.query.get(int(form_data["store"]))
        if store_obj:
            title_suffix = f"\nTienda: {store_obj.name}"
    else:
        title_suffix = "\nMarca: Todas"
    plot_data = {
        "title": f"Precio de {form_data['product_name']} ({form_data['presentation']}){title_suffix}",
        "data": data_series
    }
    return render_template('graph.html', data=plot_data)

def extract_form_data(form):
    return {
        "start_date": form.get('start_date'),
        "end_date": form.get('end_date'),
        "product_name": form.get('product_name'),
        "presentation": form.get('presentation'),
        "store": form.get('store'),
        "brand": form.get('brand')
    }

def build_base_query(form_data):
    product = Product.query.filter_by(name=form_data['product_name']).first()
    if not product:
        return jsonify({"error": "Producto no encontrado."}), 404
    query = Price.query.filter(
        Price.product_id == product.id,
        Price.date.between(form_data['start_date'], form_data['end_date'])
    )
    if form_data['presentation'] != 'all':
        query = query.filter(Price.presentation == form_data['presentation'])
    if form_data['store'] != "all":
        store_id = int(form_data['store'])
        query = query.filter(Price.store_id == store_id)
    if form_data['brand'] != "all":
        query = query.filter(Price.brand == form_data['brand'])
    return query

def determine_legend_grouping(form_data, query):
    if form_data['store'] == "all" and form_data['brand'] == "all":
        distinct_brands = query.with_entities(Price.brand).distinct().all()
        return distinct_brands, 'brand'
    elif form_data['brand'] != "all":
        distinct_stores = query.with_entities(Price.store_id).distinct().all()
        return distinct_stores, 'store_id'
    else:
        distinct_brands = query.with_entities(Price.brand).distinct().all()
        return distinct_brands, 'brand'

def build_data_series(query, legend_group, legend_key):
    data_series = []
    for item in legend_group:
        key_value = getattr(item, legend_key)
        prices_for_group = (
            query.filter_by(**{legend_key: key_value})
            .group_by(func.date(Price.date))
            .with_entities(
                func.date(Price.date),
                func.avg(Price.price)
            )
            .all()
        )
        dates = [pf[0].strftime('%Y-%m-%d') for pf in prices_for_group]
        prices = [pf[1] for pf in prices_for_group]
        if legend_key == 'brand':
            label = key_value
        else:
            store = Store.query.get(key_value)
            label = store.name if store else 'Desconocido'
        data_series.append({
            'label': label,
            'dates': dates,
            'prices': prices,
        })
    return data_series

if __name__ == '__main__':
    app.run(debug=True)
