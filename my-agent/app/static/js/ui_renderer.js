// Step 4.4: Dynamic Form Engine
function renderForm(flatDict) {
    const form = document.getElementById('dynamic-form');
    form.innerHTML = ''; // Clear existing
    
    // Ignore internal keys like _linter_error
    const keys = Object.keys(flatDict).filter(k => !k.startsWith('_'));
    
    keys.forEach(key => {
        const value = flatDict[key];
        const group = document.createElement('div');
        group.className = 'form-group';
        group.style.marginBottom = '15px';
        
        const label = document.createElement('label');
        label.innerText = key.replace(/_/g, ' ').toUpperCase();
        label.style.display = 'block';
        label.style.marginBottom = '5px';
        label.style.fontSize = '12px';
        label.style.color = 'var(--text-muted)';
        label.style.fontWeight = 'bold';
        
        // Render simple arrays as comma-separated strings for now
        let displayValue = value;
        if (Array.isArray(value)) {
            displayValue = value.join(', ');
        } else if (typeof value === 'object' && value !== null) {
            displayValue = JSON.stringify(value); // Fallback for nested objects
        }
        
        let input;
        // Use textarea for summary/content
        if (key === 'summary' || key === 'content' || key === 'raw_markdown') {
            input = document.createElement('textarea');
            input.rows = 5;
        } else {
            input = document.createElement('input');
            input.type = 'text';
        }
        
        input.value = displayValue || '';
        input.name = key;
        
        group.appendChild(label);
        group.appendChild(input);
        form.appendChild(group);
    });
}
