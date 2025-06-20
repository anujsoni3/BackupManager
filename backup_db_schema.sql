-- NHPC Backup Manager Database Schema

-- Create database
CREATE DATABASE IF NOT EXISTS nhpc_backup_manager;
USE nhpc_backup_manager;

-- Table for storing backup task definitions
CREATE TABLE backup_tasks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    task_name VARCHAR(255) NOT NULL UNIQUE,
    source_path VARCHAR(500) NOT NULL,
    destination_path VARCHAR(500) NOT NULL,
    department VARCHAR(100) NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    remarks TEXT,
    scheduled_time TIME NOT NULL,
    repeat_frequency ENUM('daily', 'weekly', 'monthly') DEFAULT 'daily',
    status ENUM('scheduled', 'running', 'completed', 'failed', 'paused') DEFAULT 'scheduled',
    last_run DATETIME NULL,
    next_run DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Table for storing backup execution logs
CREATE TABLE backup_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    task_id INT NOT NULL,
    run_time DATETIME NOT NULL,
    status ENUM('success', 'failed', 'running') NOT NULL,
    log_message TEXT,
    files_copied INT DEFAULT 0,
    total_size_mb DECIMAL(10,2) DEFAULT 0.00,
    duration_seconds INT DEFAULT 0,
    error_details TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES backup_tasks(id) ON DELETE CASCADE
);

-- Table for system settings
CREATE TABLE system_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    setting_key VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Insert default system settings
INSERT INTO system_settings (setting_key, setting_value, description) VALUES
('email_notifications', 'false', 'Enable/disable email notifications for failed backups'),
('admin_email', 'admin@nhpc.com', 'Email address for notifications'),
('max_log_retention_days', '30', 'Number of days to keep backup logs'),
('concurrent_tasks_limit', '3', 'Maximum number of backup tasks that can run simultaneously');

-- Create indexes for better performance
CREATE INDEX idx_backup_tasks_next_run ON backup_tasks(next_run);
CREATE INDEX idx_backup_tasks_status ON backup_tasks(status);
CREATE INDEX idx_backup_logs_task_id ON backup_logs(task_id);
CREATE INDEX idx_backup_logs_run_time ON backup_logs(run_time);

-- Sample data for testing
INSERT INTO backup_tasks (task_name, source_path, destination_path, department, task_type, remarks, scheduled_time, repeat_frequency, next_run) VALUES
('Daily HR Backup', 'C:\\NHPC\\HR\\Data', 'D:\\Backup\\HR', 'Human Resources', 'Database', 'Daily backup of HR files', '02:00:00', 'daily', '2025-06-06 02:00:00'),
('Weekly Finance Backup', 'C:\\NHPC\\Finance', 'E:\\Backup\\Finance', 'Finance', 'Full Backup', 'Weekly complete backup', '01:00:00', 'weekly', '2025-06-08 01:00:00'),
('Monthly Reports Archive', 'C:\\NHPC\\Reports', 'F:\\Archive\\Reports', 'Administration', 'Archive', 'Monthly reports archival', '23:30:00', 'monthly', '2025-07-01 23:30:00');



ALTER TABLE backup_logs MODIFY duration_seconds VARCHAR(8);


-- Table for admin users
CREATE TABLE admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INT DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP NULL,
    FOREIGN KEY (created_by) REFERENCES admins(id) ON DELETE SET NULL
);
