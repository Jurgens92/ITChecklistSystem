# migrate_db.py
from app import create_app, db
from app.models import (
    User, Client, ChecklistTemplate, ChecklistCategory, 
    TemplateItem, Settings, Role, ChecklistItem,
    ChecklistRecord, ChecklistNotes, CompletedItem
)
import sqlite3
import shutil
from datetime import datetime
import pytz

app = create_app()

def backup_database():
    """Create a backup of the existing database"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    try:
        shutil.copy2('instance/checklist.db', f'instance/checklist_backup_{timestamp}.db')
        print(f"Database backed up to checklist_backup_{timestamp}.db")
        return True
    except Exception as e:
        print(f"Backup failed: {str(e)}")
        return False

def migrate_database():
    with app.app_context():
        try:
            print("Starting database migration...")
            
            # Backup first
            if not backup_database():
                print("Migration aborted due to backup failure")
                return
            
            # Connect to existing database
            old_conn = sqlite3.connect('instance/checklist.db')
            old_cur = old_conn.cursor()
            
            # Store existing data
            print("Storing existing data...")
            
            # Get existing users
            old_cur.execute("SELECT id, username, password_hash, is_admin FROM user")
            existing_users = old_cur.fetchall()
            
            # Get existing clients
            old_cur.execute("SELECT id, name, is_active FROM client")
            existing_clients = old_cur.fetchall()
            
            # Get existing templates
            old_cur.execute("SELECT id, name, is_default FROM checklist_template")
            existing_templates = old_cur.fetchall()
            
            # Get existing categories
            old_cur.execute("SELECT id, name, template_id FROM checklist_category")
            existing_categories = old_cur.fetchall()
            
            # Get existing template items
            old_cur.execute("SELECT id, description, category_id, template_id FROM template_item")
            existing_template_items = old_cur.fetchall()
            
            # Get existing checklist items if they exist
            try:
                old_cur.execute("SELECT id, client_id, description, category_id FROM checklist_item")
                existing_checklist_items = old_cur.fetchall()
            except sqlite3.OperationalError:
                existing_checklist_items = []
            
            # Get existing settings
            old_cur.execute("SELECT id, timezone FROM settings")
            existing_settings = old_cur.fetchall()
            
            # Close old connection
            old_conn.close()
            
            print("Creating new tables...")
            # Create new tables without dropping existing ones
            db.create_all()
            
            # Create Power User role
            print("Creating Power User role...")
            power_user_role = Role(
                name='Power User',
                is_custom=False,
                permissions=[
                    'manage_clients',
                    'view_reports',
                    'edit_checklist_structure',
                    'add_template',
                    'add_client',
                    'delete_category',
                    'add_category',
                    'add_client_template'
                ]
            )
            db.session.add(power_user_role)
            db.session.flush()
            
            print("Migrating existing data...")
            
            # Migrate users
            for user_id, username, password_hash, is_admin in existing_users:
                user = User.query.get(user_id)
                if not user:
                    user = User(
                        id=user_id,
                        username=username,
                        password_hash=password_hash,
                        is_admin=is_admin
                    )
                    db.session.add(user)
            
            # Migrate clients
            for client_id, name, is_active in existing_clients:
                client = Client.query.get(client_id)
                if not client:
                    client = Client(
                        id=client_id,
                        name=name,
                        is_active=is_active
                    )
                    db.session.add(client)
            
            # Migrate templates
            for template_id, name, is_default in existing_templates:
                template = ChecklistTemplate.query.get(template_id)
                if not template:
                    template = ChecklistTemplate(
                        id=template_id,
                        name=name,
                        is_default=is_default
                    )
                    db.session.add(template)
            
            # Migrate categories
            for category_id, name, template_id in existing_categories:
                category = ChecklistCategory.query.get(category_id)
                if not category:
                    category = ChecklistCategory(
                        id=category_id,
                        name=name,
                        template_id=template_id
                    )
                    db.session.add(category)
            
            # Migrate template items
            for item_id, description, category_id, template_id in existing_template_items:
                item = TemplateItem.query.get(item_id)
                if not item:
                    item = TemplateItem(
                        id=item_id,
                        description=description,
                        category_id=category_id,
                        template_id=template_id
                    )
                    db.session.add(item)
            
            # Migrate checklist items
            for item_id, client_id, description, category_id in existing_checklist_items:
                item = ChecklistItem.query.get(item_id)
                if not item:
                    item = ChecklistItem(
                        id=item_id,
                        client_id=client_id,
                        description=description,
                        category_id=category_id
                    )
                    db.session.add(item)
            
            # Migrate settings
            for setting_id, timezone in existing_settings:
                setting = Settings.query.get(setting_id)
                if not setting:
                    setting = Settings(
                        id=setting_id,
                        timezone=timezone
                    )
                    db.session.add(setting)
            
            print("Committing changes...")
            db.session.commit()
            print("Migration completed successfully!")
            
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate_database()