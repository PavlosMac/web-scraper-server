import sys
print(sys.path)
from flask_migrate import MigrateCommand
from flask_script import Manager
from app import app, db
import os

app.config.from_object(os.environ['APP_SETTINGS'])
manager = Manager(app)

manager.add_command('db', MigrateCommand)

if __name__ == '__main__':
    manager.run()