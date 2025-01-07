from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    admin = User(username='admin', is_admin=True)
    admin.set_password('admin')
    db.session.add(admin)
    db.session.commit()