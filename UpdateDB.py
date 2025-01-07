from app import create_app, db
from app.models import Client

app = create_app()

def update_database():
    with app.app_context():
        # First, delete the existing database
        db.drop_all()
        
        # Create all tables with the new schema
        db.create_all()
        
        print("Database schema updated successfully!")

if __name__ == "__main__":
    update_database()