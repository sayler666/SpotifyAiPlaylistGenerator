from typing import Optional
import json
from rich.console import Console
from rich.panel import Panel
from anthropic import Client as AnthropicClient
from .protocols import AIProvider, PlaylistData
from .prompt_builder import PlaylistPromptBuilder
from .response_parser import PlaylistJSONParser

console = Console()

class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str) -> None:
        self.client = AnthropicClient(api_key=api_key)
        self.api_key = api_key
        self._available_models = [
            "claude-3-haiku-20240307",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
        ]
        self._model = self._available_models[0]
        self.prompt_builder = PlaylistPromptBuilder()
        self.response_parser = PlaylistJSONParser()
    
    def get_name(self) -> str:
        return "Claude"
    
    def get_model(self) -> str:
        return self._model
    
    def set_model(self, model: str) -> None:
        if model not in self._available_models:
            raise ValueError(f"Invalid model. Available models: {self._available_models}")
        self._model = model
    
    def get_available_models(self) -> list[str]:
        return self._available_models.copy()
    
    def generate_playlist(self, prompt: str) -> Optional[PlaylistData]:
        try:
            # type: ignore
            message = self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": self.prompt_builder.build_prompt(prompt)
                    }
                ]
            )
            
            response_text = message.content  # type: ignore
            # Handle different response formats
            if isinstance(response_text, list):
                response_text = response_text[0].text.strip()  # type: ignore
            elif hasattr(message, 'text'):
                response_text = message.text.strip()  # type: ignore
            elif isinstance(response_text, str):
                response_text = response_text.strip()
            else:
                console.print("[yellow]Warning: Unexpected response format from Claude API")
                response_text = str(message)

            return json.loads(response_text)

        except Exception as e:
            console.print(Panel(e, title=f"[red]Claude API[/red]", border_style="red"))
            return None