from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
import re

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'main.login'

def nl2br(value):
    """Convert newlines to <br> tags."""
    if not value:
        return ""
    return value.replace('\n', '<br>')

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)



    db.init_app(app)
    login_manager.init_app(app)

    # Add the nl2br filter to Jinja
    app.jinja_env.filters['nl2br'] = nl2br

    from app.models import User
    
    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    from app.routes import main
    app.register_blueprint(main)

    return app