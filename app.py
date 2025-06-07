# NHPC Backup Manager
# A Flask-based web application for managing and scheduling backup tasks using xcopy on Windows.
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import mysql.connector
from mysql.connector import Error
import subprocess
import os
import threading
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'nhpc-backup-manager-2025'

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'nhpc_backup_manager',
    'user': 'root',
    'password': '1234'  # Update with your MySQL password
}

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backup_manager.log'),
        logging.StreamHandler()
    ]
)

class BackupManager:
    def __init__(self):
        self.running_tasks = set()
    
    def get_db_connection(self):
        """Get database connection"""
        try:
            connection = mysql.connector.connect(**DB_CONFIG)
            return connection
        except Error as e:
            logging.error(f"Database connection error: {e}")
            return None
    
    def execute_backup_task(self, task_id):
        """Execute a backup task using xcopy"""
        if task_id in self.running_tasks:
            logging.warning(f"Task {task_id} is already running")
            return
        
        self.running_tasks.add(task_id)
        connection = self.get_db_connection()
        
        if not connection:
            self.running_tasks.discard(task_id)
            return
        
        cursor = connection.cursor()
        start_time = datetime.now()
        
        try:
            # Get task details
            cursor.execute("""
                SELECT task_name, source_path, destination_path, department, task_type 
                FROM backup_tasks WHERE id = %s AND is_active = TRUE
            """, (task_id,))
            
            task = cursor.fetchone()
            if not task:
                logging.error(f"Task {task_id} not found or inactive")
                return
            
            task_name, source_path, dest_path, department, task_type = task
            
            # Update task status to running
            cursor.execute("""
                UPDATE backup_tasks 
                SET status = 'running', last_run = %s 
                WHERE id = %s
            """, (start_time, task_id))
            connection.commit()
            
            # Log start of backup
            cursor.execute("""
                INSERT INTO backup_logs (task_id, run_time, status, log_message)
                VALUES (%s, %s, 'running', %s)
            """, (task_id, start_time, f"Starting backup: {task_name}"))
            log_id = cursor.lastrowid
            connection.commit()
            
            logging.info(f"Starting backup task: {task_name}")
            
            # Execute xcopy command
            xcopy_cmd = [
                'xcopy', source_path, dest_path,
                '/E', '/H', '/C', '/I', '/Y'  # /E=subdirs, /H=hidden, /C=continue on error, /I=assume dest is dir, /Y=suppress overwrite prompt
            ]
            
            result = subprocess.run(
                xcopy_cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            end_time = datetime.now()
            duration = end_time - start_time  # timedelta object
            duration_seconds = duration.total_seconds()

            # Format duration in HH:MM:SS
            hours, remainder = divmod(duration_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

            # Parse xcopy output for file count
            files_copied = 0
            if result.returncode == 0:
                output_lines = result.stdout.split('\n')
                for line in output_lines:
                    if 'File(s) copied' in line:
                        try:
                            files_copied = int(line.split()[0])
                        except:
                            pass
            
            # Calculate backup size (approximation)
            total_size_mb = self.calculate_folder_size(dest_path)
            
            if result.returncode == 0:
                # Success
                cursor.execute("""
                    UPDATE backup_tasks 
                    SET status = 'completed', next_run = %s 
                    WHERE id = %s
                """, (self.calculate_next_run(task_id), task_id))
                
                cursor.execute("""
                    UPDATE backup_logs 
                    SET status = 'success', log_message = %s, files_copied = %s, 
                        total_size_mb = %s, duration_seconds = %s
                    WHERE id = %s
                """, (f"Backup completed successfully. {files_copied} files copied.", 
                     files_copied, total_size_mb, duration_str, log_id))
                
                logging.info(f"Backup task {task_name} completed successfully")
                
            else:
                # Failure
                error_msg = result.stderr or "Unknown error occurred"
                cursor.execute("""
                    UPDATE backup_tasks 
                    SET status = 'failed', next_run = %s 
                    WHERE id = %s
                """, (self.calculate_next_run(task_id), task_id))
                
                cursor.execute("""
                    UPDATE backup_logs 
                    SET status = 'failed', log_message = %s, error_details = %s, 
                        duration_seconds = %s
                    WHERE id = %s
                """, (f"Backup failed: {error_msg}", error_msg, duration_str, log_id))
                
                logging.error(f"Backup task {task_name} failed: {error_msg}")
                
                # Send email notification if enabled
                self.send_failure_notification(task_name, error_msg)
            
            connection.commit()
            
        except subprocess.TimeoutExpired:
            cursor.execute("""
                UPDATE backup_tasks SET status = 'failed' WHERE id = %s
            """, (task_id,))
            cursor.execute("""
                UPDATE backup_logs 
                SET status = 'failed', log_message = 'Backup timeout after 1 hour'
                WHERE id = %s
            """, (log_id,))
            connection.commit()
            logging.error(f"Backup task {task_id} timed out")
            
        except Exception as e:
            cursor.execute("""
                UPDATE backup_tasks SET status = 'failed' WHERE id = %s
            """, (task_id,))
            cursor.execute("""
                UPDATE backup_logs 
                SET status = 'failed', log_message = %s, error_details = %s
                WHERE id = %s
            """, (f"Backup error: {str(e)}", str(e), log_id))
            connection.commit()
            logging.error(f"Backup task {task_id} error: {str(e)}")
            
        finally:
            cursor.close()
            connection.close()
            self.running_tasks.discard(task_id)
    
    def calculate_folder_size(self, folder_path):
        """Calculate folder size in MB"""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except OSError:
                        pass
            return round(total_size / (1024 * 1024), 2)
        except:
            return 0.0
    
    def calculate_next_run(self, task_id):
        """Calculate next run time based on task frequency"""
        connection = self.get_db_connection()
        if not connection:
            return None
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT scheduled_time, repeat_frequency 
            FROM backup_tasks WHERE id = %s
        """, (task_id,))
        
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if not result:
            return None
        
        scheduled_time, frequency = result
        now = datetime.now()
        
        # Parse scheduled time
        hour, minute, second = scheduled_time.hour, scheduled_time.minute, scheduled_time.second
        
        if frequency == 'daily':
            next_run = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
        elif frequency == 'weekly':
            next_run = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
            days_ahead = 7 - now.weekday()
            if days_ahead <= 0 or (days_ahead == 7 and next_run <= now):
                days_ahead += 7
            next_run += timedelta(days=days_ahead)
        elif frequency == 'monthly':
            if now.month == 12:
                next_run = now.replace(year=now.year+1, month=1, day=1, hour=hour, minute=minute, second=second, microsecond=0)
            else:
                next_run = now.replace(month=now.month+1, day=1, hour=hour, minute=minute, second=second, microsecond=0)
        
        return next_run
    
    def send_failure_notification(self, task_name, error_msg):
        """Send email notification for failed backups"""
        # Implementation would depend on your email server settings
        # This is a placeholder for the email functionality
        logging.info(f"Would send email notification for failed task: {task_name}")
    
    def schedule_all_tasks(self):
        """Schedule all active backup tasks"""
        connection = self.get_db_connection()
        if not connection:
            return
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id, task_name, next_run, repeat_frequency, scheduled_time
            FROM backup_tasks 
            WHERE is_active = TRUE AND status != 'paused'
        """)
        
        tasks = cursor.fetchall()
        cursor.close()
        connection.close()
        
        for task_id, task_name, next_run, frequency, scheduled_time in tasks:
            # Remove existing job if it exists
            try:
                scheduler.remove_job(f'backup_task_{task_id}')
            except:
                pass
            
            # Ensure scheduled_time is a datetime.time object
            if isinstance(scheduled_time, timedelta):
                scheduled_time = (datetime.min + scheduled_time).time()

            # Schedule new job
            if frequency == 'daily':
                trigger = CronTrigger(
                    hour=scheduled_time.hour,
                    minute=scheduled_time.minute,
                    second=scheduled_time.second
                )

            elif frequency == 'weekly':
                trigger = CronTrigger(
                    day_of_week=0,  # Monday
                    hour=scheduled_time.hour,
                    minute=scheduled_time.minute,
                    second=scheduled_time.second
                )
            elif frequency == 'monthly':
                trigger = CronTrigger(
                    day=1,  # First day of month
                    hour=scheduled_time.hour,
                    minute=scheduled_time.minute,
                    second=scheduled_time.second
                )
            
            scheduler.add_job(
                func=lambda tid=task_id: threading.Thread(
                    target=self.execute_backup_task, 
                    args=(tid,)
                ).start(),
                trigger=trigger,
                id=f'backup_task_{task_id}',
                name=f'Backup: {task_name}',
                replace_existing=True
            )
            
            logging.info(f"Scheduled task: {task_name} (ID: {task_id})")

# Initialize backup manager
backup_manager = BackupManager()

# Routes
@app.route('/')
def dashboard():
    """Main dashboard showing all backup tasks"""
    connection = backup_manager.get_db_connection()
    if not connection:
        flash('Database connection error', 'error')
        return render_template('error.html')
    
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, task_name, source_path, destination_path, department, 
               task_type, status, last_run, next_run, repeat_frequency
        FROM backup_tasks 
        WHERE is_active = TRUE
        ORDER BY next_run ASC
    """)
    
    tasks = cursor.fetchall()
    
    # Get recent logs
    cursor.execute("""
        SELECT bl.task_id, bt.task_name, bl.run_time, bl.status, bl.log_message
        FROM backup_logs bl
        JOIN backup_tasks bt ON bl.task_id = bt.id
        ORDER BY bl.run_time DESC
        LIMIT 10
    """)
    
    recent_logs = cursor.fetchall()
    cursor.close()
    connection.close()
    
    return render_template('dashboard.html', tasks=tasks, recent_logs=recent_logs)

@app.route('/add_task', methods=['GET', 'POST'])
def add_task():
    """Add new backup task"""
    if request.method == 'POST':
        task_name = request.form['task_name']
        source_path = request.form['source_path']
        destination_path = request.form['destination_path']
        department = request.form['department']
        task_type = request.form['task_type']
        remarks = request.form['remarks']
        scheduled_time = request.form['scheduled_time']
        repeat_frequency = request.form['repeat_frequency']
        
        # Calculate next run
        now = datetime.now()
        time_parts = scheduled_time.split(':')
        hour, minute = int(time_parts[0]), int(time_parts[1])
        
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            if repeat_frequency == 'daily':
                next_run += timedelta(days=1)
            elif repeat_frequency == 'weekly':
                next_run += timedelta(days=7)
            elif repeat_frequency == 'monthly':
                next_run += timedelta(days=30)
        
        connection = backup_manager.get_db_connection()
        if connection:
            cursor = connection.cursor()
            try:
                cursor.execute("""
                    INSERT INTO backup_tasks 
                    (task_name, source_path, destination_path, department, task_type, 
                     remarks, scheduled_time, repeat_frequency, next_run)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (task_name, source_path, destination_path, department, task_type,
                     remarks, scheduled_time, repeat_frequency, next_run))
                
                connection.commit()
                cursor.close()
                connection.close()
                
                # Reschedule all tasks
                backup_manager.schedule_all_tasks()
                
                flash('Backup task added successfully!', 'success')
                return redirect(url_for('dashboard'))
                
            except Error as e:
                flash(f'Error adding task: {str(e)}', 'error')
                cursor.close()
                connection.close()
    
    return render_template('dashboard.html')

@app.route('/run_task/<int:task_id>')
def run_task(task_id):
    """Manually run a backup task"""
    thread = threading.Thread(target=backup_manager.execute_backup_task, args=(task_id,))
    thread.start()
    flash('Backup task started manually', 'info')
    return redirect(url_for('dashboard'))

@app.route('/task_logs/<int:task_id>')
def task_logs(task_id):
    """View logs for a specific task"""
    connection = backup_manager.get_db_connection()
    if not connection:
        flash('Database connection error', 'error')
        return redirect(url_for('dashboard'))
    
    cursor = connection.cursor()
    cursor.execute("""
        SELECT task_name FROM backup_tasks WHERE id = %s
    """, (task_id,))
    task_name = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT run_time, status, log_message, files_copied, total_size_mb, 
               duration_seconds, error_details
        FROM backup_logs 
        WHERE task_id = %s
        ORDER BY run_time DESC
        LIMIT 50
    """, (task_id,))
    
    logs = cursor.fetchall()
    cursor.close()
    connection.close()
    
    return render_template('dashboard.html', task_name=task_name, logs=logs, task_id=task_id)

@app.route('/api/task_status/<int:task_id>')
def api_task_status(task_id):
    """API endpoint to get task status"""
    connection = backup_manager.get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = connection.cursor()
    cursor.execute("""
        SELECT status, last_run, next_run FROM backup_tasks WHERE id = %s
    """, (task_id,))
    
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    
    if result:
        status, last_run, next_run = result
        return jsonify({
            'status': status,
            'last_run': last_run.isoformat() if last_run else None,
            'next_run': next_run.isoformat() if next_run else None
        })
    else:
        return jsonify({'error': 'Task not found'}), 404

if __name__ == '__main__':
    # Schedule all tasks on startup
    backup_manager.schedule_all_tasks()
    
    # Start Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)