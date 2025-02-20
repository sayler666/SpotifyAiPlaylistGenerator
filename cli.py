import click
from config import setup_directories, load_config, CONFIG_FILE
from spotify_client import SpotifyClient
from ai_providers import AIProviderFactory
from playlist_generator import PlaylistGenerator
from rich.console import Console
from typing import Optional

console = Console(force_terminal=True)

@click.group()
def cli():
    """Tool for creating Spotify playlists using AI."""
    pass

@cli.command()
@click.option('--config', is_flag=True, help='Open configuration file.')
def configure(config):
    """Configure the tool."""
    setup_directories()
    if config:
        click.edit(filename=str(CONFIG_FILE))
    else:
        console.print(f"[green]Configuration file is located at: {CONFIG_FILE}")

@cli.command()
@click.argument('prompt')
@click.option('--private', is_flag=True, help='Create a private playlist.')
@click.option('--debug', is_flag=True, help='Display detailed debug information.')
@click.option('--ai-provider', help='Override AI provider (anthropic)')
@click.option('--model', help='Override AI model')
def create(prompt: str, private: bool, debug: bool, ai_provider: Optional[str], model: Optional[str]):
    """Create a playlist based on the provided description."""
    setup_directories()
    config = load_config()
    
    # Get AI provider from config or command line
    provider_type = ai_provider or config['ai']['provider']
    api_key = config['ai']['api_key']
    
    try:
        ai_provider = AIProviderFactory.create_provider(provider_type, api_key)
        if model:
            ai_provider.set_model(model)
        elif config['ai']['model']:
            ai_provider.set_model(config['ai']['model'])
            
        spotify_client = SpotifyClient(config['spotify'])
        generator = PlaylistGenerator(spotify_client, ai_provider)

        generator.generate(prompt, private, debug)
        
    except Exception as e:
        console.print(f"[red]Error: {str(e)}")
        if debug:
            console.print_exception()

if __name__ == '__main__':
    cli()
