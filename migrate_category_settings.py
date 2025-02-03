from app import create_app, db
from app.models import ClientCategorySettings

def migrate_category_settings():
    app = create_app()
    with app.app_context():
        # Create new table
        db.create_all()

if __name__ == '__main__':
    migrate_category_settings()