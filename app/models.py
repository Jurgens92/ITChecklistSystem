from app import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    checklist_records = db.relationship('ChecklistRecord', backref='user')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    checklist_records = db.relationship('ChecklistRecord', backref='client')
    checklists = db.relationship('ClientChecklist', backref='client', cascade='all, delete-orphan')

class ChecklistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    description = db.Column(db.String(200), nullable=False)
    record_id = db.Column(db.Integer, db.ForeignKey('checklist_record.id'))
    category = db.Column(db.String(50))
    completed = db.Column(db.Boolean, default=False)

class ChecklistRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date_performed = db.Column(db.DateTime, default=datetime.utcnow)
    items_completed = db.relationship('ChecklistItem', backref='record')

class ChecklistTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    items = db.relationship('TemplateItem', backref='template', cascade='all, delete-orphan')

class TemplateItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))
    template_id = db.Column(db.Integer, db.ForeignKey('checklist_template.id'))
    
class ClientChecklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    description = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))

