document.addEventListener('DOMContentLoaded', () => {
    // --- Top Bar Toggle Logic ---
    const toggleChatBtn = document.getElementById('toggle-chat-btn');
    const toggleEditorBtn = document.getElementById('toggle-editor-btn');
    const toggleExplorerBtn = document.getElementById('toggle-explorer-btn');

    const chatPanel = document.getElementById('chat-panel');
    const editorPanel = document.getElementById('editor-panel');
    const explorerPanel = document.getElementById('graph-panel');
    const resizer1 = document.getElementById('resizer-1');
    const resizer2 = document.getElementById('resizer-2');

    function togglePanel(btn, panel, resizerToHide) {
        if (panel.style.display === 'none') {
            panel.style.display = 'flex';
            if (resizerToHide) resizerToHide.style.display = 'block';
            btn.style.opacity = '1';
        } else {
            panel.style.display = 'none';
            if (resizerToHide) resizerToHide.style.display = 'none';
            btn.style.opacity = '0.5';
        }
        
        // Dispatch window resize so the D3 graph redraws cleanly
        window.dispatchEvent(new Event('resize'));
    }

    toggleChatBtn.addEventListener('click', () => togglePanel(toggleChatBtn, chatPanel, resizer1));
    toggleEditorBtn.addEventListener('click', () => togglePanel(toggleEditorBtn, editorPanel, resizer2));
    toggleExplorerBtn.addEventListener('click', () => togglePanel(toggleExplorerBtn, explorerPanel, resizer2));


    // --- Resizer Drag Logic ---
    let isResizing1 = false;
    let isResizing2 = false;

    resizer1.addEventListener('mousedown', (e) => {
        isResizing1 = true;
        document.body.style.cursor = 'col-resize';
        // Prevent text selection while dragging
        document.body.style.userSelect = 'none';
    });

    resizer2.addEventListener('mousedown', (e) => {
        isResizing2 = true;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing1 && !isResizing2) return;

        if (isResizing1) {
            // Adjust left panel (Chat) width
            let newWidth = e.clientX;
            if (newWidth < 200) newWidth = 200; 
            if (newWidth > window.innerWidth / 2) newWidth = window.innerWidth / 2;
            chatPanel.style.width = newWidth + 'px';
        }

        if (isResizing2) {
            // Adjust right panel (Explorer) width
            let newWidth = window.innerWidth - e.clientX;
            if (newWidth < 250) newWidth = 250;
            if (newWidth > window.innerWidth / 2) newWidth = window.innerWidth / 2;
            explorerPanel.style.width = newWidth + 'px';
        }
    });

    document.addEventListener('mouseup', () => {
        if (isResizing1 || isResizing2) {
            isResizing1 = false;
            isResizing2 = false;
            document.body.style.cursor = 'default';
            document.body.style.userSelect = 'auto';
            // Snap graph to new bounds
            window.dispatchEvent(new Event('resize'));
        }
    });

    // --- Pop Out / Pull In Logic ---
    const popOutBtn = document.getElementById('pop-out-btn');
    const pullInBtn = document.getElementById('pull-in-btn');
    const graphContainer = document.getElementById('graph-container');
    let popupWindow = null;
    let placeholderDiv = null;

    popOutBtn.addEventListener('click', () => {
        // Open the popup window
        popupWindow = window.open('/popup.html', 'LoreGraphPopup', 'width=1000,height=800');
        
        // Hide local graph, update buttons
        graphContainer.style.display = 'none';
        popOutBtn.style.display = 'none';
        pullInBtn.style.display = 'inline-block';
        
        // Show placeholder
        if (!placeholderDiv) {
            placeholderDiv = document.createElement('div');
            placeholderDiv.style.padding = '40px 20px';
            placeholderDiv.style.color = 'var(--text-muted)';
            placeholderDiv.style.textAlign = 'center';
            placeholderDiv.innerHTML = '<p>Graph is open in a separate window.</p>';
            explorerPanel.appendChild(placeholderDiv);
        }
        placeholderDiv.style.display = 'block';
    });

    window.pullInGraph = function(fromPopupClose = false) {
        if (!fromPopupClose && popupWindow && !popupWindow.closed) {
            popupWindow.close();
        }
        popupWindow = null;
        
        graphContainer.style.display = 'block';
        popOutBtn.style.display = 'inline-block';
        pullInBtn.style.display = 'none';
        
        if (placeholderDiv) {
            placeholderDiv.style.display = 'none';
        }
        
        window.dispatchEvent(new Event('resize'));
    };

    pullInBtn.addEventListener('click', () => window.pullInGraph(false));
});
