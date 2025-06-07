import os

class Config:
    SECRET_KEY = 'NHPC-Backup-Manager-2025-Secure-Key'
    
    # Database Configuration
    DB_CONFIG = {
        'host': 'localhost',
        'database': 'nhpc_backup_manager',
        'user': 'backup_admin',
        'password': 'NHPC@Backup2025'
    }
    
    # Email Configuration (for notifications)
    MAIL_SERVER = 'your-smtp-server.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'backup-alerts@nhpc.com'
    MAIL_PASSWORD = 'your-email-password'
    
    # Backup Settings
    MAX_CONCURRENT_TASKS = 3
    LOG_RETENTION_DAYS = 30
    BACKUP_TIMEOUT_HOURS = 2