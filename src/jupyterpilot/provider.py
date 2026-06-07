import json
import os
import requests

class LLMProvider:
    """Provider-agnostic LLM Engine for JupyterPilot."""
    def __init__(self, config_path="/etc/jupyterpilot/config.json"):
        self.config_path = config_path
        self.load_config()

    def load_config(self):
        # Priority: 1. User-specific config, 2. Global config, 3. Default fallback
        user_config = os.path.expanduser("~/.jupyterpilot/config.json")
        global_config = "/etc/jupyterpilot/config.json"
        
        path = None
        if os.path.exists(user_config):
            path = user_config
        elif os.path.exists(global_config):
            path = global_config
        
        if path:
            try:
                with open(path, "r") as f:
                    self.config = json.load(f)
                    self.config_path = path
                    return
            except Exception as e:
                print(f"# Warning: Failed to load config from {path}: {e}")

        # Default fallback settings
        self.config = {
            "mode": "local",
            "local": {"url": "http://localhost:11434/api/generate", "model": "qwen2.5-coder:7b"},
            "cloud": {"model": "gpt-4o", "provider": "openai"}
        }

    def generate(self, prompt, context=""):
        system_prompt = "You are JupyterPilot, a high-performance coding assistant. Return ONLY executable Python code. No markdown, no explanations."
        full_prompt = f"{system_prompt}\n\nContext from previous cells:\n{context}\n\nTask: {prompt}"
        
        if self.config.get("mode") == "local":
            return self._generate_local(full_prompt)
        else:
            return self._generate_cloud(full_prompt)

    def _generate_local(self, prompt):
        local_cfg = self.config.get("local", {})
        url = local_cfg.get("url", "http://localhost:11434/api/generate")
        model = local_cfg.get("model", "qwen2.5-coder:7b")
        try:
            response = requests.post(
                url,
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=15
            )
            text = response.json().get("response", "").strip()
            return self._clean_code(text)
        except Exception as e:
            return f"# Local Inference Error: {e}"

    def _generate_cloud(self, prompt):
        try:
            import litellm
            cloud_cfg = self.config.get("cloud", {})
            model = cloud_cfg.get("model", "gpt-4o")
            
            if "api_key" in cloud_cfg:
                provider = cloud_cfg.get("provider", "openai").upper()
                os.environ[f"{provider}_API_KEY"] = cloud_cfg["api_key"]
            
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.choices[0].message.content.strip()
            return self._clean_code(text)
        except Exception as e:
            return f"# Cloud Inference Error: {e}"

    def _clean_code(self, text):
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                if part.strip().startswith(("python", "py")):
                    return "\n".join(part.strip().splitlines()[1:]).strip()
                if len(part.strip()) > 5:
                    return part.strip()
        return text.strip()
