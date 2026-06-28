// Step 4.4: Dynamic Form Engine
function renderForm(flatDict) {
    const form = document.getElementById('dynamic-form');
    form.innerHTML = ''; // Clear existing
    
    // Ignore internal keys like _linter_error and is_empty
    const keys = Object.keys(flatDict).filter(k => !k.startsWith('_') && k !== 'is_empty');
    
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
            input.rows = key === 'content' ? 12 : 5;
            input.value = displayValue || '';
            input.name = key;
            
            if (key === 'content' || key === 'summary') {
                const wrapper = document.createElement('div');
                
                const toolbar = document.createElement('div');
                toolbar.style.display = 'flex';
                toolbar.style.justifyContent = 'flex-end';
                toolbar.style.marginBottom = '5px';
                
                const toggleBtn = document.createElement('button');
                toggleBtn.innerText = 'Preview';
                toggleBtn.type = 'button';
                toggleBtn.style.fontSize = '11px';
                toggleBtn.style.padding = '2px 8px';
                
                const previewDiv = document.createElement('div');
                previewDiv.style.display = 'none';
                previewDiv.style.border = '1px solid var(--border)';
                previewDiv.style.padding = '10px';
                previewDiv.style.backgroundColor = 'var(--panel-bg)';
                previewDiv.style.minHeight = '100px';
                previewDiv.style.maxHeight = '400px';
                previewDiv.style.overflowY = 'auto';
                previewDiv.style.whiteSpace = 'pre-wrap';
                previewDiv.style.lineHeight = '1.5';
                previewDiv.style.color = 'var(--text-color)';
                
                toggleBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (previewDiv.style.display === 'none') {
                        // Switch to preview mode
                        let text = input.value;
                        
                        // Parse Wikilinks: [[Target]] or [[Target|Alias]]
                        text = text.replace(/\[\[([^\]\|]+)(?:\|([^\]]+))?\]\]/g, (match, target, alias) => {
                            const display = alias ? alias : target;
                            return `<a href="#" class="wikilink" data-target="${target}" style="color: var(--accent); text-decoration: underline; font-weight: bold;">${display}</a>`;
                        });
                        
                        previewDiv.innerHTML = text;
                        
                        // Attach click handlers to open links in the editor
                        const links = previewDiv.querySelectorAll('.wikilink');
                        links.forEach(link => {
                            link.addEventListener('click', (ev) => {
                                ev.preventDefault();
                                const targetName = ev.target.getAttribute('data-target');
                                if (window.loadEntityIntoEditor) {
                                    window.loadEntityIntoEditor(targetName);
                                }
                            });
                        });
                        
                        input.style.display = 'none';
                        previewDiv.style.display = 'block';
                        toggleBtn.innerText = 'Edit';
                        toggleBtn.style.backgroundColor = 'var(--accent)';
                        toggleBtn.style.color = '#fff';
                    } else {
                        // Switch to edit mode
                        input.style.display = 'block';
                        previewDiv.style.display = 'none';
                        toggleBtn.innerText = 'Preview';
                        toggleBtn.style.backgroundColor = '';
                        toggleBtn.style.color = '';
                    }
                });
                
                toolbar.appendChild(toggleBtn);
                group.appendChild(label);
                group.appendChild(toolbar);
                
                wrapper.appendChild(input);
                wrapper.appendChild(previewDiv);
                group.appendChild(wrapper);
                
                // Skip the default append logic below
                form.appendChild(group);
                return;
            }
        } else {
            input = document.createElement('input');
            input.type = 'text';
            input.value = displayValue || '';
            input.name = key;
        }
        
        // Listen for entity_type changes to swap schema dynamically
        if (key === 'entity_type') {
            input.addEventListener('change', (e) => {
                const newType = e.target.value.trim();
                if (window.appSchemas && window.appSchemas[newType]) {
                    // Gather current form values so we don't lose overlapping data (like name, summary)
                    const formData = new FormData(form);
                    const currentValues = {};
                    for (const [k, v] of formData.entries()) {
                        currentValues[k] = v;
                    }
                    
                    // Load the empty schema template
                    const newDraft = { ...window.appSchemas[newType] };
                    
                    // Restore overlapping values
                    Object.keys(newDraft).forEach(k => {
                        if (currentValues[k] !== undefined && currentValues[k] !== "") {
                            newDraft[k] = currentValues[k];
                        }
                    });
                    
                    // Ensure the new type is set
                    newDraft.entity_type = newType;
                    
                    // Update global state and re-render
                    if (window.currentDraft !== undefined) {
                        window.currentDraft = newDraft;
                    }
                    renderForm(newDraft);
                }
            });
        }
        
        group.appendChild(label);
        group.appendChild(input);
        form.appendChild(group);
    });
}
