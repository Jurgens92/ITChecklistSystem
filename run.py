from app import create_app, db
from app.models import User, Client, ChecklistItem, ChecklistRecord, CompletedItem
from werkzeug.security import generate_password_hash

app = create_app()

def init_db():
    with app.app_context():
        db.create_all()
        
        # Check if we already have data
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
            
            # Create some test clients
            clients = [
                Client(name='Client 1'),
                Client(name='Client 2'),
                Client(name='Client 3')
            ]
            for client in clients:
                db.session.add(client)
            
            # Create server checklist items
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
            
            # Create desktop checklist items
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
            
            # Add server items to database
            for item in server_items:
                db.session.add(ChecklistItem(description=item, category='Server'))
            
            # Add desktop items to database
            for item in desktop_items:
                db.session.add(ChecklistItem(description=item, category='Desktop'))
            
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