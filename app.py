# NHPC Backup Manager - Secure Admin Version
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import mysql.connector
from mysql.connector import Error
import subprocess
import os
import threading
import time
from datetime import datetime, timedelta, time as dt_time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import bcrypt
from functools import wraps
import shutil
import sys
# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'nhpc-backup-manager-2025-secure-admin'

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'nhpc_backup_manager',
    'user': 'your-user',
    'password': 'your-password'  # Update with your MySQL password
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

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def login_required_ajax(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            else:
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
    
    def init_admin_tables(self):
        """Initialize admin and enhanced tables"""
        connection = self.get_db_connection()
        if not connection:
            return False
        
        cursor = connection.cursor()
        
        try:
            # Create admins table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INT DEFAULT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    last_login TIMESTAMP NULL,
                    FOREIGN KEY (created_by) REFERENCES admins(id) ON DELETE SET NULL
                )
            """)
            
            # Add admin_id to task_logs if not exists
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name = 'backup_logs' AND column_name = 'admin_id'
            """)
            
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    ALTER TABLE backup_logs 
                    ADD COLUMN admin_id INT DEFAULT NULL,
                    ADD FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE SET NULL
                """)
            
            # Create default admin if none exists
            cursor.execute("SELECT COUNT(*) FROM admins")
            if cursor.fetchone()[0] == 0:
                default_password = "admin123"  # Change this immediately after first login
                password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())
                
                cursor.execute("""
                    INSERT INTO admins (name, email, password_hash) 
                    VALUES (%s, %s, %s)
                """, ("Default Admin", "admin@nhpc.com", password_hash))
                
                logging.info("Default admin created: admin@nhpc.com / admin123")
            
            connection.commit()
            return True
            
        except Error as e:
            logging.error(f"Error initializing admin tables: {e}")
            return False
        finally:
            cursor.close()
            connection.close()
    
    def verify_admin(self, email, password):
        """Verify admin credentials"""
        connection = self.get_db_connection()
        if not connection:
            return None
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id, name, email, password_hash, is_active 
            FROM admins WHERE email = %s
        """, (email,))
        
        admin = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if admin and admin[4]:  # Check if admin exists and is active
            admin_id, name, email, password_hash, is_active = admin
            if bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                # Update last login
                connection = self.get_db_connection()
                if connection:
                    cursor = connection.cursor()
                    cursor.execute("""
                        UPDATE admins SET last_login = %s WHERE id = %s
                    """, (datetime.now(), admin_id))
                    connection.commit()
                    cursor.close()
                    connection.close()
                
                return {'id': admin_id, 'name': name, 'email': email}
        
        return None
    
    def create_admin(self, name, email, password, created_by_id):
        """Create new admin (only by existing admin)"""
        connection = self.get_db_connection()
        if not connection:
            return False, "Database connection error"
        
        cursor = connection.cursor()
        
        try:
            # Check if email already exists
            cursor.execute("SELECT id FROM admins WHERE email = %s", (email,))
            if cursor.fetchone():
                return False, "Email already exists"
            
            # Hash password
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            
            # Create admin
            cursor.execute("""
                INSERT INTO admins (name, email, password_hash, created_by) 
                VALUES (%s, %s, %s, %s)
            """, (name, email, password_hash, created_by_id))
            
            connection.commit()
            return True, "Admin created successfully"
            
        except Error as e:
            return False, f"Error creating admin: {str(e)}"
        finally:
            cursor.close()
            connection.close()
    # Add this method to your BackupManager class
    def update_admin_password(self, admin_id, current_password, new_password):
        """Update admin password after verification"""
        # Verify current password first
        if not self.verify_admin_password(admin_id, current_password):
            return False, "Current password is incorrect"
        
        # Hash new password
        new_password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        
        connection = self.get_db_connection()
        if not connection:
            return False, "Database connection error"
        
        cursor = connection.cursor()
        try:
            cursor.execute("""
                UPDATE admins
                SET password_hash = %s
                WHERE id = %s
            """, (new_password_hash, admin_id))
            connection.commit()
            return True, "Password updated successfully"
        except Error as e:
            return False, f"Error updating password: {str(e)}"
        finally:
            cursor.close()
            connection.close()

    def verify_admin_password(self, admin_id, password):
        """Verify admin password without requiring email"""
        connection = self.get_db_connection()
        if not connection:
            return False
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT password_hash 
            FROM admins 
            WHERE id = %s
        """, (admin_id,))
        
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if result and result[0]:
            stored_hash = result[0].encode('utf-8')
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
        
        return False
    
    # Task Logging and History
    def update_task_log(self, log_id, status, message, **kwargs):
        """Update backup log status and details after completion or failure."""
        connection = self.get_db_connection()
        if not connection:
            return
        
        cursor = connection.cursor()
        try:
            cursor.execute("""
                UPDATE backup_logs 
                SET status = %s, log_message = %s, 
                    files_copied = %s, total_size_mb = %s, 
                    duration_seconds = %s, error_details = %s
                WHERE id = %s
            """, (
                status,
                message,
                kwargs.get('files_copied', 0),
                kwargs.get('total_size_mb', 0.0),
                kwargs.get('duration_seconds', 0),
                kwargs.get('error_details', None),
                log_id
            ))
            connection.commit()
        except Error as e:
            logging.error(f"Error updating task log: {e}")
        finally:
            cursor.close()
            connection.close()
   
    def update_task_status(self, task_id, status):
        """Update task status"""
        try:
            connection = self.get_db_connection()
            if not connection:
                return
            
            cursor = connection.cursor()
            query = """
                UPDATE backup_tasks 
                SET status = %s, updated_at = NOW()
                WHERE id = %s
            """
            cursor.execute(query, (status, task_id))
            connection.commit()
            return True
            
        except Exception as e:
            print(f"Error updating task status: {e}")
            connection.rollback()
            return False

    def log_task_execution(self, task_id, admin_id, status, message, **kwargs):
        """Log new task execution and return log_id"""
        connection = self.get_db_connection()
        if not connection:
            return None

        cursor = connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO backup_logs 
                (task_id, admin_id, run_time, status, log_message, files_copied, 
                total_size_mb, duration_seconds, error_details)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                task_id, admin_id, datetime.now(), status, message,
                kwargs.get('files_copied', 0),
                kwargs.get('total_size_mb', 0.0),
                kwargs.get('duration_seconds', 0),
                kwargs.get('error_details', None)
            ))
            log_id = cursor.lastrowid  # ✅ Important
            connection.commit()
            return log_id
        except Error as e:
            logging.error(f"Error logging task execution: {e}")
            return None
        finally:
            cursor.close()
            connection.close()

    def get_admin_task_history(self, admin_id):
        """Get task history for specific admin"""
        connection = self.get_db_connection()
        if not connection:
            return []
        
        cursor = connection.cursor()
        if admin_id == 1:  # Superadmin
            cursor.execute("""
                SELECT bt.task_name, bl.run_time, bl.status, bl.log_message, bl.files_copied, 
                    bl.total_size_mb, bl.duration_seconds
                FROM backup_logs bl
                JOIN backup_tasks bt ON bl.task_id = bt.id
                ORDER BY bl.run_time DESC
                LIMIT 50
            """)
        else:
            cursor.execute("""
                SELECT bt.task_name, bl.run_time, bl.status, bl.log_message, bl.files_copied, 
                    bl.total_size_mb, bl.duration_seconds
                FROM backup_logs bl
                JOIN backup_tasks bt ON bl.task_id = bt.id
                WHERE bl.admin_id = %s
                ORDER BY bl.run_time DESC
                LIMIT 50
            """, (admin_id,))
            
        history = cursor.fetchall()
        cursor.close()
        connection.close()
        return history
    
    def get_admin_tasks(self, admin_id):
        """Get all tasks created by a specific admin, or all if admin_id == 1 (default admin)"""
        try:
            connection = self.get_db_connection()
            if not connection:
                return []
            
            cursor = connection.cursor()

            if admin_id == 1:
                # Super admin can view all tasks
                query = """
                    SELECT id, task_name, source_path, destination_path, department, 
                        task_type, remarks, scheduled_time, repeat_frequency, 
                        status, last_run, next_run, created_at, updated_at, 
                        is_active, created_by
                    FROM backup_tasks 
                    ORDER BY created_at DESC
                """
                cursor.execute(query)
            else:
                # Regular admin sees only their tasks
                query = """
                    SELECT id, task_name, source_path, destination_path, department, 
                        task_type, remarks, scheduled_time, repeat_frequency, 
                        status, last_run, next_run, created_at, updated_at, 
                        is_active, created_by
                    FROM backup_tasks 
                    WHERE created_by = %s 
                    ORDER BY created_at DESC
                """
                cursor.execute(query, (admin_id,))

            tasks = cursor.fetchall()
            
            # Convert to list of dictionaries for easier template usage
            task_list = []
            for task in tasks:
                task_dict = {
                    'id': task[0],
                    'task_name': task[1],
                    'source_path': task[2],
                    'destination_path': task[3],
                    'department': task[4],
                    'task_type': task[5],
                    'remarks': task[6],
                    'scheduled_time': task[7],
                    'repeat_frequency': task[8],
                    'status': task[9],
                    'last_run': task[10],
                    'next_run': task[11],
                    'created_at': task[12],
                    'updated_at': task[13],
                    'is_active': task[14],
                    'created_by': task[15]
                }
                task_list.append(task_dict)
            
            return task_list
            
        except Exception as e:
            print(f"Error getting admin tasks: {e}")
            return []

    def get_task_by_id(self, task_id):
        """Get a specific task by ID"""
        try:
            connection = self.get_db_connection()
            if not connection:
                return []
            
            cursor = connection.cursor()
            query = """
                SELECT id, task_name, source_path, destination_path, department, 
                       task_type, remarks, scheduled_time, repeat_frequency, 
                       status, last_run, next_run, created_at, updated_at, 
                       is_active, created_by
                FROM backup_tasks 
                WHERE id = %s
            """
            cursor.execute(query, (task_id,))
            task = cursor.fetchone()
            
            if task:
                return {
                    'id': task[0],
                    'task_name': task[1],
                    'source_path': task[2],
                    'destination_path': task[3],
                    'department': task[4],
                    'task_type': task[5],
                    'remarks': task[6],
                    'scheduled_time': task[7],
                    'repeat_frequency': task[8],
                    'status': task[9],
                    'last_run': task[10],
                    'next_run': task[11],
                    'created_at': task[12],
                    'updated_at': task[13],
                    'is_active': task[14],
                    'created_by': task[15]
                }
            return None
            
        except Exception as e:
            print(f"Error getting task by ID: {e}")
            return None

    def update_task(self, task_id, task_data):
        """Update an existing task"""
        connection = None
        cursor = None
        try:
            connection = self.get_db_connection()
            if not connection:
                return False

            cursor = connection.cursor()
            query = """
                UPDATE backup_tasks 
                SET task_name = %s, source_path = %s, destination_path = %s,
                    department = %s, task_type = %s, remarks = %s,
                    scheduled_time = %s, repeat_frequency = %s,
                    next_run = %s, status = %s, updated_at = NOW()
                WHERE id = %s
            """
            cursor.execute(query, (
                task_data['task_name'],
                task_data['source_path'],
                task_data['destination_path'],
                task_data['department'],
                task_data['task_type'],
                task_data['remarks'],
                task_data['scheduled_time'],
                task_data['repeat_frequency'],
                task_data['next_run'],
                task_data['status'],
                task_id
            ))
            connection.commit()
            # Reschedule tasks
            self.schedule_all_tasks()
            return cursor.rowcount > 0

        except Exception as e:
            print(f"Error updating task: {e}")
            if connection:
                connection.rollback()
            return False

        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
   
    def delete_task(self, task_id):
        """Delete a task and its related logs safely using task_id"""
        connection = None
        cursor = None
        try:
            connection = self.get_db_connection()
            if not connection:
                return False

            cursor = connection.cursor()

            # Step 1: Delete from backup_logs where task_id matches
            cursor.execute("DELETE FROM backup_logs WHERE task_id = %s", (task_id,))

            # Step 2: Delete the actual task
            cursor.execute("DELETE FROM backup_tasks WHERE id = %s", (task_id,))

            # Step 3: Remove scheduled job if any
            try:
                scheduler.remove_job(f'backup_task_{task_id}')
            except:
                pass

            connection.commit()
            return True

        except Exception as e:
            print(f"Error deleting task: {e}")
            if connection:
                connection.rollback()
            return False

        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()


            

    #COPY FILES OR MAIN BACKUP LOGIC
    def get_previous_file_states(self, task_id):
        """Retrieve last backup state including folders"""
        connection = self.get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT relative_path, last_modified, size, is_directory 
            FROM file_backup_state 
            WHERE task_id = %s
        """, (task_id,))
        prev_state = {
            row['relative_path']: {
                'last_modified': row['last_modified'],
                'size': row['size'],
                'is_directory': bool(row['is_directory'])
            } 
            for row in cursor.fetchall()
        }
        cursor.close()
        connection.close()
        return prev_state
    
    def get_current_file_states(self, source_path):
        """Scan source directory to get current file and folder states"""
        current_state = {}
        
        # Process folders first
        for dirpath, dirnames, _ in os.walk(source_path):
            rel_path = os.path.relpath(dirpath, source_path)
            if rel_path == ".":
                rel_path = ""
                
            try:
                stat = os.stat(dirpath)
                last_modified = datetime.fromtimestamp(stat.st_mtime)
                current_state[rel_path] = {
                    'last_modified': last_modified,
                    'size': 0,
                    'is_directory': True,
                    'full_path': dirpath
                }
            except Exception as e:
                logging.warning(f"Could not access directory {rel_path}: {str(e)}")
        
        # Process files
        for dirpath, _, filenames in os.walk(source_path):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(full_path, source_path)
                try:
                    stat = os.stat(full_path)
                    last_modified = datetime.fromtimestamp(stat.st_mtime)
                    size = stat.st_size
                    current_state[rel_path] = {
                        'last_modified': last_modified,
                        'size': size,
                        'is_directory': False,
                        'full_path': full_path
                    }
                except Exception as e:
                    logging.warning(f"Could not access file {rel_path}: {str(e)}")
        
        return current_state

    def get_changed_items(self, prev_state, current_state):
        """Identify changed files, folders, and deleted items"""
        changed_files = []
        new_files = []
        changed_folders = []
        new_folders = []
        deleted_items = []

        # Check for new or modified items
        for rel_path, curr_data in current_state.items():
            is_dir = curr_data['is_directory']
            prev_data = prev_state.get(rel_path)
            
            if not prev_data:
                # New item
                if is_dir:
                    new_folders.append((rel_path, curr_data['full_path'], curr_data['last_modified']))
                else:
                    new_files.append((rel_path, curr_data['full_path'], curr_data['last_modified'], curr_data['size']))
            else:
                # Existing item - check for changes
                if is_dir:
                    # Directory changed if modification time differs
                    if prev_data['last_modified'] != curr_data['last_modified']:
                        changed_folders.append((rel_path, curr_data['full_path'], curr_data['last_modified']))
                else:
                    # File changed if size or mod time differs
                    if (prev_data['last_modified'] != curr_data['last_modified'] or 
                        prev_data['size'] != curr_data['size']):
                        changed_files.append((rel_path, curr_data['full_path'], curr_data['last_modified'], curr_data['size']))
        
        # Check for deleted items
        for rel_path in set(prev_state.keys()) - set(current_state.keys()):
            deleted_items.append(rel_path)
        
        return changed_files, new_files, changed_folders, new_folders, deleted_items

    
    def copy_changed_items(self, changed_files, new_files, changed_folders, new_folders, dest_path):
        """Copy changed items and create necessary folders"""
        # Create new and changed folders (including empty ones)
        for folder_list in [new_folders, changed_folders]:
            for rel_path, full_src_path, _ in folder_list:
                dest_folder_path = os.path.join(dest_path, rel_path)
                os.makedirs(dest_folder_path, exist_ok=True)
        
        # Copy changed files
        copied_count = 0
        for file_list in [changed_files, new_files]:
            for rel_path, full_src_path, _, _ in file_list:
                dest_file_path = os.path.join(dest_path, rel_path)
                # Ensure parent directory exists
                os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)
                shutil.copy2(full_src_path, dest_file_path)
                copied_count += 1
        
        return copied_count

        
    def update_file_states(self, task_id, changed_files, new_files, changed_folders, new_folders, deleted_items):
        """Update database with new file/folder states"""
        connection = self.get_db_connection()
        cursor = connection.cursor()
        
        # Update changed and new files
        for item_list in [changed_files, new_files]:
            for rel_path, _, last_modified, size in item_list:
                cursor.execute("""
                    REPLACE INTO file_backup_state 
                    (task_id, relative_path, last_modified, size, is_directory)
                    VALUES (%s, %s, %s, %s, %s)
                """, (task_id, rel_path, last_modified, size, False))
        
        # Update changed and new folders
        for item_list in [changed_folders, new_folders]:
            for rel_path, _, last_modified in item_list:
                cursor.execute("""
                    REPLACE INTO file_backup_state 
                    (task_id, relative_path, last_modified, size, is_directory)
                    VALUES (%s, %s, %s, %s, %s)
                """, (task_id, rel_path, last_modified, 0, True))
        
        # Remove deleted items
        if deleted_items:
            placeholders = ', '.join(['%s'] * len(deleted_items))
            cursor.execute(f"""
                DELETE FROM file_backup_state 
                WHERE task_id = %s 
                AND relative_path IN ({placeholders})
            """, (task_id, *deleted_items))
        
        connection.commit()
        cursor.close()
        connection.close()

    def execute_backup_task(self, task_id, admin_id=1):
        """Execute a backup task with admin tracking and proper logging"""
        
        
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
        log_id = None
        try:
            # Fetch task details
            cursor.execute("""
                SELECT task_name, source_path, destination_path, department, task_type,
                    scheduled_time, repeat_frequency
                FROM backup_tasks WHERE id = %s AND is_active = TRUE
            """, (task_id,))
            task = cursor.fetchone()

            if not task:
                logging.error(f"Task {task_id} not found or inactive")
                return

            task_name, source_path, dest_path, department, task_type, scheduled_time, frequency = task

            # Normalize scheduled_time to time object
            if isinstance(scheduled_time, timedelta):
                total_seconds = scheduled_time.total_seconds()
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                scheduled_time = dt_time(hours, minutes)
            elif isinstance(scheduled_time, str):
                scheduled_time = datetime.strptime(scheduled_time, '%H:%M').time()
            # ✅ Check if source path exists
            if not os.path.exists(source_path):
                msg = f"Source path does not exist: {source_path}"
                logging.error(msg)

                log_id = self.log_task_execution(task_id, admin_id, 'failed', msg)
                cursor.execute("UPDATE backup_tasks SET status = 'failed' WHERE id = %s", (task_id,))
                connection.commit()

                self.update_task_log(
                    log_id, 'failed', msg,
                    error_details=msg,
                    files_copied=0,
                    total_size_mb=0.0,
                    duration_seconds=0
                )
                return
            # Update status and last_run before actual backup
            cursor.execute("""
                UPDATE backup_tasks
                SET status = 'running', last_run = %s
                WHERE id = %s
            """, (start_time, task_id))
            connection.commit()

            # Start log entry
            log_id = self.log_task_execution(
                task_id, admin_id, 'running', f"Starting backup: {task_name}"
            )

            logging.info(f"Starting incremental backup task: {task_name}")

            # Get item states
            prev_state = self.get_previous_file_states(task_id)
            current_state = self.get_current_file_states(source_path)
            changed_files, new_files, changed_folders, new_folders, deleted_items = self.get_changed_items(
                prev_state, current_state
            )
            
            # Perform backup
            files_copied = self.copy_changed_items(
                changed_files, new_files, changed_folders, new_folders, dest_path
            )
            self.update_file_states(
                task_id, changed_files, new_files, changed_folders, new_folders, deleted_items
            )
            
            # Calculate metrics
            end_time = datetime.now()
            duration_seconds = int((end_time - start_time).total_seconds())
            total_size_mb = self.calculate_folder_size(dest_path)
            next_run = self.calculate_next_run(scheduled_time, frequency)
            
            # Detailed change reporting
            change_counts = {
                'files_modified': len(changed_files),
                'files_added': len(new_files),
                'folders_modified': len(changed_folders),
                'folders_added': len(new_folders),
                'items_deleted': len(deleted_items)
            }
            total_changes = sum(change_counts.values())
            
            if total_changes > 0:
                # Prepare human-readable change summary
                changes = []
                if change_counts['files_modified']:
                    changes.append(f"{change_counts['files_modified']} file(s) modified")
                if change_counts['files_added']:
                    changes.append(f"{change_counts['files_added']} new file(s)")
                if change_counts['folders_modified']:
                    changes.append(f"{change_counts['folders_modified']} folder(s) modified")
                if change_counts['folders_added']:
                    changes.append(f"{change_counts['folders_added']} new folder(s)")
                if change_counts['items_deleted']:
                    changes.append(f"{change_counts['items_deleted']} item(s) deleted")
                    
                change_msg = ", ".join(changes)
                
                # Update task status
                cursor.execute("""
                    UPDATE backup_tasks SET status = 'completed', next_run = %s 
                    WHERE id = %s
                """, (next_run, task_id))

                # Update log
                self.update_task_log(
                    log_id, 'success',
                    f"Backup completed. {change_msg}. {files_copied} files copied.",
                    files_copied=files_copied,
                    total_size_mb=total_size_mb,
                    duration_seconds=duration_seconds,
                    **change_counts
                )
                logging.info(f"Backup task {task_name} completed. {change_msg}.")

            else:
                # No changes detected
                cursor.execute("""
                    UPDATE backup_tasks SET status = 'completed', next_run = %s WHERE id = %s
                """, (next_run, task_id))

                self.update_task_log(
                    log_id, 'success',
                    "No files changed since last backup.",
                    files_copied=0,
                    total_size_mb=total_size_mb,
                    duration_seconds=duration_seconds
                )
                logging.info(f"No changes found for backup task {task_name}.")

            connection.commit()

        except Exception as e:
            try:
                cursor.execute("UPDATE backup_tasks SET status = 'failed' WHERE id = %s", (task_id,))
                connection.commit()
            except Exception as db_err:
                logging.error(f"Failed to update task status to failed: {db_err}")

            try:
                if log_id:
                    self.update_task_log(
                        log_id, 'failed',
                        f"Backup error: {str(e)}",
                        error_details=str(e)
                    )
            except Exception as log_err:
                logging.error(f"Failed to update task log for task {task_id}: {log_err}")

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
    
    def calculate_next_run(self, scheduled_time, frequency):
        """Calculate next run time based on task frequency"""
        now = datetime.now()
        
        # Convert any type to time object
        if isinstance(scheduled_time, str):
            scheduled_time = datetime.strptime(scheduled_time, '%H:%M').time()
        elif isinstance(scheduled_time, timedelta):
            total_seconds = scheduled_time.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            scheduled_time = dt_time(hours, minutes)
        elif not isinstance(scheduled_time, dt_time):
            logging.error(f"Invalid scheduled_time type: {type(scheduled_time)}")
            scheduled_time = now.time()
        
        base_time = now.replace(
            hour=scheduled_time.hour,
            minute=scheduled_time.minute,
            second=0,
            microsecond=0
        )
        
        if frequency == 'daily':
            if base_time <= now:
                return base_time + timedelta(days=1)
            return base_time
            
        elif frequency == 'weekly':
            days_ahead = (0 - now.weekday()) % 7
            if days_ahead == 0 and base_time <= now:
                days_ahead = 7
            return base_time + timedelta(days=days_ahead)
            
        elif frequency == 'monthly':
            if now.month == 12:
                next_month = now.replace(year=now.year+1, month=1, day=1)
            else:
                next_month = now.replace(month=now.month+1, day=1)
            return next_month.replace(
                hour=scheduled_time.hour,
                minute=scheduled_time.minute,
                second=0
            )
        
        if base_time <= now:
            return base_time + timedelta(days=1)
        return base_time
    
    def send_failure_notification(self, task_name, error_msg):
        """Send email notification for failed backups"""
        logging.info(f"Would send email notification for failed task: {task_name}")
    
    def schedule_all_tasks(self):
        """Schedule all active backup tasks"""
        connection = self.get_db_connection()
        if not connection:
            return
        
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id, task_name, next_run, repeat_frequency, scheduled_time, created_by
            FROM backup_tasks 
            WHERE is_active = TRUE AND status != 'paused'
        """)
        
        tasks = cursor.fetchall()
        cursor.close()
        connection.close()
        
        for task_id, task_name, next_run, frequency, scheduled_time, created_by in tasks:
            try:
                scheduler.remove_job(f'backup_task_{task_id}')
            except:
                pass
            
            if isinstance(scheduled_time, str):
                scheduled_time = datetime.strptime(scheduled_time, '%H:%M').time()
            elif isinstance(scheduled_time, timedelta):
                total_seconds = scheduled_time.total_seconds()
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                scheduled_time = dt_time(hours, minutes)
            elif not isinstance(scheduled_time, dt_time):
                scheduled_time = datetime.now().time()
                logging.error(f"Invalid scheduled_time type for task {task_id}")

            if frequency == 'daily':
                trigger = CronTrigger(
                    hour=scheduled_time.hour,
                    minute=scheduled_time.minute,
                    second=0
                )
            elif frequency == 'weekly':
                trigger = CronTrigger(
                    day_of_week='mon',
                    hour=scheduled_time.hour,
                    minute=scheduled_time.minute,
                    second=0
                )
            elif frequency == 'monthly':
                trigger = CronTrigger(
                    day=1,
                    hour=scheduled_time.hour,
                    minute=scheduled_time.minute,
                    second=0
                )
            
            scheduler.add_job(
                func=lambda tid=task_id,aid=created_by: threading.Thread(
                    target=self.execute_backup_task, 
                    args=(tid, aid)  # None for scheduled tasks
                ).start(),
                trigger=trigger,
                id=f'backup_task_{task_id}',
                name=f'Backup: {task_name}',
                replace_existing=True
            )
            
            logging.info(f"Scheduled task: {task_name} (ID: {task_id})")

    


# Initialize backup manager
backup_manager = BackupManager()

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        admin = backup_manager.verify_admin(email, password)
        if admin:
            session['admin_id'] = admin['id']
            session['admin_name'] = admin['name']
            session['admin_email'] = admin['email']
            flash(f'Welcome back, {admin["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/change_password', methods=['POST'])
def change_password():
    if 'admin_id' not in session:
        flash('You must be logged in to change your password', 'danger')
        return redirect(url_for('login'))
    
    admin_id = session['admin_id']
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    # Validate inputs
    if not all([current_password, new_password, confirm_password]):
        flash('All fields are required', 'danger')
        return redirect(url_for('profile'))
    
    if new_password != confirm_password:
        flash('New password and confirmation do not match', 'danger')
        return redirect(url_for('profile'))
    
    if len(new_password) < 8:
        flash('Password must be at least 8 characters', 'danger')
        return redirect(url_for('profile'))
    
    # Update password

    success, message = backup_manager.update_admin_password(
        admin_id, 
        current_password, 
        new_password
    )
    
    if success:
        flash('Password changed successfully!', 'success')
    else:
        flash(f'Password change failed: {message}', 'danger')
    
    return redirect(url_for('profile'))

@app.route('/logout')
@login_required
def logout():
    """Admin logout"""
    admin_name = session.get('admin_name', 'Admin')
    session.clear()
    flash(f'Goodbye, {admin_name}!', 'info')
    return redirect(url_for('login'))

@app.route('/add_admin', methods=['GET', 'POST'])
@login_required
def add_admin():
    """Add new admin (only by existing admin)"""
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
        else:
            success, message = backup_manager.create_admin(
                name, email, password, session['admin_id']
            )
            flash(message, 'success' if success else 'error')
            if success:
                return redirect(url_for('profile'))
    
    return render_template('add_admin.html')

@app.route('/profile')
@login_required
def profile():
    """Admin profile page showing their tasks and activity"""
    admin_id = session['admin_id']
    
    # Get admin's tasks
    admin_tasks = backup_manager.get_admin_tasks(admin_id)
    print("Admin ID:", admin_id)
    print("Admin Tasks:", admin_tasks)

    # Get task history (existing function)
    task_history = backup_manager.get_admin_task_history(admin_id)
    
    return render_template('profile.html',
                         admin_name=session['admin_name'],
                         admin_email=session['admin_email'],
                         admin_tasks=admin_tasks,
                         task_history=task_history)

# Protected Routes (existing routes with @login_required)
@app.route('/')
@login_required
def dashboard():
    """Main dashboard - PROTECTED"""
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
    
    # Get recent logs with admin names
    cursor.execute("""
        SELECT bl.task_id, bt.task_name, bl.run_time, bl.status, bl.log_message, a.name
        FROM backup_logs bl
        JOIN backup_tasks bt ON bl.task_id = bt.id
        LEFT JOIN admins a ON bl.admin_id = a.id
        ORDER BY bl.run_time DESC
        LIMIT 10
    """)
    recent_logs = cursor.fetchall()
    
    # Task counters
    cursor.execute("SELECT COUNT(*) FROM backup_tasks WHERE is_active = TRUE")
    total_tasks = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM backup_tasks WHERE status = 'completed'")
    completed_tasks = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM backup_tasks WHERE status = 'running'")
    running_tasks = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM backup_tasks WHERE status = 'failed'")
    failed_tasks = cursor.fetchone()[0]

    cursor.close()
    connection.close()
    
    return render_template('dashboard.html', 
                         tasks=tasks, 
                         recent_logs=recent_logs, 
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks,
                         running_tasks=running_tasks,
                         failed_tasks=failed_tasks)

@app.route('/add_task', methods=['GET', 'POST'])
@login_required
def add_task():
    """Add new backup task - PROTECTED"""
    if request.method == 'POST':
        task_name = request.form['task_name']
        source_path = request.form['source_path']
        destination_path = request.form['destination_path']
        department = request.form['department']
        task_type = request.form['task_type']
        remarks = request.form['remarks']
        scheduled_time = request.form['scheduled_time']
        repeat_frequency = request.form['repeat_frequency']

        scheduled_time_obj = datetime.strptime(scheduled_time, '%H:%M').time()
        next_run = backup_manager.calculate_next_run(scheduled_time_obj, repeat_frequency)

        admin_id = session.get('admin_id', 1)  # default to superadmin if not found

        connection = backup_manager.get_db_connection()
        if connection:
            cursor = connection.cursor()
            try:
                cursor.execute("""
                    INSERT INTO backup_tasks 
                    (task_name, source_path, destination_path, department, task_type, 
                     remarks, scheduled_time, repeat_frequency, next_run, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    task_name, source_path, destination_path, department, task_type,
                    remarks, scheduled_time, repeat_frequency, next_run, admin_id
                ))

                connection.commit()
                task_id = cursor.lastrowid
                cursor.close()
                connection.close()

                backup_manager.schedule_all_tasks()
                flash('Backup task added successfully!', 'success')
                return redirect(url_for('dashboard'))

            except Error as e:
                flash(f'Error adding task: {str(e)}', 'error')
                cursor.close()
                connection.close()

    return render_template('dashboard.html')

@app.route('/edit_task/<int:task_id>')
@login_required
def edit_task(task_id):
    """Edit task page"""
    admin_id = session['admin_id']
    task = backup_manager.get_task_by_id(task_id)
    
    if not task:
        flash('Task not found', 'error')
        return redirect(url_for('profile'))
    
    # Check if the current admin owns this task
    if task['created_by'] != admin_id:
        flash('You can only edit your own tasks', 'error')
        return redirect(url_for('profile'))
    
    return render_template('edit_task.html', task=task)

@app.route('/edit_task/<int:task_id>', methods=['POST'])
@login_required
def update_task(task_id):
    """Update task"""
    admin_id = session['admin_id']
    task = backup_manager.get_task_by_id(task_id)

    if not task or task['created_by'] != admin_id:
        flash('Task not found or access denied', 'error')
        return redirect(url_for('profile'))

        # Get raw time string from form
        # Get raw time string from form
    raw_time = request.form.get('scheduled_time', '').strip()

    # Attempt to parse time in multiple formats
    scheduled_time = None
    for fmt in ('%H:%M', '%H:%M:%S'):
        try:
            scheduled_time = datetime.strptime(raw_time, fmt).time()
            break  # stop after first successful format
        except ValueError:
            continue

    # If parsing failed for all formats
    if not scheduled_time:
        flash(f"Invalid scheduled time format: '{raw_time}'", 'error')
        return redirect(url_for('profile'))

    # Frequency from form
    repeat_frequency = request.form.get('repeat_frequency', 'daily')

    # Now calculate next_run
    next_run = backup_manager.calculate_next_run(scheduled_time, repeat_frequency)
    status = 'scheduled' if next_run > datetime.now() else 'running'

    task_data = {
        'task_name': request.form['task_name'],
        'source_path': request.form['source_path'],
        'destination_path': request.form['destination_path'],
        'department': request.form['department'],
        'task_type': request.form['task_type'],
        'remarks': request.form.get('remarks', ''),
        'scheduled_time': scheduled_time,
        'repeat_frequency': repeat_frequency,
        'next_run': next_run,  # Pass this explicitly if needed
        'status': status
    }

    if backup_manager.update_task(task_id, task_data):
        flash('Task updated successfully', 'success')
    else:
        flash('Error updating task', 'error')

    return redirect(url_for('profile'))


@app.route('/delete_task/<int:task_id>', methods=['DELETE'])
@login_required_ajax
def delete_task(task_id):
    admin_id = session['admin_id']
    task = backup_manager.get_task_by_id(task_id)

    if not task:
        return jsonify({'success': False, 'message': 'Task not found'})

    if task['created_by'] != admin_id:
        return jsonify({'success': False, 'message': 'You can only delete your own tasks'})

    if backup_manager.delete_task(task_id):
        return jsonify({'success': True, 'message': 'Task deleted'})
    return jsonify({'success': False, 'message': 'Could not delete task'})


@app.route('/run_task/<int:task_id>')
@login_required
def run_task(task_id):
    """Manually run a backup task - PROTECTED"""
    admin_id = session['admin_id']
    thread = threading.Thread(
        target=backup_manager.execute_backup_task, 
        args=(task_id, admin_id)
    )
    thread.start()
    flash('Backup task started manually', 'info')
    return redirect(url_for('dashboard'))


@app.route('/task_logs/<int:task_id>')
@login_required
def task_logs(task_id):
    """View logs for a specific task - PROTECTED"""
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
        SELECT bl.run_time, bl.status, bl.log_message, bl.files_copied, bl.total_size_mb, 
               bl.duration_seconds, bl.error_details, a.name
        FROM backup_logs bl
        LEFT JOIN admins a ON bl.admin_id = a.id
        WHERE bl.task_id = %s
        ORDER BY bl.run_time DESC
        LIMIT 50
    """, (task_id,))
    
    logs = cursor.fetchall()
    cursor.close()
    connection.close()
    
    return render_template('dashboard.html', task_name=task_name, logs=logs, task_id=task_id)

@app.route('/api/validate_path', methods=['POST'])
@login_required
def validate_path():
    """Validate file path - PROTECTED"""
    path = request.json.get('path', '')
    if not os.path.exists(path):
        return jsonify({'valid': False, 'message': 'Path does not exist'}), 200
    if not os.access(path, os.R_OK):
        return jsonify({'valid': False, 'message': 'Read access denied'}), 200
    return jsonify({'valid': True}), 200

@app.route('/api/task_status/<int:task_id>')
@login_required
def api_task_status(task_id):
    """API endpoint to get task status - PROTECTED"""
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
    # Initialize admin tables
    backup_manager.init_admin_tables()
    
    # Schedule all tasks on startup
    backup_manager.schedule_all_tasks()
    
    # Start Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
