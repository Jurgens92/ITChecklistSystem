from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'main.login'  # Changed from 'auth.login' to 'main.login'

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User
    
    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    from app.routes import main
    app.register_blueprint(main)

    return app