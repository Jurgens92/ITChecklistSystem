# migrate_add_users.py
from app import create_app, db
from app.models import Client, ChecklistCategory, ClientUser, UserChecklist

def migrate_add_users():
    app = create_app()
    with app.app_context():
        # Create new tables
        db.create_all()
        
        # Add is_per_user column to checklist_category if it doesn't exist
        try:
            db.session.execute('ALTER TABLE checklist_category ADD COLUMN is_per_user BOOLEAN DEFAULT FALSE')
            db.session.commit()
            print("Added is_per_user column to checklist_category")
        except Exception as e:
            print(f"Column may already exist or other error: {e}")
            db.session.rollback()

if __name__ == '__main__':
    migrate_add_users()