import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import ollama

# Load environment variables from .env file
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class SecurityException(ValueError):
    """Raised when an adversarial prompt injection pattern is detected."""
    pass

INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|above)\s+instructions",
    r"system\s+override",
    r"override\s+system\s+instructions",
    r"you\s+are\s+now\s+a",
    r"forget\s+(?:your\s+)?previous\s+system",
    r"disregard\s+(?:all\s+)?instructions",
    r"new\s+system\s+prompt",
    r"stop\s+following\s+instructions",
    r"(?:print|output|reveal|show|display).*(?:system|initial|developer|original).*(?:prompt|instruction)",
    r"word-for-word.*(?:initial|system|developer|original|prompt|instruction)"
]

def check_prompt_injection(prompt: str) -> None:
    """Statically scans prompt for common adversarial injection patterns."""
    if not prompt:
        return
    import re
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            raise SecurityException("Adversarial prompt injection pattern detected. Request blocked.")

class LLMClient:
    """
    Centralized LLM Client managing Gemini and Ollama API calls.
    Used by all agents to ensure consistent configuration and mocking potential.
    """
    def __init__(self, provider: str = "ollama", model_name: str = None):
        self.provider = provider
        if provider == "gemini":
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not found in environment. Check your .env file.")
            self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            self.model_name = model_name or "gemini-2.5-flash"
        elif provider == "ollama":
            self.model_name = model_name or "batiai/gemma4-e2b:q4"
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def generate(self, prompt: str, system_instruction: str = None, response_schema: type = None) -> str:
        """
        Generates content from the LLM. 
        If response_schema is provided (a Pydantic model), the output is constrained to JSON.
        """
        check_prompt_injection(prompt)
        
        if self.provider == "gemini":
            if not hasattr(self, 'gemini_client') or self.gemini_client is None:
                if not GEMINI_API_KEY:
                    raise ValueError("GEMINI_API_KEY not found in environment. Check your .env file.")
                self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2, # Low temperature for more deterministic/structured lore
            )
            if response_schema:
                config.response_mime_type = "application/json"
                config.response_schema = response_schema
                
            response = self.gemini_client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            return response.text
            
        elif self.provider == "ollama":
            messages = []
            
            # Inject schema into prompt for Ollama since it lacks strict Structured Outputs API like Gemini
            if response_schema:
                schema_dict = response_schema.model_json_schema()
                import json
                schema_str = json.dumps(schema_dict, indent=2)
                schema_instruction = f"\n\nYou MUST return valid JSON. Do not include markdown formatting or conversational text. Your JSON MUST strictly conform to this JSON Schema:\n{schema_str}"
                
                if system_instruction:
                    system_instruction += schema_instruction
                else:
                    system_instruction = schema_instruction
                    
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            
            options = {}
            if response_schema:
                # Ollama JSON mode
                options["format"] = "json"
                
            response = ollama.chat(
                model=self.model_name,
                messages=messages,
                options=options
            )
            return response['message']['content']
