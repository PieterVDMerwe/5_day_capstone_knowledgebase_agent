---
name: llm-mocking-guide
description: Standardizes the simple approach for mocking LLM calls (Gemini/Ollama) in pytest to ensure tests run offline without draining API quotas.
---

# LLM Mocking Guide

When writing automated tests in Phase 6, we must ensure that the LLM is entirely mocked out using the "Simple Way" (Python function patching) rather than intercepting network requests.

## 1. Core Rule: No Live API Calls in Unit Tests
Unit tests must run entirely offline, instantly, and deterministically. Never allow `test_pipeline.py` to hit the real Gemini API or the local Ollama instance.

## 2. Mocking Strategy (The Simple Way)
We will use standard Python `unittest.mock.patch` (or pytest's `monkeypatch`) to override the exact LLM SDK functions.

### Mocking Gemini SDK
If the application uses the `google-genai` SDK, you must patch the `generate_content` method to return a dummy response object that mimics the real SDK response object (which has a `.text` property).

**Example Pytest Fixture:**
```python
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_gemini_success():
    # Create a fake response object where response.text contains our strict JSON
    fake_response = MagicMock()
    fake_response.text = '{"name": "Eldrin", "type": "character", "status": "active"}'
    
    # Patch the exact SDK path used in agent.py
    with patch('app.agent.client.models.generate_content', return_value=fake_response) as mock_generate:
        yield mock_generate
```

### Mocking Defensive Parsing Failures
Since our agents rely on a 1-retry self-correction loop for malformed JSON, you MUST write tests that mock a failure followed by a success.

**Example of mocking a retry sequence using `side_effect`:**
```python
@pytest.fixture
def mock_gemini_retry_scenario():
    fake_fail = MagicMock()
    fake_fail.text = 'I am an AI, here is your character: {broken json'
    
    fake_success = MagicMock()
    fake_success.text = '{"name": "Eldrin", "type": "character", "status": "active"}'
    
    # side_effect returns fail on the first call, success on the second
    with patch('app.agent.client.models.generate_content', side_effect=[fake_fail, fake_success]) as mock_generate:
        yield mock_generate
```

## 3. Mock Payload Management
Do not write massive JSON strings inside the test functions. Store the fake JSON payloads in a `tests/fixtures/` directory or at the top of the test file as constants to keep the test logic clean and readable.
