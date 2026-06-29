// New Note Wizard Controller
document.addEventListener("DOMContentLoaded", () => {
    const modal = document.getElementById("wizard-modal");
    const openBtn = document.getElementById("new-note-btn");
    const closeBtn = document.getElementById("wizard-close-btn");
    const prevBtn = document.getElementById("wizard-prev-btn");
    const nextBtn = document.getElementById("wizard-next-btn");
    const regenBtn = document.getElementById("wizard-regen-btn");
    const typeButtons = document.querySelectorAll(".wizard-type-btn");
    const progressBar = document.getElementById("wizard-progress");
    const title = document.getElementById("wizard-title");
    
    let currentStep = 1;
    let selectedType = null;
    let wizardDraft = null;
    
    // Open Modal
    openBtn?.addEventListener("click", () => {
        currentStep = 1;
        selectedType = null;
        wizardDraft = null;
        window.stubCompletionName = null;
        typeButtons.forEach(btn => btn.classList.remove("selected"));
        
        showStep(1);
        modal.style.display = "flex";
    });

    const completeStubBtn = document.getElementById("wizard-complete-stub-btn");
    completeStubBtn?.addEventListener("click", () => {
        currentStep = 1;
        selectedType = null;
        wizardDraft = null;
        window.stubCompletionName = window.currentDraft ? window.currentDraft.name : null;
        typeButtons.forEach(btn => btn.classList.remove("selected"));
        
        showStep(1);
        modal.style.display = "flex";
    });
    
    // Close Modal
    const closeModal = () => {
        modal.style.display = "none";
        window.stubCompletionName = null;
    };
    closeBtn?.addEventListener("click", closeModal);
    
    // Type selection
    typeButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            typeButtons.forEach(b => b.classList.remove("selected"));
            btn.classList.add("selected");
            selectedType = btn.getAttribute("data-type");
            nextBtn.disabled = false;
        });
    });
    
    // Navigation
    prevBtn?.addEventListener("click", () => {
        if (currentStep > 1) {
            currentStep--;
            showStep(currentStep);
        }
    });
    
    nextBtn?.addEventListener("click", async () => {
        if (currentStep === 1) {
            currentStep = 2;
            showStep(2);
            await loadSuggestions();
        } else if (currentStep === 2) {
            // Read form values
            saveStep2Values();
            currentStep = 3;
            showStep(3);
            await generateContent();
        } else if (currentStep === 3) {
            // Save generated summary and content
            wizardDraft.summary = document.getElementById("wizard-summary-result").value;
            wizardDraft.content = document.getElementById("wizard-content-result").value;
            currentStep = 4;
            showStep(4);
        } else if (currentStep === 4) {
            // Save draft to DB/Vault
            await createNote();
        }
    });
    
    // Regenerate
    regenBtn?.addEventListener("click", async () => {
        const instruction = document.getElementById("wizard-regen-instruction").value.trim();
        await generateContent(instruction);
    });
    
    function showStep(step) {
        currentStep = step;
        
        // Hide all steps
        document.querySelectorAll(".wizard-step").forEach(s => s.style.display = "none");
        
        // Show active step
        document.getElementById(`wizard-step-${step}`).style.display = "block";
        
        // Progress bar and title
        progressBar.style.width = `${step * 25}%`;
        const titles = {
            1: "Step 1: Choose Type",
            2: "Step 2: Generate/Edit Fields",
            3: "Step 3: Generate Lore",
            4: "Step 4: Final Review"
        };
        title.innerText = `New Note Wizard - ${titles[step]}`;
        
        // Footer buttons state
        prevBtn.disabled = (step === 1);
        
        if (step === 1) {
            nextBtn.innerText = "Next";
            nextBtn.disabled = !selectedType;
        } else if (step === 4) {
            nextBtn.innerText = "Create Note";
            nextBtn.disabled = false;
        } else {
            nextBtn.innerText = "Next";
            nextBtn.disabled = false;
        }
    }
    
    async function loadSuggestions() {
        const fieldsForm = document.getElementById("wizard-fields-form");
        fieldsForm.innerHTML = `<p style="color:var(--text-muted);">Generating seeds...</p>`;
        
        try {
            const res = await fetch(`/api/wizard/suggest?entity_type=${selectedType}`);
            const data = await res.json();
            if (data.status === "success") {
                wizardDraft = data.data;
                if (window.stubCompletionName) {
                    wizardDraft.name = window.stubCompletionName;
                }
                renderWizardForm(wizardDraft, fieldsForm);
            } else {
                fieldsForm.innerHTML = `<p style="color:var(--error);">Failed to generate suggestions: ${data.message}</p>`;
            }
        } catch (e) {
            fieldsForm.innerHTML = `<p style="color:var(--error);">Error loading suggestions: ${e.message}</p>`;
        }
    }
    
    function renderWizardForm(flatDict, formElement) {
        formElement.innerHTML = '';
        const skipKeys = ['is_empty', 'summary', 'content', 'raw_markdown'];
        const keys = Object.keys(flatDict).filter(k => !k.startsWith('_') && !skipKeys.includes(k));
        
        keys.forEach(key => {
            const value = flatDict[key];
            const group = document.createElement('div');
            group.className = 'form-group';
            group.style.display = 'flex';
            group.style.flexDirection = 'column';
            group.style.marginBottom = '15px';
            
            const label = document.createElement('label');
            label.innerText = key.replace(/_/g, ' ').toUpperCase();
            label.style.fontSize = '12px';
            label.style.color = 'var(--text-muted)';
            label.style.fontWeight = 'bold';
            label.style.marginBottom = '5px';
            
            let displayValue = value;
            if (Array.isArray(value)) {
                displayValue = value.join(', ');
            }
            
            const input = document.createElement('input');
            input.type = 'text';
            input.value = displayValue || '';
            input.name = key;
            input.style.width = '100%';
            input.style.padding = '8px';
            input.style.background = 'var(--bg-color)';
            input.style.border = '1px solid var(--border)';
            input.style.color = 'var(--text-color)';
            input.style.borderRadius = '4px';
            
            group.appendChild(label);
            group.appendChild(input);
            formElement.appendChild(group);
        });
    }
    
    function saveStep2Values() {
        const form = document.getElementById("wizard-fields-form");
        const formData = new FormData(form);
        const updatedFields = {};
        for (const [key, value] of formData.entries()) {
            updatedFields[key] = value;
        }
        
        // Merge values back to wizardDraft
        Object.keys(updatedFields).forEach(key => {
            if (Array.isArray(wizardDraft[key])) {
                wizardDraft[key] = updatedFields[key].split(',').map(s => s.trim()).filter(Boolean);
            } else {
                wizardDraft[key] = updatedFields[key];
            }
        });
    }
    
    async function generateContent(instruction = "") {
        const loadingDiv = document.getElementById("wizard-lore-generating");
        const resultDiv = document.getElementById("wizard-lore-result");
        
        loadingDiv.style.display = "flex";
        resultDiv.style.display = "none";
        nextBtn.disabled = true;
        prevBtn.disabled = true;
        
        try {
            const reqBody = {
                draft_state: wizardDraft,
                instruction: instruction,
                provider: document.getElementById('llm-provider-select')?.value || 'gemini',
                model: document.getElementById('llm-model-input')?.value || 'gemini-2.5-flash'
            };
            
            const res = await fetch("/api/wizard/generate-content", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(reqBody)
            });
            const data = await res.json();
            
            if (data.status === "success") {
                document.getElementById("wizard-summary-result").value = data.data.summary || "";
                document.getElementById("wizard-content-result").value = data.data.content || "";
                
                loadingDiv.style.display = "none";
                resultDiv.style.display = "flex";
                nextBtn.disabled = false;
                prevBtn.disabled = false;
            } else {
                alert(`Error generating content: ${data.message}`);
                loadingDiv.style.display = "none";
                prevBtn.disabled = false;
            }
        } catch (e) {
            alert(`Network error: ${e.message}`);
            loadingDiv.style.display = "none";
            prevBtn.disabled = false;
        }
    }
    
    function renderReview() {
        const container = document.getElementById("wizard-review-container");
        container.innerHTML = "";
        
        const summary = document.getElementById("wizard-summary-result").value;
        const content = document.getElementById("wizard-content-result").value;
        
        const fullDraft = {
            ...wizardDraft,
            summary: summary,
            content: content
        };
        
        container.innerText = JSON.stringify(fullDraft, null, 2);
    }
    
    // Listen for reviews
    const originalShowStep = showStep;
    showStep = function(step) {
        originalShowStep(step);
        if (step === 4) {
            renderReview();
        }
    };
    
    async function createNote() {
        nextBtn.disabled = true;
        prevBtn.disabled = true;
        
        const summary = document.getElementById("wizard-summary-result").value;
        const content = document.getElementById("wizard-content-result").value;
        
        const finalDraft = {
            ...wizardDraft,
            summary: summary,
            content: content
        };
        
        window.saveEntityWithIncomingConnections(
            finalDraft,
            async (result) => {
                closeModal();
                if (window.loadEntityIntoEditor) {
                    await window.loadEntityIntoEditor(finalDraft.name);
                }
                if (window.loadGraph) window.loadGraph();
            },
            (errMessage) => {
                alert(`Failed to save note: ${errMessage}`);
                nextBtn.disabled = false;
                prevBtn.disabled = false;
            }
        );
    }
});
