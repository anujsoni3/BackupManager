
        // Auto-refresh task status every 30 seconds
        function refreshTaskStatus() {
            const taskRows = document.querySelectorAll('[id^="task-row-"]');
            taskRows.forEach(row => {
                const taskId = row.id.split('-')[2];
                fetch(`/api/task_status/${taskId}`)
                    .then(response => response.json())
                    .then(data => {
                        if (!data.error) {
                            // Update status badge
                            const statusBadge = row.querySelector('.status-badge');
                            statusBadge.className = `status-badge status-${data.status}`;
                            statusBadge.textContent = data.status.charAt(0).toUpperCase() + data.status.slice(1);
                            
                            // Update last run
                            const lastRunCell = row.cells[4];
                            if (data.last_run) {
                                const lastRunDate = new Date(data.last_run);
                                lastRunCell.innerHTML = lastRunDate.toLocaleString('en-IN', {
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
                                nextRunCell.innerHTML = nextRunDate.toLocaleString('en-IN', {
                                    year: 'numeric',
                                    month: '2-digit',
                                    day: '2-digit',
                                    hour: '2-digit',
                                    minute: '2-digit'
                                });
                            }
                        }
                    })
                    .catch(error => console.log('Status update failed for task', taskId));
            });
        }

        // Start auto-refresh if on dashboard
        if (window.location.pathname === '/') {
            setInterval(refreshTaskStatus, 30000); // 30 seconds
        }

        // Form validation
        document.addEventListener('DOMContentLoaded', function() {
            const forms = document.querySelectorAll('form');
            forms.forEach(form => {
                form.addEventListener('submit', function(e) {
                    const requiredFields = form.querySelectorAll('[required]');
                    let isValid = true;
                    
                    requiredFields.forEach(field => {
                        if (!field.value.trim()) {
                            field.classList.add('is-invalid');
                            isValid = false;
                        } else {
                            field.classList.remove('is-invalid');
                        }
                    });
                    
                    if (!isValid) {
                        e.preventDefault();
                        alert('Please fill in all required fields.');
                    }
                });
            });
        });

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
        
        setInterval(updateClock, 1000);
        updateClock();
    