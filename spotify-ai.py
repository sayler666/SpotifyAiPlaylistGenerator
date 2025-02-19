import click
import json
import os
from pathlib import Path
from spotipy.oauth2 import SpotifyOAuth
import spotipy
from rich.console import Console
from rich.progress import Progress
from rich import print as rprint
from rich.panel import Panel
from rich.traceback import install
import configparser
import sys
import anthropic
import asyncio
import locale
import codecs
from datetime import datetime
import traceback

# Enable detailed tracebacks
install(show_locals=True)

# Set encoding for Windows
if sys.platform.startswith('win'):
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

# Initialize console with encoding support
console = Console(force_terminal=True)

# Configure paths
SCRIPT_DIR = Path(__file__).parent.absolute()
CONFIG_DIR = SCRIPT_DIR / 'config'
CONFIG_FILE = CONFIG_DIR / 'config.ini'
LOG_DIR = CONFIG_DIR / 'logs'
ERROR_LOG_FILE = LOG_DIR / f'errors_{datetime.now().strftime("%Y%m%d")}.log'

def setup_logging():
    """Configure logging system."""
    if not LOG_DIR.exists():
        LOG_DIR.mkdir(parents=True)

def log_error(error_type: str, error: Exception, api_response=None):
    """Log error to file and display it in console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_message = f"""
=== {timestamp} ===
Type: {error_type}
Error: {str(error)}
Traceback:
{traceback.format_exc()}
"""
    if api_response:
        error_message += f"\nAPI Response:\n{json.dumps(api_response, indent=2, ensure_ascii=False)}\n"
    
    # Write to file
    with open(ERROR_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(error_message + "\n")
    
    # Display in console
    console.print(Panel(error_message, title=f"[red]Error {error_type}[/red]", border_style="red"))

def ensure_config_exists():
    """Check and create configuration if it doesn't exist."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True)
    
    if not CONFIG_FILE.exists():
        config = configparser.ConfigParser()
        config['spotify'] = {
            'client_id': '',
            'client_secret': '',
            'redirect_uri': 'http://localhost:8888/callback'
        }
        config['anthropic'] = {
            'api_key': ''
        }
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            config.write(f)
        
        console.print("[red]Configuration requires setup. Open file: " + str(CONFIG_FILE))
        sys.exit(1)

def load_config():
    """Load configuration."""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding='utf-8')
    return config

async def get_ai_response(prompt, config):
    """Get response from Claude."""
    try:
        client = anthropic.Client(api_key=config['api_key'])
        # type: ignore
        message = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"Create a playlist based on this description, at least 15 songs, unless specified otherwise: {prompt}. Respond ONLY in JSON format, without any additional text before or after. Format: {{\"playlist_name\": \"name\", \"description\": \"description\", \"tracks\": [{{\"artist\": \"artist\", \"title\": \"title\"}}]}}"
                }
            ]
        )
        
        try:
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
        except json.JSONDecodeError as je:
            log_error("Claude JSON Parse", je, response_text)
            return None
        except AttributeError as ae:
            log_error("Claude Response Format", ae, {"message": str(message), "content": str(message.content)})
            return None
    except Exception as e:
        log_error("Claude API", e, message if 'message' in locals() else None)
        return None

class SpotifyAIPlaylist:
    def __init__(self, config):
        """Initialize Spotify client."""
        try:
            self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=config['client_id'],
                client_secret=config['client_secret'],
                redirect_uri=config['redirect_uri'],
                scope="playlist-modify-public playlist-modify-private"
            ))
            
            # Get current user with validation
            current_user = self.sp.current_user()
            if current_user is None:
                raise Exception("Failed to get current user information")
                
            self.user_id = current_user.get("id")
            if not self.user_id:
                raise Exception("User ID not found in response")
                
        except Exception as e:
            log_error("Spotify Authentication", e)
            raise

    def create_playlist(self, name, description="", public=True):
        """Create a new playlist."""
        try:
            return self.sp.user_playlist_create(
                user=self.user_id,
                name=name,
                public=public,
                description=description
            )
        except Exception as e:
            log_error("Spotify Create Playlist", e)
            return None

    def search_track(self, artist, title):
        """Search for a track."""
        try:
            query = f"artist:{artist} track:{title}"
            results = self.sp.search(q=query, limit=1, type="track")
            
            # Validate results structure
            if not results:
                return None
                
            tracks = results.get("tracks")
            if not tracks:
                return None
                
            items = tracks.get("items")
            if not items or len(items) == 0:
                return None
                
            return items[0]
            
        except Exception as e:
            log_error("Spotify Search Track", e, {"query": query} if 'query' in locals() else None)
            return None

    def add_tracks_to_playlist(self, playlist_id, track_ids):
        """Add tracks to playlist."""
        try:
            if track_ids:
                self.sp.playlist_add_items(playlist_id, track_ids)
                return True
            return False
        except Exception as e:
            log_error("Spotify Add Tracks", e, {
                "playlist_id": playlist_id,
                "track_ids": track_ids
            })
            return False

@click.group()
def cli():
    """Tool for creating Spotify playlists using Claude AI."""
    pass

@cli.command()
@click.option('--config', is_flag=True, help='Open configuration file.')
def configure(config):
    """Configure the tool."""
    ensure_config_exists()
    if config:
        click.edit(filename=str(CONFIG_FILE))
    else:
        console.print(f"[green]Configuration file is located at: {CONFIG_FILE}")
        console.print(f"[yellow]Error logs are located at: {LOG_DIR}")

@cli.command()
@click.argument('prompt')
@click.option('--private', is_flag=True, help='Create a private playlist.')
@click.option('--debug', is_flag=True, help='Display detailed debug information.')
def create(prompt, private, debug):
    """Create a playlist based on the provided description."""
    setup_logging()
    ensure_config_exists()
    config = load_config()
    
    with console.status("[bold green]Generating playlist...") as status:
        try:
            # Get suggestions from Claude
            response = asyncio.run(get_ai_response(prompt, config['anthropic']))
            if not response:
                return

            if debug:
                console.print("\n[cyan]Claude Response:[/cyan]")
                console.print(json.dumps(response, indent=2, ensure_ascii=False))

            # Initialize Spotify client
            spotify = SpotifyAIPlaylist(config["spotify"])
            
            # Create playlist
            playlist = spotify.create_playlist(
                name=response["playlist_name"],
                description=response["description"],
                public=not private
            )

            if not playlist:
                console.print("[red]Failed to create playlist.")
                return

            track_ids = []
            not_found = []

            # Search and add tracks
            with Progress() as progress:
                task = progress.add_task("[cyan]Searching for tracks...", total=len(response["tracks"]))
                
                for track in response["tracks"]:
                    result = spotify.search_track(track["artist"], track["title"])
                    if result:
                        track_ids.append(result["id"])
                        rprint(f"[green]✓[/green] Found: {track['artist']} - {track['title']}")
                        if debug:
                            rprint(f"   [dim]Track ID: {result['id']}[/dim]")
                    else:
                        not_found.append(f"{track['artist']} - {track['title']}")
                        rprint(f"[red]✗[/red] Not found: {track['artist']} - {track['title']}")
                    progress.advance(task)

            # Add tracks to playlist
            if track_ids:
                success = spotify.add_tracks_to_playlist(playlist["id"], track_ids)
                if success:
                    spotify_url = playlist['external_urls']['spotify']
                    # Convert https://open.spotify.com/playlist/XXX to spotify:playlist:XXX
                    spotify_uri = 'spotify:' + spotify_url.split('spotify.com/')[1].replace('/', ':')
                    try:
                        if sys.platform.startswith('win'):
                            os.startfile(spotify_uri)
                        elif sys.platform.startswith('darwin'):  # for macOS
                            os.system(f'open {spotify_uri}')
                        elif sys.platform.startswith('linux'):  # for Linux
                            os.system(f'xdg-open {spotify_uri}')
                        console.print(f"\n[green]Created playlist and opened in Spotify!")
                        console.print(f"[dim]Browser URL: {spotify_url}")
                        console.print(f"[dim]Spotify URI: {spotify_uri}")
                    except Exception as e:
                        console.print(f"\n[green]Created playlist: {spotify_url}")
                        log_error("Open Spotify", e)
                else:
                    console.print("[red]Error adding tracks to playlist.")
                
                if not_found:
                    console.print("\n[yellow]The following tracks were not found:")
                    for track in not_found:
                        console.print(f"[yellow]- {track}")
            else:
                console.print("[red]No tracks were found. Playlist was not created.")

        except Exception as e:
            log_error("General", e)
            console.print("[red]An unexpected error occurred. Check logs in the logs directory.[/red]")

if __name__ == '__main__':
    cli()