
class Config:
    SECRET_KEY = 'dev'  # Change this to a random string in production
    SQLALCHEMY_DATABASE_URI = 'sqlite:///checklist.sqlite'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
