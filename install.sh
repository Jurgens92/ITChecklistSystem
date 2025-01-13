#!/bin/bash

# install.sh

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
apt install -y python3 python3-pip python3-venv nginx supervisor git

# Create application directory
print_message "Creating application directory..."
mkdir -p /var/www/itchecklist
cd /var/www/itchecklist

# Clone repository
print_message "Cloning repository..."
if [ -d "/var/www/itchecklist/.git" ]; then
    print_warning "Git repository already exists. Pulling latest changes..."
    git pull origin main
else
    git clone https://github.com/Jurgens92/ITChecklistSystem.git .
fi

# Create virtual environment
print_message "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python packages
print_message "Installing Python requirements..."
pip install --upgrade pip
pip install -r requirements.txt
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

# Create update script
print_message "Creating update script..."
cat > /var/www/itchecklist/update.sh << EOL
#!/bin/bash
cd /var/www/itchecklist
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo supervisorctl restart itchecklist
sudo systemctl restart nginx
EOL

# Make update script executable
chmod +x /var/www/itchecklist/update.sh

# Set correct permissions
print_message "Setting permissions..."
chown -R www-data:www-data /var/www/itchecklist

# Initialize database
print_message "Initializing database..."
cd /var/www/itchecklist
source venv/bin/activate
python3 resetdb.py

# Start services
print_message "Starting services..."
systemctl restart nginx
supervisorctl reread
supervisorctl update
supervisorctl start itchecklist

print_message "Installation complete!"
print_message "You can now access the application at: http://your-server-ip"
print_warning "Default login credentials:"
print_warning "Username: admin"
print_warning "Password: admin"
print_warning "Please change these credentials after first login!"

# Print update instructions
echo ""
print_message "To update the application in the future, run:"
echo "sudo /var/www/itchecklist/update.sh"

exit 0
