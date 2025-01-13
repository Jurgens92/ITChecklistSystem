# run.py
from app import create_app, db
from app.models import User

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

            try:
                db.session.commit()
                print("Database initialized successfully!")
            except Exception as e:
                print(f"Error initializing database: {e}")
                db.session.rollback()
        else:
            print("Database already contains data - skipping initialization")

if __name__ == '__main__':
    init_db()  # Initialize database if empty
    app.run(debug=True)