from app import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import event, UniqueConstraint

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'))
    checklist_records = db.relationship('ChecklistRecord', backref='user')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_power_user(self):
        return self.role is not None and self.role.name == 'Power User'

    def has_permission(self, permission):
        if self.is_admin:
            return True
        if self.role and self.role.permissions:
            return permission in self.role.permissions
        return False

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, default=True)
    checklist_records = db.relationship('ChecklistRecord', backref='client', cascade='all, delete-orphan')
    checklists = db.relationship('ClientChecklist', backref='client', cascade='all, delete-orphan')
    checklist_items = db.relationship('ChecklistItem', backref='client', cascade='all, delete-orphan')
    users = db.relationship('ClientUser', backref='client', cascade='all, delete-orphan')

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
    items = db.relationship('ChecklistItem', backref='record', lazy='dynamic')
    notes = db.relationship('ChecklistNotes', backref='record', lazy='dynamic')
    user_checklists = db.relationship('UserChecklist', backref='record', lazy='dynamic')



    @property
    def completed_count(self):
        return CompletedItem.query.filter_by(
            record_id=self.id,
            completed=True
        ).count()

class ChecklistNotes(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    checklist_record_id = db.Column(db.Integer, db.ForeignKey('checklist_record.id'))
    note_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='notes')

class CompletedItem(db.Model):
    __tablename__ = 'completed_items'
    __table_args__ = (
        UniqueConstraint('record_id', 'checklist_item_id', name='uix_record_item'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('checklist_record.id', ondelete='CASCADE'))
    checklist_item_id = db.Column(db.Integer, db.ForeignKey('checklist_item.id', ondelete='CASCADE'))
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class ChecklistTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    items = db.relationship('TemplateItem', backref='template', cascade='all, delete-orphan')

class ChecklistCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('checklist_template.id'))
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    is_per_user = db.Column(db.Boolean, default=False)  # Add this line
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

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timezone = db.Column(db.String(50), default='UTC')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def get_timezone():
        settings = Settings.query.first()
        return settings.timezone if settings else 'UTC'

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    is_custom = db.Column(db.Boolean, default=True)
    permissions = db.Column(db.JSON)
    users = db.relationship('User', backref='role', lazy=True)
    
    # Store permissions as a JSON string
    permissions = db.Column(db.JSON)

class ClientUser(db.Model):
    __tablename__ = 'client_user'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id', ondelete='CASCADE'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('client_id', 'name', name='uix_client_user_name'),
    )

class UserChecklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('checklist_record.id', ondelete='CASCADE'))
    category_id = db.Column(db.Integer, db.ForeignKey('checklist_category.id', ondelete='CASCADE'))
    client_user_id = db.Column(db.Integer, db.ForeignKey('client_user.id', ondelete='CASCADE'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    client_user = db.relationship('ClientUser', backref='user_checklists')

