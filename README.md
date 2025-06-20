# NHPC Backup Manager - Professional Edition

[![Version](https://img.shields.io/badge/Version-2.1-blue.svg)](https://github.com/nhpc/backup-manager-pro)
[![License](https://img.shields.io/badge/License-Enterprise-green.svg)](LICENSE.md)
[![Python](https://img.shields.io/badge/Python-3.8+-yellow.svg)](https://python.org)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)](https://github.com/nhpc/backup-manager-pro)

## Overview

**NHPC Backup Manager Professional Edition** is an enterprise-grade backup management system designed for National Hydroelectric Power Corporation infrastructure. This solution provides automated, scheduled, and on-demand backup capabilities for critical business data across multiple departments.

### Key Benefits

- **Enterprise Security**: Military-grade encryption and access controls
- **High Performance**: Optimized for large-scale data operations
- **Real-time Monitoring**: Live dashboard with comprehensive analytics
- **Automated Operations**: Flexible scheduling with multiple frequency options
- **Multi-Department Support**: Departmental isolation and centralized management
- **Modern Interface**: Responsive web-based dashboard accessible from any device

## Features

### Core Functionality
- Automated backup scheduling (daily, weekly, monthly cycles)
- Real-time task monitoring and progress tracking
- Multi-format support (files, databases, system configurations)
- Incremental and full backup capabilities
- Data compression and encryption
- Complete disaster recovery planning

### Management Dashboard
- Executive overview with key performance indicators
- Comprehensive task management interface
- Department-wise analytics and reporting
- Resource monitoring (CPU, memory, storage)
- Configurable alert system (email/SMS notifications)
- Complete audit trail for compliance

### Enterprise Features
- Role-based access control with multi-level permissions
- RESTful API for third-party integrations
- Scalable architecture supporting multiple backup agents
- Automated compliance and audit reporting
- Configurable data retention policies

## System Requirements

### Minimum Requirements
| Component | Specification |
|-----------|---------------|
| **OS** | Windows Server 2016+ / Ubuntu 18.04+ / CentOS 7+ |
| **CPU** | 4 cores, 2.4GHz |
| **RAM** | 8 GB |
| **Storage** | 100 GB available space |
| **Network** | 1 Gbps Ethernet |
| **Database** | MySQL 8.0+ / PostgreSQL 12+ |

### Recommended Requirements
| Component | Specification |
|-----------|---------------|
| **OS** | Windows Server 2019+ / Ubuntu 20.04+ |
| **CPU** | 8+ cores, 3.0GHz+ |
| **RAM** | 32 GB |
| **Storage** | 1 TB NVMe SSD + Network Storage |
| **Network** | 10 Gbps Ethernet |
| **Database** | MySQL 8.0+ Cluster / PostgreSQL 13+ |

## Installation

### Docker Installation (Recommended)

```bash
git clone https://github.com/nhpc/backup-manager-pro.git
cd backup-manager-pro
docker-compose up -d
# Access: http://localhost:5000
```

### Manual Installation

```bash
# 1. Clone and setup environment
git clone https://github.com/nhpc/backup-manager-pro.git
cd backup-manager-pro
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 2. Install dependencies and setup database
pip install -r requirements.txt
python manage.py db init
python manage.py db migrate
python manage.py db upgrade

# 3. Create admin user and start
python manage.py create-admin
python manage.py run
```

## Quick Start

### Initial Login
Access the web interface at `http://your-server:5000`

**Default Credentials:**
- Username: `admin@nhpc.co.in`
- Password: `nhpc_admin_2024!`

> **Important**: Change default credentials immediately after first login.

### Creating Your First Backup Task

```python
import requests

url = "http://localhost:5000/api/tasks"
headers = {"Authorization": "Bearer YOUR_API_TOKEN"}

task_data = {
    "name": "HR Daily Backup",
    "source_path": "/data/hr/",
    "destination_path": "/backup/hr/",
    "department": "Human Resources",
    "type": "incremental",
    "schedule": "daily",
    "time": "02:00"
}

response = requests.post(url, json=task_data, headers=headers)
```

## Configuration

### Environment Variables

```bash
# Application Settings
FLASK_ENV=production
SECRET_KEY=your-secure-secret-key
DEBUG=False

# Database
DATABASE_URL=mysql://user:password@localhost/nhpc_backup
REDIS_URL=redis://localhost:6379/0

# Security
JWT_SECRET_KEY=your-jwt-secret
PASSWORD_SALT=your-password-salt

# Email Configuration
MAIL_SERVER=smtp.nhpc.co.in
MAIL_PORT=587
MAIL_USERNAME=backup-system@nhpc.co.in
MAIL_PASSWORD=your-email-password

# Storage
BACKUP_ROOT_PATH=/data/backups
MAX_BACKUP_SIZE=1TB
COMPRESSION_LEVEL=6
```

### Department Configuration

```yaml
departments:
  hr:
    name: "Human Resources"
    priority: high
    retention_days: 365
    encryption: true
    
  finance:
    name: "Finance"
    priority: critical
    retention_days: 2555  # 7 years
    encryption: true
    compliance: true
    
  engineering:
    name: "Engineering"
    priority: medium
    retention_days: 1095  # 3 years
    encryption: true
```

## API Documentation

### Authentication

```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'
```

### Main Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List all backup tasks |
| POST | `/api/tasks` | Create new backup task |
| GET | `/api/tasks/{id}` | Get task details |
| PUT | `/api/tasks/{id}` | Update task |
| DELETE | `/api/tasks/{id}` | Delete task |
| POST | `/api/tasks/{id}/run` | Execute task |

## Security

### Security Features
- **AES-256 Encryption**: All data encrypted at rest and in transit
- **Multi-factor Authentication**: TOTP and SMS-based 2FA support
- **Role-based Access Control**: Granular permissions system
- **Network Security**: TLS 1.3, IP whitelisting, VPN integration
- **Audit Logging**: Comprehensive compliance trail
- **Secure Key Management**: HSM support available

### Best Practices
1. Enable TLS 1.3 for all communications
2. Implement network segmentation
3. Regular security updates and key rotation
4. Monitor and audit all access attempts
5. Encrypt all backup data with strong keys

## Troubleshooting

### Common Issues

**Backup Task Failing**
```bash
# Check disk space and permissions
df -h
ls -la /backup/path/
tail -f /var/log/nhpc-backup/error.log
```

**High Memory Usage**
```bash
# Monitor system resources
ps aux | grep backup
free -h
systemctl restart nhpc-backup
```

**Database Connection Issues**
```bash
# Verify database connectivity
systemctl status mysql
mysql -u user -p -h host
tail -f /var/log/mysql/error.log
```

### Diagnostic Commands

```bash
# System health check
python manage.py health-check --verbose

# Performance analysis
python manage.py performance-report

# Configuration validation
python manage.py validate-config
```

## Maintenance

### Backup Retention Policies

| Department | Daily | Weekly | Monthly | Yearly |
|------------|-------|--------|---------|--------|
| Finance | 30 days | 12 weeks | 7 years | 10 years |
| HR | 30 days | 8 weeks | 3 years | 5 years |
| Engineering | 14 days | 4 weeks | 2 years | 3 years |
| Operations | 14 days | 4 weeks | 1 year | 2 years |

### Automated Maintenance

```bash
# Daily maintenance
0 1 * * * /usr/local/bin/nhpc-backup daily-maintenance

# Weekly maintenance
0 2 * * 0 /usr/local/bin/nhpc-backup weekly-maintenance

# Monthly maintenance
0 3 1 * * /usr/local/bin/nhpc-backup monthly-maintenance
```

## Support

### NHPC Backup Manager Team
- **Technical Lead**: Priya Sharma (priya.sharma@nhpc.co.in)
- **Security Officer**: Amit Singh (amit.singh@nhpc.co.in)
- **Support Team**: backup-support@nhpc.co.in

### NHPC IT Division
- **Address**: NHPC Corporate Office, Faridabad, Haryana 121007
- **Phone**: +91-129-2277-000
- **Emergency**: +91-129-2277-911 (24/7 Support)

---

## License

**NHPC Backup Manager Professional Edition**

Copyright © 2024 National Hydroelectric Power Corporation (NHPC)

Licensed under NHPC Enterprise License Agreement for internal use within NHPC and subsidiaries only.

---

*Built for NHPC Enterprise Solutions Team*  
*Powering India's Energy Future with Reliable Backup Solutions*
