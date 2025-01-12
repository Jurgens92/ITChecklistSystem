from app import create_app, db
from app.models import User, Client, ChecklistTemplate, TemplateItem

app = create_app()

def init_db():
    with app.app_context():
        db.create_all()
        
        if User.query.first() is None:
            print("Initializing database with sample data...")
            
            # Create admin user
            admin = User(username='admin', is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
            
            # Create regular user
            user = User(username='user', is_admin=False)
            user.set_password('user')
            db.session.add(user)

            # Create default template
            default_template = ChecklistTemplate(name='Default Template', is_default=True)
            db.session.add(default_template)
            db.session.commit()  # Commit to get template ID

            # Create default categories
            server_category = ChecklistCategory(name='Server', template_id=default_template.id)
            desktop_category = ChecklistCategory(name='Desktop', template_id=default_template.id)
            db.session.add(server_category)
            db.session.add(desktop_category)
            db.session.commit()

            # Server checklist items
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
            
            # Desktop checklist items
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

            # Add server items to template
            for item in server_items:
                template_item = TemplateItem(
                    description=item,
                    category_id=server_category.id,
                    template_id=default_template.id
                )
                db.session.add(template_item)
            
            # Add desktop items to template
            for item in desktop_items:
                template_item = TemplateItem(
                    description=item,
                    category_id=desktop_category.id,
                    template_id=default_template.id
                )
                db.session.add(template_item)

            try:
                db.session.commit()
                print("Database initialized successfully!")
            except Exception as e:
                print(f"Error initializing database: {e}")
                db.session.rollback()
        else:
            print("Database already contains data - skipping initialization")

def reset_db():
    with app.app_context():
        try:
            print("Dropping all tables...")
            db.drop_all()
            print("Creating all tables...")
            db.create_all()
            print("Initializing fresh data...")
            init_db()
            print("Database reset complete!")
        except Exception as e:
            print(f"Error resetting database: {e}")

if __name__ == '__main__':
    init_db()  # Initialize database if empty
    app.run(debug=True)
