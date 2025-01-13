# IT Checklist System (Beta)

A web-based IT checklist management system designed for IT companies to efficiently manage and track client maintenance tasks. Built with Flask and SQLite, this application provides a simple yet powerful way to standardize IT maintenance procedures across clients.

## Features

- **User Management**
  - Admin and standard user roles
  - Secure authentication system
  - Password management

- **Client Management**
  - Add and manage multiple clients
  - Active/Archive client status
  - Search functionality

- **Checklist Templates**
  - Create and customize checklist templates
  - Category-based organization
  - Default template system

- **Checklist Management**
  - Track completion of maintenance tasks
  - Historical record keeping
  - Category-based task organization

- **Reporting**
  - Generate client reports
  - Export reports to PDF
  - Activity tracking

## Prerequisites

- Python 3.8 or higher
- Ubuntu/Debian-based system
- Nginx
- Supervisor

## Installation

### Automated Installation (Recommended)

1. Clone the repository:
```bash
git clone https://github.com/Jurgens92/ITChecklistSystem.git

## Run the installation script

cd ITChecklistSystem
chmod +x install.sh
sudo ./install.sh

### Access the application at
http://your-server-ip

# Default Credentials

Username: admin
Password: admin

Important: Change these credentials after first login.
Configuration
All configuration settings can be found in config.py. Key settings include:

SECRET_KEY: Application security key
SQLALCHEMY_DATABASE_URI: Database connection string

# Updating

sudo /var/www/itchecklist/update.sh

# Contributing

Fork the repository
Create your feature branch (git checkout -b feature/AmazingFeature)
Commit your changes (git commit -m 'Add some AmazingFeature')
Push to the branch (git push origin feature/AmazingFeature)
Open a Pull Request

