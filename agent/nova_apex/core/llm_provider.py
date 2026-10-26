import os
import json
import base64
from typing import Dict, Any, List, Optional
import httpx
from nova_apex.config.settings import settings
from nova_apex.core.logger import agent_logger

class LLMProvider:
    """
    Unified multi-provider AI reasoning & vision abstraction:
    - Google Gemini (Gemini 2.5 Flash / Gemini Pro)
    - OpenAI (GPT-4o)
    - Anthropic Claude
    - Local Ollama
    - Autonomous Heuristic Engine (deterministic rule-based semantic planning fallback)
    """

    def __init__(self):
        self.provider = settings.default_llm_provider
        self.model = settings.default_model

    def get_active_provider(self) -> str:
        if self.provider != "auto":
            return self.provider
        if settings.gemini_api_key:
            return "gemini"
        if settings.openai_api_key:
            return "openai"
        if settings.anthropic_api_key:
            return "anthropic"
        return "heuristic"

    async def generate_response(
        self,
        prompt: str,
        system_instruction: str = "",
        image_path: Optional[str] = None,
        json_mode: bool = False
    ) -> str:
        active = self.get_active_provider()
        agent_logger.thinking(f"Reasoning with engine [{active}]...", domain="LLM")

        try:
            if active == "gemini":
                return await self._call_gemini(prompt, system_instruction, image_path, json_mode)
            elif active == "openai":
                return await self._call_openai(prompt, system_instruction, image_path, json_mode)
            elif active == "anthropic":
                return await self._call_anthropic(prompt, system_instruction, image_path)
            elif active == "ollama":
                return await self._call_ollama(prompt, system_instruction, json_mode)
            else:
                return self._call_heuristic_planner(prompt, system_instruction)
        except Exception as e:
            agent_logger.warning(f"Provider [{active}] error ({e}). Falling back to Autonomous Heuristic Engine.", domain="LLM")
            return self._call_heuristic_planner(prompt, system_instruction)

    async def _call_gemini(
        self, prompt: str, system_instruction: str, image_path: Optional[str], json_mode: bool
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={settings.gemini_api_key}"
        parts: List[Dict[str, Any]] = []

        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as img_file:
                b64 = base64.b64encode(img_file.read()).decode("utf-8")
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": b64
                    }
                })

        parts.append({"text": prompt})

        payload = {
            "contents": [{"parts": parts}],
            "system_instruction": {"parts": [{"text": system_instruction}]} if system_instruction else None,
            "generationConfig": {
                "response_mime_type": "application/json" if json_mode else "text/plain",
                "temperature": 0.2
            }
        }
        # Clean nulls
        if not payload["system_instruction"]:
            del payload["system_instruction"]

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _call_openai(
        self, prompt: str, system_instruction: str, image_path: Optional[str], json_mode: bool
    ) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json"
        }
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        content_parts = []
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"}
                })
        content_parts.append({"type": "text", "text": prompt})

        messages.append({"role": "user", "content": content_parts})

        payload = {
            "model": "gpt-4o",
            "messages": messages,
            "response_format": {"type": "json_object"} if json_mode else {"type": "text"}
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def _call_anthropic(
        self, prompt: str, system_instruction: str, image_path: Optional[str]
    ) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        content = []
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64}
                })
        content.append({"type": "text", "text": prompt})

        payload = {
            "model": "claude-3-7-sonnet-20250219",
            "max_tokens": 4096,
            "system": system_instruction,
            "messages": [{"role": "user", "content": content}]
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]

    async def _call_ollama(
        self, prompt: str, system_instruction: str, json_mode: bool
    ) -> str:
        url = f"{settings.ollama_base_url}/api/generate"
        payload = {
            "model": "llama3",
            "prompt": f"{system_instruction}\n\n{prompt}",
            "stream": False,
            "format": "json" if json_mode else ""
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()["response"]

    def _call_heuristic_planner(self, prompt: str, system_instruction: str) -> str:
        """
        High-performance deterministic reasoning fallback:
        Translates natural language intents into high-level agent action steps when offline or no API keys are provided.
        """
        lower = prompt.lower()
        steps = []
        step_id = 1

        # Check for web account creation intent
        if "create account" in lower or "register" in lower or "signup" in lower or "sign up" in lower:
            # Extract target site if specified
            target_url = "https://github.com/signup"
            if "google" in lower: target_url = "https://accounts.google.com/signup"
            elif "twitter" in lower or "x.com" in lower: target_url = "https://twitter.com/i/flow/signup"
            elif "reddit" in lower: target_url = "https://www.reddit.com/register/"
            elif "http" in lower:
                words = prompt.split()
                for w in words:
                    if w.startswith("http"): target_url = w; break

            steps.append({
                "step_id": step_id,
                "title": f"Navigate to Registration Portal",
                "description": f"Open browser and go to {target_url}",
                "domain": "browser",
                "action_type": "navigate",
                "target": target_url,
                "value": target_url,
                "params": {}
            })
            step_id += 1
            steps.append({
                "step_id": step_id,
                "title": "Analyze Registration Form & Fill Profile",
                "description": "Inspect DOM, detect input fields (email, username, password), and fill with synthesized credentials",
                "domain": "browser",
                "action_type": "create_account",
                "target": "auto_detect_form",
                "value": "auto_generate",
                "params": {"store_in_vault": True}
            })
            step_id += 1
            steps.append({
                "step_id": step_id,
                "title": "Verify and Complete Sign-up Confirmation",
                "description": "Wait for submission confirmation and capture verification proof",
                "domain": "browser",
                "action_type": "browser_screenshot",
                "target": "full_page",
                "value": "",
                "params": {}
            })

        # Check for desktop / file creation intent
        elif any(k in lower for k in ["create file", "folder", "write file", "make directory", "scaffold", "desktop"]):
            steps.append({
                "step_id": step_id,
                "title": "Initialize Project Workspace & Directories",
                "description": "Create required folders in workspace",
                "domain": "filesystem",
                "action_type": "create_folder",
                "target": "automated_workspace",
                "value": "",
                "params": {}
            })
            step_id += 1
            steps.append({
                "step_id": step_id,
                "title": "Generate Target Artifact / Code / Documentation",
                "description": "Write requested content to target files",
                "domain": "filesystem",
                "action_type": "write_file",
                "target": "automated_workspace/manifest.json",
                "value": "{\n  \"status\": \"active\",\n  \"system\": \"NOVA-APEX Universal Automation\",\n  \"timestamp\": \"2026-10-26\"\n}",
                "params": {}
            })
            step_id += 1
            steps.append({
                "step_id": step_id,
                "title": "Execute System Verification & Capture Desktop State",
                "description": "Capture desktop screen to verify desktop state",
                "domain": "desktop",
                "action_type": "desktop_screenshot",
                "target": "screen",
                "value": "",
                "params": {}
            })

        # Check for mobile intent
        elif any(k in lower for k in ["mobile", "android", "phone", "adb"]):
            steps.append({
                "step_id": step_id,
                "title": "Scan & Connect to Android Device / Emulator",
                "description": "Inspect active ADB devices and establish control pipe",
                "domain": "mobile",
                "action_type": "adb_dump_hierarchy",
                "target": "root",
                "value": "",
                "params": {}
            })
            step_id += 1
            steps.append({
                "step_id": step_id,
                "title": "Capture Mobile Screen State",
                "description": "Take device screenshot and log UI bounds",
                "domain": "mobile",
                "action_type": "adb_screenshot",
                "target": "screen",
                "value": "",
                "params": {}
            })

        # General browsing / searching / execution
        elif any(k in lower for k in ["browse", "search", "web", "internet", "google", "visit"]):
            url = "https://www.google.com"
            if "http" in lower:
                for w in prompt.split():
                    if w.startswith("http"): url = w; break
            steps.append({
                "step_id": step_id,
                "title": f"Navigate to Destination Webpage",
                "description": f"Direct browser to {url}",
                "domain": "browser",
                "action_type": "navigate",
                "target": url,
                "value": url,
                "params": {}
            })
            step_id += 1
            steps.append({
                "step_id": step_id,
                "title": "Extract Page Content & Interactive Elements",
                "description": "Scan DOM accessibility tree and read content",
                "domain": "browser",
                "action_type": "extract_content",
                "target": "body",
                "value": "",
                "params": {}
            })
            step_id += 1
            steps.append({
                "step_id": step_id,
                "title": "Capture Verification Viewport Screenshot",
                "description": "Store high-res snapshot of the active page",
                "domain": "browser",
                "action_type": "browser_screenshot",
                "target": "viewport",
                "value": "",
                "params": {}
            })

        # Default fallback
        else:
            steps.append({
                "step_id": step_id,
                "title": "Plan and Execute High-Level Autonomous Workflow",
                "description": f"Autonomous execution for: {prompt[:80]}",
                "domain": "shell",
                "action_type": "execute_shell",
                "target": "",
                "value": "echo 'NOVA-APEX Universal Engine executing autonomous goal...'",
                "params": {}
            })

        return json.dumps({
            "goal": prompt,
            "steps": steps,
            "explanation": "Autonomous plan synthesized based on requested cross-domain capabilities."
        }, indent=2)

llm = LLMProvider()
