# resetdb.py
from app import create_app, db
from app.models import User, Client, ChecklistTemplate, ChecklistCategory, TemplateItem, Settings
import pytz
from datetime import datetime

app = create_app()

def create_default_data():
    try:
        # Add default settings
        default_settings = Settings(timezone='Africa/Johannesburg')  # Set default to SA timezone
        db.session.add(default_settings)
        db.session.flush()  # Ensure settings are saved before continuing

        # Create admin user
        admin = User(username='admin', is_admin=True)
        admin.set_password('admin')
        db.session.add(admin)
        
        # Create regular user
        user = User(username='user', is_admin=False)
        user.set_password('user')
        db.session.add(user)
        db.session.flush()

        # Create default template
        default_template = ChecklistTemplate(name='Default Template', is_default=True)
        db.session.add(default_template)
        db.session.flush()  # Get the template ID

        print(f"Created default template with ID: {default_template.id}")

        # Create categories
        server_category = ChecklistCategory(name='Server', template_id=default_template.id)
        desktop_category = ChecklistCategory(name='Desktop', template_id=default_template.id)
        db.session.add(server_category)
        db.session.add(desktop_category)
        db.session.flush()  # Get category IDs

        print(f"Created categories - Server ID: {server_category.id}, Desktop ID: {desktop_category.id}")

        # Define checklist items
        server_items = [
            'Server Access Reviewed',
            'Firewall Rules Reviewed',
            'Backups and Restores Tested and Confirmed Working',
            'Resource Usage Checked',
            'Unused Applications Removed',
            'Review Disk Fragmentation and Run Defrag on All Drives',
            'Monitor Available Disk Space',
            'Disk Integrity Checked',
            'Event Log and Statistics Monitored',
            'Antivirus Logs and Updates'
        ]
        
        desktop_items = [
            'Computer Updates (windows and Apps)',
            'Scans and Checks (event logs, antivirus)',
            'Backup Check (onedrive sync, local backups, local data on computer awareness)',
            'Cleanup Computer (temp files, unused programs, Remove Unused Printers)',
            'Check Printer on status (Restart 1 per week atleast)',
            'Check Hardware (disk SMART status, resource usage, disk fragmentation/trim, outdated hardware)',
            'Sitefile Updates',
            'Monthly Reporting'
        ]

        # Add items to template
        for item in server_items:
            template_item = TemplateItem(
                description=item,
                category_id=server_category.id,
                template_id=default_template.id
            )
            db.session.add(template_item)
        
        for item in desktop_items:
            template_item = TemplateItem(
                description=item,
                category_id=desktop_category.id,
                template_id=default_template.id
            )
            db.session.add(template_item)

        # Create default client
        client1 = Client(name='Client1', is_active=True)
        db.session.add(client1)

        # Final commit for all changes
        db.session.commit()
        print("Successfully created all default data!")

    except Exception as e:
        print(f"Error in create_default_data: {str(e)}")
        db.session.rollback()
        raise

def reset_db():
    with app.app_context():
        try:
            print("Dropping all tables...")
            db.drop_all()
            print("Creating all tables...")
            db.create_all()
            print("Creating default data...")
            create_default_data()
            print("Database reset complete!")
        except Exception as e:
            print(f"Error resetting database: {e}")
            db.session.rollback()
            raise  # Re-raise the exception to see the full traceback

if __name__ == '__main__':
    reset_db()