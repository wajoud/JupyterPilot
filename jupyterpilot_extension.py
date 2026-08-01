import json
import os
import sys

import requests
from IPython.core.magic import Magics, line_magic, magics_class


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
            "local": {
                "url": "http://localhost:11434/api/generate",
                "model": "qwen2.5-coder:7b",
            },
            "cloud": {"model": "gpt-4o", "provider": "openai"},
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
                timeout=15,
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

            # Setup environment for litellm
            if "api_key" in cloud_cfg:
                provider = cloud_cfg.get("provider", "openai").upper()
                os.environ[f"{provider}_API_KEY"] = cloud_cfg["api_key"]

            response = litellm.completion(
                model=model, messages=[{"role": "user", "content": prompt}]
            )
            text = response.choices[0].message.content.strip()
            return self._clean_code(text)
        except Exception as e:
            return f"# Cloud Inference Error: {e}"

    def _clean_code(self, text):
        if "```" in text:
            lines = text.splitlines()
            code_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    code_lines.append(line)
            return "\n".join(code_lines).strip() if code_lines else text.strip()
        return text.strip()


@magics_class
class JupyterPilotMagics(Magics):
    def __init__(self, shell):
        super().__init__(shell)
        self.provider = LLMProvider()

    def _get_context(self):
        # Retrieve last 3 input cells
        history = self.shell.history_manager.input_hist_raw
        # Exclude current line and empty ones
        valid = [
            h.strip()
            for h in history
            if h.strip() and not h.startswith(("%do", "%fix"))
        ]
        return "\n# --- Previous Cell ---\n".join(valid[-3:])

    @line_magic
    def do(self, line):
        """%do <prompt> - Generate code from natural language."""
        if not line:
            print("Please provide a prompt. Example: %do create a plot")
            return
        context = self._get_context()
        code = self.provider.generate(line, context)
        self.shell.set_next_input(code)

    @line_magic
    def fix(self, line):
        """%fix - Analyze and fix the last error."""
        import traceback

        # Access the last exception from IPython
        if not hasattr(sys, "last_traceback"):
            print("No recent error found in sys.last_traceback.")
            return

        etype, evalue, tb = sys.last_type, sys.last_value, sys.last_traceback
        err_msg = "".join(traceback.format_exception(etype, evalue, tb))

        # Get the cell that caused the error
        last_cell = self.shell.history_manager.input_hist_raw[-1]
        context = self._get_context()

        prompt = f"The following code failed with an error. Please fix it.\n\nCode:\n{last_cell}\n\nError:\n{err_msg}"
        fixed_code = self.provider.generate(prompt, context)
        self.shell.set_next_input(fixed_code)


# Register magics if in IPython environment
try:
    ip = get_ipython()
    if ip:
        ip.register_magics(JupyterPilotMagics(ip))
except NameError:
    pass
