from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from collections import defaultdict
from app.models import (
    User,
    Client,
    ChecklistItem,
    ChecklistRecord,
    ChecklistTemplate,
    CompletedItem,
    TemplateItem,
    ChecklistCategory,
    ChecklistNotes,
    Settings,
)
import pytz
from app import db
from sqlalchemy import func, text
from datetime import datetime, timedelta

from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT, TA_CENTER


def get_local_time():
    settings = Settings.query.first()
    tz = pytz.timezone(settings.timezone if settings else 'UTC')
    return datetime.now(tz)

def convert_to_local_time(utc_dt):
    if not utc_dt:
        return None
    
    settings = Settings.query.first()
    local_tz = pytz.timezone(settings.timezone if settings else 'UTC')
    
    # If the datetime is naive (has no timezone info), assume it's UTC
    if utc_dt.tzinfo is None:
        utc_dt = pytz.UTC.localize(utc_dt)
    
    return utc_dt.astimezone(local_tz)



main = Blueprint("main", __name__)

@main.route("/")
@login_required
def dashboard():
    # Only get active clients
    clients = Client.query.filter_by(is_active=True).all()
    return render_template("dashboard.html", clients=clients)

@main.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        new_timezone = request.form.get("timezone")
        try:
            # Validate timezone
            pytz.timezone(new_timezone)
            
            settings = Settings.query.first()
            if not settings:
                settings = Settings(timezone=new_timezone)
                db.session.add(settings)
            else:
                settings.timezone = new_timezone
                settings.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash("Timezone settings updated successfully")
        except Exception as e:
            flash(f"Invalid timezone: {str(e)}")
        
        return redirect(url_for("main.settings"))

    settings = Settings.query.first()
    timezones = pytz.all_timezones
    return render_template(
        "settings.html",
        current_timezone=settings.timezone if settings else 'UTC',
        available_timezones=timezones
    )

@main.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username")).first()
        if user and user.check_password(request.form.get("password")):
            login_user(user)
            return redirect(url_for("main.dashboard"))
        flash("Invalid username or password")
    return render_template("login.html")

@main.route("/toggle-admin/<int:user_id>", methods=["POST"])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    if current_user.id == user_id:
        flash("Cannot change your own admin status")
        return redirect(url_for("main.manage_users"))

    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    
    new_role = "admin" if user.is_admin else "standard user"
    flash(f"Changed {user.username}'s role to {new_role}")
    return redirect(url_for("main.manage_users"))

@main.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.login"))


@main.route("/client/<int:client_id>", methods=["GET"])
@login_required
def client_checklist(client_id):
    client = Client.query.get_or_404(client_id)
    
    # Get all available templates
    templates = ChecklistTemplate.query.all()
    print(f"DEBUG: Found {len(templates)} templates")  # Debug line
    
    # Get all items for this client
    items_by_category = {}
    categories = ChecklistCategory.query.all()
    
    for category in categories:
        items = ChecklistItem.query.filter_by(
            client_id=client_id,
            category_id=category.id
        ).all()
        
        if items:  # Only add categories that have items
            items_by_category[category] = items

    # Print debug information
    print(f"DEBUG: Client ID: {client_id}")
    print(f"DEBUG: Number of templates: {len(templates)}")
    for template in templates:
        print(f"DEBUG: Template: {template.name} (ID: {template.id})")
        
    return render_template(
        "checklist.html",
        client=client,
        items_by_category=items_by_category,
        templates=templates
    )

@main.route("/submit_checklist", methods=["POST"])
@login_required
def submit_checklist():
    try:
        # Start transaction
        db.session.begin_nested()
        
        client_id = request.form.get("client_id")
        if not client_id:
            raise ValueError("No client specified")

        completed_item_ids = request.form.getlist("items")
        notes_text = request.form.get("notes", "").strip()
        
        # Validate client exists
        client = Client.query.get_or_404(client_id)
        
        # Create record with proper error handling
        try:
            record = ChecklistRecord(
                client_id=client_id,
                user_id=current_user.id,
                date_performed=get_local_time()
            )
            db.session.add(record)
            db.session.flush()  # Get the record ID
            
            # Add notes if provided
            if notes_text:
                notes = ChecklistNotes(
                    checklist_record_id=record.id,
                    note_text=notes_text,
                    user_id=current_user.id
                )
                db.session.add(notes)
            
            # Get all items for this client
            client_items = ChecklistItem.query.filter_by(client_id=client_id).all()
            
            # Build summary data while creating CompletedItems
            summary_data = {}
            for item in client_items:
                completed = str(item.id) in completed_item_ids
                
                # Check for existing completed item
                existing_completed = CompletedItem.query.filter_by(
                    record_id=record.id,
                    checklist_item_id=item.id
                ).first()
                
                if not existing_completed:
                    completed_item = CompletedItem(
                        record_id=record.id,
                        checklist_item_id=item.id,
                        completed=completed,
                        completed_by=current_user.id if completed else None
                    )
                    db.session.add(completed_item)
                
                # Build summary data
                if completed:
                    category = ChecklistCategory.query.get(item.category_id)
                    if category:
                        category_name = category.name
                        if category_name not in summary_data:
                            summary_data[category_name] = []
                        summary_data[category_name].append(item.description)
            
            db.session.commit()
            
            # Clear client session data after successful submission
            session_key = f'client_{client_id}_checklist'
            if session_key in session:
                session.pop(session_key)
            
            return jsonify({
                'status': 'success',
                'summary': summary_data,
                'notes': notes_text,
                'record_id': record.id
            })
            
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"Integrity Error: {str(e)}")
            return jsonify({
                "status": "error",
                "message": "Database integrity error. Possible duplicate entry."
            }), 400
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error submitting checklist: {str(e)}")
            return jsonify({
                "status": "error",
                "message": "An error occurred while submitting the checklist."
            }), 500
            
    except Exception as e:
        current_app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "An unexpected error occurred."
        }), 500



@main.route("/checklist-summary")
@login_required
def checklist_summary():
    summary_data = session.pop('checklist_summary', None)
    if not summary_data:
        return redirect(url_for('main.dashboard'))
    return render_template('checklist_summary.html', summary=summary_data)

@main.route("/reports")
@login_required
def reports():
    if not current_user.is_admin:
        flash("Access denied. Admin privileges required.")
        return redirect(url_for("main.dashboard"))

    clients = Client.query.all()
    users = User.query.all()

    return render_template("reports.html", clients=clients, users=users)


@main.route("/reports/user/<int:user_id>")
@login_required
def user_report(user_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    user = User.query.get_or_404(user_id)
    
    # Get date range filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Base query
    query = ChecklistRecord.query.filter_by(user_id=user_id)
    
    # Apply date filters if provided
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(ChecklistRecord.date_performed >= start)
        except ValueError:
            flash("Invalid start date format")
    
    if end_date:
        try:
            # Add one day to include the end date fully
            end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(ChecklistRecord.date_performed < end)
        except ValueError:
            flash("Invalid end date format")
    
    # Get records with filters
    records = query.order_by(ChecklistRecord.date_performed.desc()).all()

    return render_template(
        "user_report.html",
        user=user,
        records=records,
        start_date=start_date,
        end_date=end_date,
        convert_to_local_time=convert_to_local_time
    )

@main.route("/reports/summary")
@login_required
def summary_report():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    # Get last 30 days of activity
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # Summary statistics
    total_checks = ChecklistRecord.query.count()
    recent_checks = ChecklistRecord.query.filter(
        ChecklistRecord.date_performed >= thirty_days_ago
    ).count()
    total_clients = Client.query.count()
    total_users = User.query.count()

    # Most active clients
    active_clients = (
        db.session.query(Client, func.count(ChecklistRecord.id).label("check_count"))
        .join(ChecklistRecord)
        .group_by(Client)
        .order_by(func.count(ChecklistRecord.id).desc())
        .limit(5)
        .all()
    )

    # Most active users
    active_users = (
        db.session.query(User, func.count(ChecklistRecord.id).label("check_count"))
        .join(ChecklistRecord)
        .group_by(User)
        .order_by(func.count(ChecklistRecord.id).desc())
        .limit(5)
        .all()
    )

    return render_template(
        "summary_report.html",
        total_checks=total_checks,
        recent_checks=recent_checks,
        total_clients=total_clients,
        total_users=total_users,
        active_clients=active_clients,
        active_users=active_users,
    )

@main.route("/client-report/<int:client_id>")
@login_required
def client_report(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    try:
        client = Client.query.get_or_404(client_id)
        
        # Get date range filters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Base query
        query = ChecklistRecord.query.filter_by(client_id=client_id)
        
        # Apply date filters if provided
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(ChecklistRecord.date_performed >= start)
            except ValueError:
                flash("Invalid start date format")
        
        if end_date:
            try:
                # Add one day to include the end date fully
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(ChecklistRecord.date_performed < end)
            except ValueError:
                flash("Invalid end date format")
        
        # Get records with filters and count completed items
        records = query.order_by(ChecklistRecord.date_performed.desc()).all()
        
        return render_template(
            "client_report.html",
            client=client,
            records=records,
            start_date=start_date,
            end_date=end_date,
            convert_to_local_time=convert_to_local_time
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating client report: {str(e)}")
        flash("Error generating report")
        return redirect(url_for("main.reports"))

@main.route("/export-user-report/<int:user_id>")
@login_required
def export_user_report(user_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    try:
        user = User.query.get_or_404(user_id)
        
        # Get date range filters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Base query
        query = ChecklistRecord.query.filter_by(user_id=user_id)
        
        # Apply date filters if provided
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(ChecklistRecord.date_performed >= start)
            except ValueError:
                flash("Invalid start date format")
                return redirect(url_for('main.user_report', user_id=user_id))
        
        if end_date:
            try:
                # Add one day to include the end date fully
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(ChecklistRecord.date_performed < end)
            except ValueError:
                flash("Invalid end date format")
                return redirect(url_for('main.user_report', user_id=user_id))
        
        records = query.order_by(ChecklistRecord.date_performed.desc()).all()

        # Create PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        elements = []
        styles = getSampleStyleSheet()
        
        # Add title with date range if specified
        title = f"User Report - {user.username}"
        if start_date and end_date:
            title += f" ({start_date} to {end_date})"
        elements.append(Paragraph(title, styles['Heading1']))
        elements.append(Spacer(1, 20))
        
        # Add report generation date
        report_date = datetime.now().strftime("%Y-%m-%d %H:%M")
        elements.append(Paragraph(f"Generated: {report_date}", styles['Normal']))
        elements.append(Spacer(1, 20))

        # Prepare table data
        table_data = [['Date', 'Client', 'Category', 'Item', 'Status']]
        
        for record in records:
            # Get completed items for this record
            completed_items = CompletedItem.query.filter_by(record_id=record.id).all()
            
            # Get notes for this record
            notes = ChecklistNotes.query.filter_by(checklist_record_id=record.id).first()
            
            # Add items
            for completed_item in completed_items:
                checklist_item = ChecklistItem.query.get(completed_item.checklist_item_id)
                if checklist_item:
                    category = ChecklistCategory.query.get(checklist_item.category_id)
                    category_name = category.name if category else "No Category"
                    
                    table_data.append([
                        record.date_performed.strftime('%Y-%m-%d %H:%M'),
                        record.client.name,
                        category_name,
                        Paragraph(checklist_item.description, styles['Normal']),
                        'Completed' if completed_item.completed else 'Not Completed'
                    ])
            
            # If there are notes, add them after the items
            if notes and notes.note_text:
                table_data.append(['', '', '', '', ''])  # Empty row for spacing
                note_header = f"Notes ({record.date_performed.strftime('%Y-%m-%d %H:%M')}):"
                table_data.append([Paragraph(note_header, styles['Heading4']), '', '', '', ''])
                table_data.append([Paragraph(notes.note_text, styles['Normal']), '', '', '', ''])
                table_data.append(['', '', '', '', ''])  # Empty row for spacing

        if len(table_data) > 1:
            # Calculate column widths
            page_width = letter[0] - 72
            col_widths = [
                page_width * 0.15,  # Date
                page_width * 0.15,  # Client
                page_width * 0.15,  # Category
                page_width * 0.40,  # Item
                page_width * 0.15   # Status
            ]

            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, 0), 1, colors.black),
                ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('SPAN', (0, -1), (-1, -1)),
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("No records found for this user", styles['Normal']))

        doc.build(elements)
        buffer.seek(0)
        
        # Generate filename with date range if specified
        filename = f"{user.username}_report"
        if start_date and end_date:
            filename += f"_{start_date}_to_{end_date}"
        filename += ".pdf"
        
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"Error generating PDF report: {str(e)}")
        flash("Error generating PDF report")
        return redirect(url_for('main.user_report', user_id=user_id))

@main.route("/export-client-report/<int:client_id>")
@login_required
def export_client_report(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    try:
        client = Client.query.get_or_404(client_id)
        
        # Get date range filters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Base query
        query = ChecklistRecord.query.filter_by(client_id=client_id)
        
        # Apply date filters if provided
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(ChecklistRecord.date_performed >= start)
            except ValueError:
                flash("Invalid start date format")
                return redirect(url_for('main.client_report', client_id=client_id))
        
        if end_date:
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(ChecklistRecord.date_performed < end)
            except ValueError:
                flash("Invalid end date format")
                return redirect(url_for('main.client_report', client_id=client_id))
        
        records = query.order_by(ChecklistRecord.date_performed.desc()).all()

        # Create PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        elements = []
        styles = getSampleStyleSheet()
        
        # Add title with date range if specified
        title = f"Checklist Report - {client.name}"
        if start_date and end_date:
            title += f" ({start_date} to {end_date})"
        elements.append(Paragraph(title, styles['Heading1']))
        elements.append(Spacer(1, 20))
        
        # Add report generation date
        report_date = datetime.now().strftime("%Y-%m-%d %H:%M")
        elements.append(Paragraph(f"Generated: {report_date}", styles['Normal']))
        elements.append(Spacer(1, 20))

        # Prepare table data
        table_data = [['Date', 'Performed By', 'Category', 'Item', 'Status']]
        
        for record in records:
            # Get completed items for this record
            completed_items = CompletedItem.query.filter_by(record_id=record.id).all()
            
            # Get notes for this record
            notes = ChecklistNotes.query.filter_by(checklist_record_id=record.id).first()
            
            # Add items
            for completed_item in completed_items:
                checklist_item = ChecklistItem.query.get(completed_item.checklist_item_id)
                if checklist_item:
                    category = ChecklistCategory.query.get(checklist_item.category_id)
                    category_name = category.name if category else "No Category"
                    
                    table_data.append([
                        record.date_performed.strftime('%Y-%m-%d %H:%M'),
                        record.user.username,
                        category_name,
                        Paragraph(checklist_item.description, styles['Normal']),
                        'Completed' if completed_item.completed else 'Not Completed'
                    ])
            
            # If there are notes, add them after the items
            if notes and notes.note_text:
                table_data.append(['', '', '', '', ''])  # Empty row for spacing
                note_header = f"Notes ({record.date_performed.strftime('%Y-%m-%d %H:%M')}):"
                table_data.append([Paragraph(note_header, styles['Heading4']), '', '', '', ''])
                table_data.append([Paragraph(notes.note_text, styles['Normal']), '', '', '', ''])
                table_data.append(['', '', '', '', ''])  # Empty row for spacing

        if len(table_data) > 1:
            # Calculate column widths
            page_width = letter[0] - 72
            col_widths = [
                page_width * 0.15,  # Date
                page_width * 0.15,  # Performed by
                page_width * 0.15,  # Category
                page_width * 0.40,  # Item
                page_width * 0.15   # Status
            ]

            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, 0), 1, colors.black),
                ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('SPAN', (0, -1), (-1, -1)),
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("No records found for this client", styles['Normal']))

        doc.build(elements)
        buffer.seek(0)
        
        # Generate filename with date range if specified
        filename = f"{client.name}_checklist_report"
        if start_date and end_date:
            filename += f"_{start_date}_to_{end_date}"
        filename += ".pdf"
        
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"Error generating PDF report: {str(e)}")
        flash("Error generating PDF report")
        return redirect(url_for('main.client_report', client_id=client_id))

@main.route("/manage-clients")
@login_required
def manage_clients():
    if not current_user.is_admin:
        flash("Access denied. Admin privileges required.")
        return redirect(url_for("main.dashboard"))

    clients = Client.query.all()
    templates = ChecklistTemplate.query.all()
    return render_template("manage_clients.html", clients=clients, templates=templates)


@main.route("/add-client", methods=["POST"])
@login_required
def add_client():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    client_name = request.form.get("client_name")
    template_id = request.form.get("template_id")
    
    if client_name:
        # Check if client already exists
        existing_client = Client.query.filter(func.lower(Client.name) == func.lower(client_name)).first()
        if existing_client:
            flash("A client with this name already exists.")
            return redirect(url_for("main.manage_clients"))
            
        try:
            # Create new client
            new_client = Client(name=client_name, is_active=True)
            db.session.add(new_client)
            db.session.flush()  # Get the client ID
            
            # Apply template
            if template_id:
                template = ChecklistTemplate.query.get(int(template_id))
            else:
                template = ChecklistTemplate.query.filter_by(is_default=True).first()
            
            if template:
                # Get all template items with categories
                template_items = db.session.query(
                    TemplateItem, ChecklistCategory
                ).join(
                    ChecklistCategory, 
                    TemplateItem.category_id == ChecklistCategory.id
                ).filter(
                    TemplateItem.template_id == template.id
                ).all()
                
                # Create checklist items
                for template_item, category in template_items:
                    item = ChecklistItem(
                        client_id=new_client.id,
                        description=template_item.description,
                        category_id=category.id,
                        completed=False
                    )
                    db.session.add(item)
                
            db.session.commit()
            flash(f"Client added successfully with template {template.name if template else 'None'}")
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating client: {str(e)}")
            
    return redirect(url_for("main.manage_clients"))

@main.route("/delete-template/<int:template_id>", methods=["POST"])
@login_required
def delete_template(template_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    template = ChecklistTemplate.query.get_or_404(template_id)

    try:
        # Delete associated template items first (should happen automatically with cascade)
        db.session.delete(template)
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@main.route('/add-category/<int:template_id>', methods=['POST'])
@login_required
def add_category(template_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    category = ChecklistCategory(
        name=data['name'],
        template_id=template_id
    )
    db.session.add(category)
    db.session.commit()
    return jsonify({'status': 'success'})

@main.route('/delete-category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    category = ChecklistCategory.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    return jsonify({'status': 'success'})

@main.route("/toggle-client/<int:client_id>")
@login_required
def toggle_client(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    client = Client.query.get_or_404(client_id)
    client.is_active = not client.is_active
    db.session.commit()
    status = "activated" if client.is_active else "archived"
    flash(f"Client {client.name} has been {status}.")
    return redirect(url_for("main.manage_clients"))

@main.route("/remove-client-category/<int:client_id>/<int:category_id>", methods=["POST"])
@login_required
def remove_client_category(client_id, category_id):
    if not current_user.is_admin:
        return jsonify({"status": "error", "message": "Access denied"}), 403

    try:
        # Delete all items in this category for this client
        ChecklistItem.query.filter_by(
            client_id=client_id,
            category_id=category_id
        ).delete()

        # If this is a custom category (associated with this client), delete it
        category = ChecklistCategory.query.filter_by(
            id=category_id,
            client_id=client_id
        ).first()
        
        if category:
            db.session.delete(category)

        db.session.commit()
        return jsonify({"status": "success"})

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@main.route("/manage-users")
@login_required
def manage_users():
    if not current_user.is_admin:
        flash("Access denied. Admin privileges required.")
        return redirect(url_for("main.dashboard"))

    users = User.query.all()
    return render_template("manage_users.html", users=users)


@main.route("/add-user", methods=["POST"])
@login_required
def add_user():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    username = request.form.get("username")
    password = request.form.get("password")
    is_admin = request.form.get("is_admin") == "true"

    if username and password:
        if User.query.filter_by(username=username).first():
            flash("Username already exists.")
        else:
            new_user = User(username=username, is_admin=is_admin)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash("User added successfully.")
    return redirect(url_for("main.manage_users"))


@main.route("/delete-user/<int:user_id>")
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    if current_user.id == user_id:
        flash("Cannot delete your own account.")
        return redirect(url_for("main.manage_users"))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f"User {user.username} has been deleted.")
    return redirect(url_for("main.manage_users"))


@main.route("/reset_password/<int:user_id>", methods=["POST"])
@login_required
def reset_password(user_id):
    if not current_user.is_admin:
        flash("Only administrators can reset passwords.")
        return redirect(url_for("main.manage_users"))

    user = User.query.get_or_404(user_id)
    new_password = request.form.get("new_password")

    if new_password:
        user.set_password(new_password)
        db.session.commit()
        flash(f"Password reset successfully for {user.username}")

    return redirect(url_for("main.manage_users"))


@main.route("/manage-templates")
@login_required
def manage_templates():
    if not current_user.is_admin:
        flash("Access denied. Admin privileges required.")
        return redirect(url_for("main.dashboard"))

    templates = ChecklistTemplate.query.all()
    return render_template("manage_templates.html", templates=templates)


@main.route("/add-template", methods=["POST"])
@login_required
def add_template():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    name = request.form.get("template_name")
    is_default = request.form.get("is_default") == "true"

    if name:
        template = ChecklistTemplate(name=name, is_default=is_default)
        db.session.add(template)
        db.session.commit()
        flash("Template added successfully")

    return redirect(url_for("main.manage_templates"))


@main.route("/edit-template/<int:template_id>", methods=["GET", "POST"])
@login_required
def edit_template(template_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    template = ChecklistTemplate.query.get_or_404(template_id)
    
    if request.method == "POST":
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "No data provided"}), 400

            # Delete existing template items
            TemplateItem.query.filter_by(template_id=template_id).delete()
            
            # Add new items
            if 'items' in data:
                for item_data in data['items']:
                    if 'description' in item_data and 'category_id' in item_data:
                        new_item = TemplateItem(
                            description=item_data['description'],
                            category_id=item_data['category_id'],
                            template_id=template_id
                        )
                        db.session.add(new_item)

            db.session.commit()
            return jsonify({"status": "success"})

        except Exception as e:
            db.session.rollback()
            print(f"Error saving template: {str(e)}")  # Debug logging
            return jsonify({"status": "error", "message": str(e)}), 500

    # GET request handling
    categories = ChecklistCategory.query.filter_by(template_id=template_id).all()
    items_by_category = {}
    
    for category in categories:
        items = TemplateItem.query.filter_by(
            template_id=template_id,
            category_id=category.id
        ).all()
        items_by_category[category] = items

    return render_template(
        "edit_template.html",
        template=template,
        categories=categories,
        items_by_category=items_by_category
    )

@main.route("/add-template-to-client/<int:client_id>", methods=["POST"])
@login_required
def add_template_to_client(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))
    
    template_id = request.form.get('template_id')
    print(f"DEBUG: Received template_id: {template_id}")
    
    if not template_id:
        flash("No template selected")
        return redirect(url_for("main.client_checklist", client_id=client_id))
        
    try:
        # Convert template_id to integer
        template_id = int(template_id)
        template = ChecklistTemplate.query.get(template_id)
        
        if not template:
            flash(f"Template with ID {template_id} not found")
            return redirect(url_for("main.client_checklist", client_id=client_id))
            
        # Get template items and categories
        categories = ChecklistCategory.query.filter_by(template_id=template.id).all()
        if not categories:
            flash(f"No categories found for template '{template.name}'")
            return redirect(url_for("main.client_checklist", client_id=client_id))
            
        items_added = 0
        duplicates_prevented = 0
        
        for category in categories:
            template_items = TemplateItem.query.filter_by(
                template_id=template.id,
                category_id=category.id
            ).all()
            
            for item in template_items:
                # Check for duplicate
                existing = ChecklistItem.query.filter_by(
                    client_id=client_id,
                    category_id=category.id,
                    description=item.description
                ).first()
                
                if not existing:
                    new_item = ChecklistItem(
                        client_id=client_id,
                        description=item.description,
                        category_id=category.id
                    )
                    db.session.add(new_item)
                    items_added += 1
                else:
                    duplicates_prevented += 1
        
        db.session.commit()
        flash(f"Added {items_added} items from template. Skipped {duplicates_prevented} duplicates.")
        
    except ValueError:
        flash("Invalid template ID")
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding template: {str(e)}")
        print(f"DEBUG: Error details: {str(e)}")
    
    return redirect(url_for("main.client_checklist", client_id=client_id))

@main.route("/delete-client/<int:client_id>", methods=["POST"])
@login_required
def delete_client(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    client = Client.query.get_or_404(client_id)

    try:
        # Delete the client - this should cascade to all related items
        db.session.delete(client)
        db.session.commit()
        flash(f"Client {client.name} has been deleted.")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting client: {str(e)}")
        print(f"DEBUG: Error details: {str(e)}")

    return redirect(url_for("main.manage_clients"))

@main.route("/edit-client-structure/<int:client_id>", methods=["GET", "POST"])
@login_required
def edit_client_structure(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))
        
    client = Client.query.get_or_404(client_id)
    
    if request.method == "POST":
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"status": "error", "message": "No data provided"}), 400
            
            # Check for duplicates across all categories
            all_items = []
            for category_data in data.get('categories', []):
                category_id = category_data.get('id')
                items = category_data.get('items', [])
                
                # Create a list of lowercase descriptions for case-insensitive comparison
                category_items = [item['description'].lower().strip() for item in items if 'description' in item]
                
                # Check for duplicates within the category
                duplicates = [item for item in category_items if category_items.count(item) > 1]
                if duplicates:
                    category = ChecklistCategory.query.get(category_id)
                    return jsonify({
                        "status": "error",
                        "message": f"Duplicate items found in category {category.name}: {', '.join(set(duplicates))}"
                    }), 400
                
                all_items.extend(category_items)
            
            # Delete existing items for this client
            ChecklistItem.query.filter_by(client_id=client_id).delete()
            
            # Add new/updated items
            for category_data in data.get('categories', []):
                category_id = category_data.get('id')
                items = category_data.get('items', [])
                
                print(f"Processing category {category_id} with {len(items)} items")  # Debug log
                
                if category_id and items:
                    for item in items:
                        if 'description' in item and item['description'].strip():
                            new_item = ChecklistItem(
                                client_id=client_id,
                                description=item['description'].strip(),
                                category_id=category_id
                            )
                            db.session.add(new_item)
            
            db.session.commit()
            return jsonify({"status": "success"})
            
        except Exception as e:
            db.session.rollback()
            print(f"Error in edit_client_structure: {str(e)}")  # Debug log
            return jsonify({"status": "error", "message": str(e)}), 500
    
    # GET request handling
    items_by_category = {}
    
    # Get categories that either:
    # 1. Have items for this client
    # 2. Are custom categories for this client
    # 3. Are template categories with items
    categories = db.session.query(ChecklistCategory).distinct().join(
        ChecklistItem,
        (ChecklistItem.category_id == ChecklistCategory.id) & 
        (ChecklistItem.client_id == client_id),
        isouter=True
    ).filter(
        db.or_(
            ChecklistItem.client_id == client_id,
            ChecklistCategory.client_id == client_id,
            db.and_(
                ChecklistCategory.template_id.isnot(None),
                ChecklistItem.id.isnot(None)
            )
        )
    ).all()
    
    for category in categories:
        items = ChecklistItem.query.filter_by(
            client_id=client_id,
            category_id=category.id
        ).all()
        
        # Only include categories that have items or are custom to this client
        if items or category.client_id == client_id:
            items_by_category[category] = items
    
    return render_template(
        "edit_client_structure.html",
        client=client,
        categories=categories,
        items_by_category=items_by_category
    )

@main.route('/add-custom-category/<int:client_id>', methods=['POST'])
@login_required
def add_custom_category(client_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    category_name = data.get('name')
    
    if not category_name:
        return jsonify({'error': 'Category name is required'}), 400
        
    try:
        # Create new category associated with the client only
        category = ChecklistCategory(
            name=category_name,
            client_id=client_id  # Associate with client instead of template
        )
        db.session.add(category)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'category': {
                'id': category.id,
                'name': category.name
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@main.route("/checklist-detail/<int:record_id>")
@login_required
def checklist_detail(record_id):
    record = ChecklistRecord.query.get_or_404(record_id)
    
    # Get all completed items for this record with their details
    completed_items = db.session.query(
        CompletedItem, ChecklistItem, ChecklistCategory
    ).join(
        ChecklistItem, CompletedItem.checklist_item_id == ChecklistItem.id
    ).join(
        ChecklistCategory, ChecklistItem.category_id == ChecklistCategory.id
    ).filter(
        CompletedItem.record_id == record_id
    ).all()
    
    # Organize items by category
    items_by_category = {}
    for completed_item, checklist_item, category in completed_items:
        if category not in items_by_category:
            items_by_category[category] = []
        
        items_by_category[category].append({
            'description': checklist_item.description,
            'completed': completed_item.completed
        })
    
    # Get the notes
    notes = ChecklistNotes.query.filter_by(checklist_record_id=record_id).first()
    
    return render_template(
        'checklist_detail.html',
        record=record,
        convert_to_local_time=convert_to_local_time,
        items_by_category=items_by_category,
        notes=notes
    )

@main.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        if not current_user.check_password(current_password):
            flash("Current password is incorrect")
            return redirect(url_for("main.change_password"))
            
        if new_password != confirm_password:
            flash("New passwords do not match")
            return redirect(url_for("main.change_password"))
            
        if len(new_password) < 6:
            flash("New password must be at least 6 characters long")
            return redirect(url_for("main.change_password"))
            
        current_user.set_password(new_password)
        db.session.commit()
        flash("Password changed successfully")
        return redirect(url_for("main.dashboard"))
        
    return render_template("change_password.html")