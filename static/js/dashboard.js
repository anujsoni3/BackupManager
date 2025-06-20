// Auto-refresh task status every 20 seconds
function refreshTaskStatus() {
    const taskRows = document.querySelectorAll('[id^="task-row-"]');
    
    taskRows.forEach(row => {
        const taskId = row.id.split('-')[2];
        const statusBadge = row.querySelector('.status-badge');
        
        // Add visual indicator for running tasks
        if (statusBadge.textContent.toLowerCase() === 'running') {
            if (!row.querySelector('.progress')) {
                const progressDiv = document.createElement('div');
                progressDiv.className = 'progress mt-1';
                progressDiv.innerHTML = `
                    <div class="progress-bar progress-bar-striped progress-bar-animated" 
                         style="width: 50%"></div>
                `;
                statusBadge.after(progressDiv);
            }
        }
        
        // Fetch updated status from API
        fetch(`/api/task_status/${taskId}`)
            .then(response => response.json())
            .then(data => {
                if (!data.error) {
                    // Update status badge
                    statusBadge.className = `status-badge status-${data.status}`;
                    statusBadge.textContent = data.status.charAt(0).toUpperCase() + data.status.slice(1);
                    
                    // Update last run
                    const lastRunCell = row.cells[4];
                    if (data.last_run) {
                        const lastRunDate = new Date(data.last_run);
                        lastRunCell.textContent = lastRunDate.toLocaleString('en-IN', {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                    }
                    
                    // Update next run
                    const nextRunCell = row.cells[5];
                    if (data.next_run) {
                        const nextRunDate = new Date(data.next_run);
                        nextRunCell.textContent = nextRunDate.toLocaleString('en-IN', {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                    }
                    
                    // Update running progress indicator
                    if (data.status === 'running') {
                        if (!row.querySelector('.progress')) {
                            const progressDiv = document.createElement('div');
                            progressDiv.className = 'progress mt-1';
                            progressDiv.innerHTML = `
                                <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                     style="width: 50%"></div>
                            `;
                            statusBadge.after(progressDiv);
                        }
                    } else {
                        const progress = row.querySelector('.progress');
                        if (progress) progress.remove();
                    }
                }
            })
            .catch(error => console.error('Status update error:', error));
    });
}

// Path validation for source/destination inputs
function setupPathValidation() {
    document.querySelectorAll('[data-path-validate]').forEach(input => {
        input.addEventListener('blur', function() {
            const path = this.value.trim();
            const feedback = this.nextElementSibling;
            
            if (path) {
                fetch('/api/validate_path', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name="csrf_token"]').value
                    },
                    body: JSON.stringify({ path: path })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.valid) {
                        this.classList.remove('is-invalid');
                        this.classList.add('is-valid');
                        feedback.textContent = '';
                    } else {
                        this.classList.remove('is-valid');
                        this.classList.add('is-invalid');
                        feedback.textContent = data.message || 'Invalid path';
                    }
                });
            }
        });
    });
}

// Real-time clock
function updateClock() {
    const now = new Date();
    const timeString = now.toLocaleString('en-IN', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    
    const clockElement = document.getElementById('current-time');
    if (clockElement) {
        clockElement.textContent = timeString;
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Start auto-refresh if on dashboard
    if (window.location.pathname === '/') {
        setInterval(refreshTaskStatus, 20000); // 20 seconds
        refreshTaskStatus(); // Initial refresh
    }
    
    // Initialize form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            let isValid = true;
            
            // Validate required fields
            form.querySelectorAll('[required]').forEach(field => {
                if (!field.value.trim()) {
                    field.classList.add('is-invalid');
                    isValid = false;
                }
            });
            
            // Validate paths
            form.querySelectorAll('[data-path-validate]').forEach(field => {
                if (field.classList.contains('is-invalid')) {
                    isValid = false;
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                alert('Please correct the errors in the form');
            }
        });
    });
    
    // Setup path validation
    setupPathValidation();
    
    // Start clock
    setInterval(updateClock, 1000);
    updateClock();
    
    // Add navigation active state
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
            link.innerHTML = `<i class="fas fa-${link.getAttribute('data-icon')} me-1"></i> ${link.textContent}`;
        }
    });
});