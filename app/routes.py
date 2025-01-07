from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, Client, ChecklistItem, ChecklistRecord, CompletedItem
from app import db
from sqlalchemy import func
from datetime import datetime, timedelta

main = Blueprint('main', __name__)

@main.route('/')
@login_required
def dashboard():
    # Only get active clients
    clients = Client.query.filter_by(is_active=True).all()
    return render_template('dashboard.html', clients=clients)

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            return redirect(url_for('main.dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@main.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@main.route('/client/<int:client_id>', methods=['GET'])
@login_required
def client_checklist(client_id):
    client = Client.query.get_or_404(client_id)
    server_items = ChecklistItem.query.filter_by(category='Server').all()
    desktop_items = ChecklistItem.query.filter_by(category='Desktop').all()
    return render_template('checklist.html', 
                         client=client, 
                         server_items=server_items,
                         desktop_items=desktop_items)

@main.route('/submit_checklist', methods=['POST'])
@login_required
def submit_checklist():
    client_id = request.form.get('client_id')
    
    record = ChecklistRecord(
        client_id=client_id,
        user_id=current_user.id
    )
    db.session.add(record)
    db.session.commit()
    
    completed_items = request.form.getlist('items')
    for item_id in completed_items:
        completed_item = CompletedItem(
            record_id=record.id,
            checklist_item_id=int(item_id),
            completed=True
        )
        db.session.add(completed_item)
    
    db.session.commit()
    flash('Checklist submitted successfully')
    return redirect(url_for('main.dashboard'))
    
@main.route('/reports')
@login_required
def reports():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('main.dashboard'))
    
    # Get all clients and users for the dropdowns
    clients = Client.query.all()
    users = User.query.all()
    
    return render_template('reports.html', clients=clients, users=users)

@main.route('/reports/client/<int:client_id>')
@login_required
def client_report(client_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('main.dashboard'))
        
    client = Client.query.get_or_404(client_id)
    records = ChecklistRecord.query.filter_by(client_id=client_id).order_by(ChecklistRecord.date_performed.desc()).all()
    
    return render_template('client_report.html', client=client, records=records)

@main.route('/reports/user/<int:user_id>')
@login_required
def user_report(user_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('main.dashboard'))
        
    user = User.query.get_or_404(user_id)
    records = ChecklistRecord.query.filter_by(user_id=user_id).order_by(ChecklistRecord.date_performed.desc()).all()
    
    return render_template('user_report.html', user=user, records=records)

@main.route('/reports/summary')
@login_required
def summary_report():
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('main.dashboard'))
    
    # Get last 30 days of activity
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Summary statistics
    total_checks = ChecklistRecord.query.count()
    recent_checks = ChecklistRecord.query.filter(ChecklistRecord.date_performed >= thirty_days_ago).count()
    total_clients = Client.query.count()
    total_users = User.query.count()
    
    # Most active clients
    active_clients = db.session.query(
        Client,
        func.count(ChecklistRecord.id).label('check_count')
    ).join(ChecklistRecord).group_by(Client).order_by(func.count(ChecklistRecord.id).desc()).limit(5).all()
    
    # Most active users
    active_users = db.session.query(
        User,
        func.count(ChecklistRecord.id).label('check_count')
    ).join(ChecklistRecord).group_by(User).order_by(func.count(ChecklistRecord.id).desc()).limit(5).all()
    
    return render_template('summary_report.html',
                         total_checks=total_checks,
                         recent_checks=recent_checks,
                         total_clients=total_clients,
                         total_users=total_users,
                         active_clients=active_clients,
                         active_users=active_users)

@main.route('/manage-clients')
@login_required
def manage_clients():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('main.dashboard'))
    
    clients = Client.query.all()
    return render_template('manage_clients.html', clients=clients)

@main.route('/add-client', methods=['POST'])
@login_required
def add_client():
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('main.dashboard'))
    
    client_name = request.form.get('client_name')
    if client_name:
        if Client.query.filter_by(name=client_name).first():
            flash('A client with this name already exists.')
        else:
            new_client = Client(name=client_name, is_active=True)
            db.session.add(new_client)
            db.session.commit()
            flash('Client added successfully.')
    return redirect(url_for('main.manage_clients'))

@main.route('/toggle-client/<int:client_id>')
@login_required
def toggle_client(client_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('main.dashboard'))
    
    client = Client.query.get_or_404(client_id)
    client.is_active = not client.is_active
    db.session.commit()
    status = "activated" if client.is_active else "archived"
    flash(f'Client {client.name} has been {status}.')
    return redirect(url_for('main.manage_clients'))

@main.route('/manage-users')
@login_required
def manage_users():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('main.dashboard'))
    
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@main.route('/add-user', methods=['POST'])
@login_required
def add_user():
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('main.dashboard'))
    
    username = request.form.get('username')
    password = request.form.get('password')
    is_admin = request.form.get('is_admin') == 'true'
    
    if username and password:
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
        else:
            new_user = User(username=username, is_admin=is_admin)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('User added successfully.')
    return redirect(url_for('main.manage_users'))

@main.route('/delete-user/<int:user_id>')
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('main.dashboard'))
    
    if current_user.id == user_id:
        flash('Cannot delete your own account.')
        return redirect(url_for('main.manage_users'))
    
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} has been deleted.')
    return redirect(url_for('main.manage_users'))