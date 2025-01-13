#!/bin/bash

# Exit on any error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print colored message
print_message() {
    echo -e "${GREEN}[*] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[!] $1${NC}"
}

print_error() {
    echo -e "${RED}[X] $1${NC}"
}

# Check if script is run as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root (sudo)"
   exit 1
fi

print_message "Starting IT Checklist System installation..."

# Update system packages
print_message "Updating system packages..."
apt update && apt upgrade -y

# Install required system packages
print_message "Installing required packages..."
apt install -y python3 python3-pip python3-venv nginx supervisor git python3-dev libfreetype6-dev

# Create application directory
print_message "Creating application directory..."
mkdir -p /var/www/itchecklist
cd /var/www/itchecklist

# Handle repository setup
print_message "Setting up repository..."
if [ -d ".git" ]; then
    # Save git config
    mv .git /tmp/itchecklist_git
    # Clean directory
    rm -rf *
    # Restore git config
    mv /tmp/itchecklist_git .git
    # Configure git safety
    git config --global --add safe.directory /var/www/itchecklist
    # Force clean checkout
    git fetch origin
    git reset --hard origin/main
else
    rm -rf *
    git clone https://github.com/Jurgens92/ITChecklistSystem.git .
fi

# Verify and create essential files if missing
if [ ! -f "config.py" ]; then
    print_message "Creating config.py..."
    cat > config.py << EOL
class Config:
    SECRET_KEY = 'dev'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///checklist.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
EOL
fi

# Check for requirements.txt
if [ ! -f "requirements.txt" ]; then
    print_message "Creating requirements.txt..."
    cat > requirements.txt << EOL
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Werkzeug==3.0.1
SQLAlchemy==2.0.23
python-dotenv==1.0.0
Bootstrap-Flask==2.3.3
reportlab==4.0.4
EOL
fi

# Create instance directory for SQLite database
print_message "Creating instance directory..."
mkdir -p /var/www/itchecklist/instance
chown -R www-data:www-data /var/www/itchecklist/instance
chmod 775 /var/www/itchecklist/instance

# Generate and set random secret key
print_message "Generating random secret key..."
RANDOM_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
sed -i "s/SECRET_KEY = 'dev'/SECRET_KEY = '$RANDOM_KEY'/" config.py

# Create virtual environment
print_message "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python packages
print_message "Installing Python requirements..."
pip install --upgrade pip
pip install --only-binary=:all: -r requirements.txt || pip install -r requirements.txt
pip install gunicorn

# Create Gunicorn configuration
print_message "Creating Gunicorn configuration..."
cat > gunicorn_config.py << EOL
bind = "unix:/var/www/itchecklist/itchecklist.sock"
workers = 3
user = "www-data"
group = "www-data"
EOL

# Create Supervisor configuration
print_message "Creating Supervisor configuration..."
cat > /etc/supervisor/conf.d/itchecklist.conf << EOL
[program:itchecklist]
directory=/var/www/itchecklist
command=/var/www/itchecklist/venv/bin/gunicorn -c gunicorn_config.py run:app
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/itchecklist/itchecklist.err.log
stdout_logfile=/var/log/itchecklist/itchecklist.out.log
startsecs=10
stopwaitsecs=60
environment=PATH="/var/www/itchecklist/venv/bin"
EOL

# Create log directory
print_message "Creating log directory..."
mkdir -p /var/log/itchecklist
chown www-data:www-data /var/log/itchecklist

# Create Nginx configuration
print_message "Creating Nginx configuration..."
cat > /etc/nginx/sites-available/itchecklist << EOL
server {
    listen 80;
    server_name _;  # Change this to your domain name if you have one

    location / {
        proxy_pass http://unix:/var/www/itchecklist/itchecklist.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOL

# Enable Nginx site
print_message "Enabling Nginx site..."
ln -sf /etc/nginx/sites-available/itchecklist /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default  # Remove default site
nginx -t

# Create update script with service checks
print_message "Creating update script..."
cat > /var/www/itchecklist/update.sh << EOL
#!/bin/bash

# Check if services are running
if ! systemctl is-active --quiet nginx; then
    systemctl start nginx
fi

if ! systemctl is-active --quiet supervisor; then
    systemctl start supervisor
fi

cd /var/www/itchecklist
git pull origin main
source venv/bin/activate
pip install -r requirements.txt

# Set proper permissions
chown -R www-data:www-data /var/www/itchecklist/instance
chmod 775 /var/www/itchecklist/instance
[ -f /var/www/itchecklist/instance/checklist.db ] && chmod 664 /var/www/itchecklist/instance/checklist.db

# Restart application
sudo supervisorctl restart itchecklist

# Ensure nginx is configured correctly and restart
sudo nginx -t && sudo systemctl restart nginx

# Verify services are running
if ! supervisorctl status itchecklist | grep -q RUNNING; then
    echo "Warning: Application failed to start. Checking logs..."
    tail -n 50 /var/log/itchecklist/itchecklist.err.log
fi
EOL

# Make update script executable
chmod +x /var/www/itchecklist/update.sh

# Set correct permissions
print_message "Setting permissions..."
chown -R www-data:www-data /var/www/itchecklist
chmod 775 /var/www/itchecklist
[ -f /var/www/itchecklist/instance/checklist.db ] && chmod 664 /var/www/itchecklist/instance/checklist.db

# Add current user to www-data group
print_message "Adding current user to www-data group..."
usermod -a -G www-data $SUDO_USER

# Initialize database
print_message "Initializing database..."
cd /var/www/itchecklist
sudo -u www-data bash -c "source /var/www/itchecklist/venv/bin/activate && python3 resetdb.py"

# Enable services to start on boot
print_message "Enabling services to start on boot..."
systemctl enable nginx
systemctl enable supervisor

# Ensure supervisor is running and will start on boot
systemctl start supervisor
supervisorctl reread
supervisorctl update

# Start services
print_message "Starting services..."
systemctl restart nginx
supervisorctl reread
supervisorctl update
supervisorctl start itchecklist

# Verify services are running correctly
print_message "Verifying services..."
if ! systemctl is-active --quiet nginx; then
    print_error "Nginx is not running!"
    exit 1
fi

if ! systemctl is-active --quiet supervisor; then
    print_error "Supervisor is not running!"
    exit 1
fi

# Modified check for application status
print_message "Checking application status..."
SUPERVISOR_STATUS=$(supervisorctl status itchecklist)
if echo "$SUPERVISOR_STATUS" | grep -q "RUNNING"; then
    print_message "Application is running properly!"
else
    print_error "Application failed to start! Checking logs..."
    tail -n 50 /var/log/itchecklist/itchecklist.err.log
    exit 1
fi

# Fix permissions one final time
print_message "Final permission check..."
chown -R www-data:www-data /var/www/itchecklist/instance
chmod 775 /var/www/itchecklist/instance
[ -f /var/www/itchecklist/instance/checklist.db ] && chmod 664 /var/www/itchecklist/instance/checklist.db

print_message "Installation complete!"
print_message "You can now access the application at: http://your-server-ip"
print_warning "Default login credentials:"
print_warning "Username: admin"
print_warning "Password: admin"
print_warning "Please change these credentials after first login!"
print_warning "A random SECRET_KEY has been generated for security"

# Print update instructions
echo ""
print_message "To update the application in the future, run:"
echo "sudo /var/www/itchecklist/update.sh"

# Notify about group changes
print_warning "NOTE: You may need to log out and back in for group changes to take effect"

exit 0