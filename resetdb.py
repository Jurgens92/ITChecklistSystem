from app import create_app
app = create_app()
from run import reset_db
reset_db()