
import os
import sqlite3
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms.fields import PasswordField

# --- 1. CONFIGURACIÓN INICIAL DE LA APLICACIÓN ---
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)

# Configuración de Seguridad y Base de Datos
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or 'una_clave_secreta_local_para_pruebas_DEBES_CAMBIARLA'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' 

# --- 2. MODELOS DE BASE DE DATOS ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Truck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(20), unique=True, nullable=False)
    location = db.Column(db.String(100), default='')
    # Storing dates as ISO strings (YYYY-MM-DD) to match frontend logic simply
    location_last_updated = db.Column(db.String(20), default='2000-01-01') 
    creation_date = db.Column(db.String(20), nullable=False)
    deletion_date = db.Column(db.String(20), nullable=True)
    is_location_manual = db.Column(db.Boolean, default=False)
    zones_str = db.Column(db.String(200), default='') 

    def to_dict(self):
        return {
            'plate': self.plate,
            'location': self.location,
            'locationLastUpdatedDate': self.location_last_updated,
            'creationDate': self.creation_date,
            'deletionDate': self.deletion_date,
            'isLocationManual': self.is_location_manual,
            'zones': self.zones_str.split(',') if self.zones_str else []
        }

class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False) # 'departure', 'return'
    client = db.Column(db.String(100), nullable=False)
    driver = db.Column(db.String(100), default='')
    origin = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    load_date = db.Column(db.String(20), nullable=False)
    unload_date = db.Column(db.String(20), nullable=False)
    
    assigned_truck_plate = db.Column(db.String(20), db.ForeignKey('truck.plate'), nullable=True)
    assigned_slot = db.Column(db.Integer, nullable=True)
    
    is_urgent = db.Column(db.Boolean, default=False)
    is_groupage = db.Column(db.Boolean, default=False)
    zone = db.Column(db.String(50), nullable=True)
    
    pg = db.Column(db.Integer, default=0)
    ep = db.Column(db.Integer, default=0)
    pp = db.Column(db.Integer, default=0)
    
    notify_time = db.Column(db.String(20), default="")
    is_notified = db.Column(db.Boolean, default=False)

    assigned_truck = db.relationship('Truck', backref=db.backref('trips', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'client': self.client,
            'driver': self.driver,
            'origin': self.origin,
            'destination': self.destination,
            'loadDate': self.load_date,
            'unloadDate': self.unload_date,
            'assignedTruck': self.assigned_truck_plate,
            'assignedSlot': self.assigned_slot,
            'isUrgent': self.is_urgent,
            'isGroupage': self.is_groupage,
            'zone': self.zone,
            'pg': self.pg,
            'ep': self.ep,
            'pp': self.pp,
            'notifyTime': self.notify_time,
            'isNotified': self.is_notified
        }

class DailyNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, default='')
    __table_args__ = (db.UniqueConstraint('date', 'type', name='unique_date_type'),)

class TruckFds(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    truck_plate = db.Column(db.String(20), db.ForeignKey('truck.plate'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    is_out_of_service = db.Column(db.Boolean, default=True)
    __table_args__ = (db.UniqueConstraint('truck_plate', 'date', name='unique_plate_date'),)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 3. VISTAS ADMIN ---
class ProtectedAdminView(ModelView):
    form_extra_fields = {'password': PasswordField('Contraseña')}
    form_excluded_columns = ('password_hash',)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('index'))

    def on_model_change(self, form, model, is_created):
        if 'password' in form and form.password.data:
            model.password_hash = generate_password_hash(form.password.data)
        super(ProtectedAdminView, self).on_model_change(form, model, is_created)

class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('index'))

admin = Admin(app, name='Gestor Tráfico', index_view=MyAdminIndexView(name='Dashboard', url='/admin'))
admin.add_view(ProtectedAdminView(User, db.session, name='Usuarios'))
admin.add_view(ProtectedAdminView(Truck, db.session, name='Camiones'))
admin.add_view(ProtectedAdminView(Trip, db.session, name='Viajes'))
admin.add_view(ProtectedAdminView(DailyNote, db.session, name='Notas'))

# --- 4. INIT & RUTAS BASIVAS ---
def create_db_and_admin():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='davidp').first():
            u = User(username='davidp', is_admin=True)
            u.set_password('admin')
            db.session.add(u)
            db.session.commit()
            print("Admin 'davidp' creado.")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        u = User.query.filter_by(username=request.form.get('username')).first()
        if u and u.check_password(request.form.get('password')):
            login_user(u)
            flash('Login exitoso', 'success')
            next_p = request.args.get('next')
            if next_p and not current_user.is_admin and '/admin' in next_p: return redirect(url_for('index'))
            if current_user.is_admin and not next_p: return redirect(url_for('admin.index'))
            return redirect(next_p or url_for('index'))
        else: flash('Datos incorrectos', 'danger')
    return render_template('login.html', title='Login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', title='Gestor de Tráfico')

# --- 5. API ENDPOINTS ---
@app.route('/api/initial-data')
@login_required
def get_initial_data():
    trucks = [t.to_dict() for t in Truck.query.all()]
    trips = [t.to_dict() for t in Trip.query.all()]
    fds = {}
    for r in TruckFds.query.filter_by(is_out_of_service=True).all():
        if r.truck_plate not in fds: fds[r.truck_plate] = {}
        fds[r.truck_plate][r.date] = True
    return jsonify({'trucks': trucks, 'trips': trips, 'fds_data': fds})

@app.route('/api/trucks', methods=['POST'])
@login_required
def save_truck():
    d = request.json
    t = Truck.query.filter_by(plate=d.get('plate')).first()
    if not t:
        t = Truck(plate=d.get('plate'))
        db.session.add(t)
    t.location = d.get('location', '')
    t.location_last_updated = d.get('locationLastUpdatedDate', '2000-01-01')
    t.creation_date = d.get('creationDate', '2000-01-01')
    t.deletion_date = d.get('deletionDate')
    t.is_location_manual = d.get('isLocationManual', False)
    t.zones_str = ','.join(d.get('zones', []))
    db.session.commit()
    return jsonify(t.to_dict())

@app.route('/api/trucks/<string:plate>', methods=['DELETE'])
@login_required
def delete_truck(plate):
    # This endpoint might remain unused if we only use soft-delete via save_truck, 
    # but good to have for cleanup if needed.
    t = Truck.query.filter_by(plate=plate).first()
    if t:
        db.session.delete(t)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/trips', methods=['POST'])
@login_required
def save_trip():
    d = request.json
    tid = d.get('id')
    t = Trip.query.get(tid) if tid else None
    if not t:
        t = Trip()
        db.session.add(t)
    
    t.type = d.get('type')
    t.client = d.get('client')
    t.driver = d.get('driver')
    t.origin = d.get('origin')
    t.destination = d.get('destination')
    t.load_date = d.get('loadDate')
    t.unload_date = d.get('unloadDate')
    # Handle nullable foreign key for truck
    t.assigned_truck_plate = d.get('assignedTruck') or None 
    t.assigned_slot = d.get('assignedSlot')
    t.is_urgent = d.get('isUrgent', False)
    t.is_groupage = d.get('isGroupage', False)
    t.zone = d.get('zone')
    t.pg, t.ep, t.pp = d.get('pg', 0), d.get('ep', 0), d.get('pp', 0)
    t.notify_time = d.get('notifyTime', '')
    t.is_notified = d.get('isNotified', False)
    
    db.session.commit()
    return jsonify(t.to_dict())

@app.route('/api/trips/<int:tid>', methods=['DELETE'])
@login_required
def delete_trip(tid):
    t = Trip.query.get(tid)
    if t:
        db.session.delete(t)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/notes', methods=['GET', 'POST'])
@login_required
def notes():
    if request.method == 'GET':
        n = DailyNote.query.filter_by(date=request.args.get('date'), type=request.args.get('type')).first()
        return jsonify({'content': n.content if n else ''})
    d = request.json
    n = DailyNote.query.filter_by(date=d.get('date'), type=d.get('type')).first()
    if not n:
        n = DailyNote(date=d.get('date'), type=d.get('type'))
        db.session.add(n)
    n.content = d.get('content', '')
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/fds', methods=['POST'])
@login_required
def fds():
    d = request.json
    r = TruckFds.query.filter_by(truck_plate=d.get('plate'), date=d.get('date')).first()
    if d.get('is_out_of_service'):
        if not r: db.session.add(TruckFds(truck_plate=d.get('plate'), date=d.get('date'), is_out_of_service=True))
        else: r.is_out_of_service = True
    elif r: db.session.delete(r)
    db.session.commit()
    return jsonify({'success': True})

if __name__ == '__main__':
    create_db_and_admin()
    app.run(debug=True)
