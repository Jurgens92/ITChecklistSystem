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
    category_id = db.Column(db.Integer, db.ForeignKey('checklist_category.id'))
    completed = db.Column(db.Boolean, default=False)

class ChecklistRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date_performed = db.Column(db.DateTime, default=datetime.utcnow)
    items_completed = db.relationship('CompletedItem', backref='record')
    notes = db.relationship('ChecklistNotes', backref='record', lazy='dynamic')

    @property
    def completed_count(self):
        return CompletedItem.query.filter_by(record_id=self.id, completed=True).count()

class ChecklistNotes(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    checklist_record_id = db.Column(db.Integer, db.ForeignKey('checklist_record.id'))
    note_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='notes')

class CompletedItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('checklist_record.id'))
    checklist_item_id = db.Column(db.Integer, db.ForeignKey('checklist_item.id'))
    completed = db.Column(db.Boolean, default=False)

class ChecklistTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    items = db.relationship('TemplateItem', backref='template', cascade='all, delete-orphan')

class ChecklistCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('checklist_template.id'))
    items = db.relationship('TemplateItem', backref='category', cascade='all, delete-orphan')
    
class TemplateItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('checklist_category.id'))
    template_id = db.Column(db.Integer, db.ForeignKey('checklist_template.id'))
    
class ClientChecklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    description = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))

