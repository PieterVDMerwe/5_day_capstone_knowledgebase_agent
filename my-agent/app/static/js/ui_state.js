window.appSchemas = {};

document.addEventListener("DOMContentLoaded", async () => {
    try {
        const res = await fetch('/api/schemas');
        const data = await res.json();
        if (data.status === 'success') {
            window.appSchemas = data.data;
        }
    } catch (e) {
        console.error("Failed to load schemas", e);
    }
});

// Step 4.3: State Machine Implementation
const State = {
    IDLE: 'Idle',
    GENERATING: 'Generating...',
    DRAFT_RECEIVED: 'Draft Received. Awaiting Approval.',
    SAVING: 'Saving...',
    SYNCING: 'Syncing...'
};

let currentState = State.IDLE;
window.currentDraft = null;

function updateStatus(state) {
    currentState = state;
    document.getElementById('status-indicator').innerText = `Status: ${state}`;
    
    // Toggle button states based on 5-Step UI Pipeline
    const saveBtn = document.getElementById('save-btn');
    const discardBtn = document.getElementById('discard-btn');
    const sendBtn = document.getElementById('send-btn');
    const input = document.getElementById('chat-input');
    
    if (state === State.DRAFT_RECEIVED) {
        saveBtn.disabled = false;
        discardBtn.disabled = false;
        sendBtn.disabled = false;
        input.disabled = false;
    } else if (state === State.IDLE) {
        saveBtn.disabled = true;
        discardBtn.disabled = true;
        sendBtn.disabled = false;
        input.disabled = false;
    } else {
        // Generating, Saving, Syncing
        saveBtn.disabled = true;
        discardBtn.disabled = true;
        sendBtn.disabled = true;
        input.disabled = true;
    }
}

function appendMessage(sender, text) {
    const history = document.getElementById('chat-history');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;
    msgDiv.innerText = text;
    history.appendChild(msgDiv);
    history.scrollTop = history.scrollHeight;
}

document.getElementById('send-btn').addEventListener('click', async () => {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;
    
    appendMessage('user', text);
    input.value = '';
    
    updateStatus(State.GENERATING);
    
    try {
        const payload = {
            user_message: text,
            draft_state: window.currentDraft
        };
        
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        // Envelope: { status, current_step, data, message }
        
        appendMessage('system', result.message);
        
        if (result.data && result.data.draft) {
            window.currentDraft = result.data.draft;
            document.querySelector('.placeholder-text').style.display = 'none';
            renderForm(window.currentDraft);
            updateStatus(State.DRAFT_RECEIVED);
        } else if (result.data && result.data.answer) {
            appendMessage('system', result.data.answer);
            updateStatus(State.IDLE);
        } else {
            updateStatus(State.IDLE);
        }
    } catch (err) {
        appendMessage('system', 'Error connecting to server: ' + err.message);
        updateStatus(State.IDLE);
    }
});

document.getElementById('chat-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        document.getElementById('send-btn').click();
    }
});

document.getElementById('discard-btn').addEventListener('click', () => {
    window.currentDraft = null;
    document.getElementById('dynamic-form').innerHTML = '';
    document.querySelector('.placeholder-text').style.display = 'block';
    updateStatus(State.IDLE);
    appendMessage('system', 'Draft discarded.');
});

document.getElementById('save-btn').addEventListener('click', async () => {
    // Gather all inputs from the form dynamically
    const form = document.getElementById('dynamic-form');
    const formData = new FormData(form);
    const updatedDraft = {};
    for (const [key, value] of formData.entries()) {
        updatedDraft[key] = value;
    }
    
    // Merge back any internal fields or arrays that aren't strings in the form
    const payloadDraft = { ...window.currentDraft, ...updatedDraft };
    
    // We try to convert comma-separated fields back to arrays based on original draft format
    Object.keys(payloadDraft).forEach(key => {
        if (Array.isArray(window.currentDraft[key]) && typeof updatedDraft[key] === 'string') {
            payloadDraft[key] = updatedDraft[key].split(',').map(s => s.trim()).filter(Boolean);
        }
    });

    updateStatus(State.SAVING);
    appendMessage('system', 'Validating logic, linking entities, and saving to vault...');
    
    try {
        const response = await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ draft_state: payloadDraft })
        });
        
        const result = await response.json();
        
        if (result.status === 'warning' || result.status === 'error') {
            appendMessage('system', result.message);
            updateStatus(State.DRAFT_RECEIVED); // Leave draft open so user can fix issues
        } else {
            appendMessage('system', result.message);
            window.currentDraft = null;
            document.getElementById('dynamic-form').innerHTML = '';
            document.querySelector('.placeholder-text').style.display = 'block';
            updateStatus(State.IDLE);
            
            // Reload graph if global function exists
            if (window.loadGraph) window.loadGraph();
        }
    } catch (err) {
        appendMessage('system', 'Error saving entity: ' + err.message);
        updateStatus(State.DRAFT_RECEIVED);
    }
});

// Load Entity from DB into Editor
window.loadEntityIntoEditor = async function(name) {
    try {
        updateStatus(State.GENERATING);
        const res = await fetch(`/api/entity/${encodeURIComponent(name)}`);
        const data = await res.json();
        
        if (data.status === 'success') {
            let fetchedDraft = data.data;
            const type = fetchedDraft.entity_type;
            
            // Merge the loaded data onto the empty schema template to guarantee all fields are present
            if (window.appSchemas && window.appSchemas[type]) {
                window.currentDraft = { ...window.appSchemas[type], ...fetchedDraft };
            } else {
                window.currentDraft = fetchedDraft;
            }
            
            document.querySelector('.placeholder-text').style.display = 'none';
            renderForm(window.currentDraft);
            updateStatus(State.DRAFT_RECEIVED);
            appendMessage('system', `Loaded '${name}' into the editor.`);
        } else {
            appendMessage('system', 'Error loading entity: ' + data.message);
            updateStatus(State.IDLE);
        }
    } catch (err) {
        appendMessage('system', 'Error loading entity: ' + err.message);
        updateStatus(State.IDLE);
    }
};

// View Toggles
document.getElementById('view-graph-btn').addEventListener('click', (e) => {
    e.target.style.opacity = '1';
    document.getElementById('view-list-btn').style.opacity = '0.5';
    document.getElementById('graph-container').style.display = 'block';
    document.getElementById('list-container').style.display = 'none';
});

document.getElementById('view-list-btn').addEventListener('click', (e) => {
    e.target.style.opacity = '1';
    document.getElementById('view-graph-btn').style.opacity = '0.5';
    document.getElementById('graph-container').style.display = 'none';
    document.getElementById('list-container').style.display = 'flex';
    window.renderList();
});

// List Renderer
window.renderList = function() {
    const listDiv = document.getElementById('list-items');
    listDiv.innerHTML = '';
    const query = document.getElementById('list-search').value.toLowerCase();
    
    const nodes = window.allNodes || [];
    const filtered = nodes.filter(n => n.id.toLowerCase().includes(query));
    
    filtered.forEach(node => {
        const item = document.createElement('div');
        item.style.padding = '10px';
        item.style.borderBottom = '1px solid var(--border)';
        item.style.cursor = 'pointer';
        item.style.color = 'var(--text-color)';
        item.innerHTML = `<strong>${node.id}</strong> <span style="color:var(--text-muted);font-size:12px;margin-left:8px;">(${node.group})</span>`;
        
        item.addEventListener('click', () => window.loadEntityIntoEditor(node.id));
        item.addEventListener('mouseover', () => item.style.backgroundColor = 'var(--panel-bg)');
        item.addEventListener('mouseout', () => item.style.backgroundColor = 'transparent');
        
        listDiv.appendChild(item);
    });
};

document.getElementById('list-search').addEventListener('input', window.renderList);
