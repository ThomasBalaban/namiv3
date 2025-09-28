import sys
import threading
import os
import subprocess
import time
import requests
import json
import re
import atexit
from nami.bot_core import ask_question, BOTNAME
from nami.audio_utils.hearing_system import start_hearing_system, stop_hearing_system
from nami.vision_client import start_vision_client
from nami.twitch_integration import init_twitch_bot, send_to_twitch_sync
from nami.input_systems import (
    init_priority_system,
    shutdown_priority_system,
    process_console_command,
    process_hearing_line,
)
from nami.ui import start_ui_server, emit_log, emit_bot_reply
from nami.vision_process_manager import start_vision_process, stop_vision_process
from nami.tts_utils.content_filter import process_response_for_content

# Import security config
from nami.config import (
    NGROK_AUTH_ENABLED, 
    NGROK_AUTH_USERNAME, 
    NGROK_AUTH_PASSWORD,
    NGROK_BIND_TLS,
    NGROK_INSPECT,
    SECURITY_NOTIFICATIONS
)

# --- UI Log Redirection ---
_is_logging = threading.local()

class LogRedirector:
    """Redirects stdout/stderr to the UI log panel."""
    def __init__(self, original_stream, level):
        self.original_stream = original_stream
        self.level = level

    def write(self, message):
        # Prevent recursion if a print is called within the logging system itself
        if getattr(_is_logging, 'active', False):
            self.original_stream.write(message)
            return

        try:
            _is_logging.active = True
            self.original_stream.write(message)
            # Only emit non-empty messages to the UI to avoid clutter
            if message.strip():
                emit_log(self.level, message.strip())
        finally:
            # Ensure the flag is always reset
            _is_logging.active = False

    def flush(self):
        self.original_stream.flush()

# Import the input funnel
try:
    from nami.input_funnel.input_funnel import InputFunnel
    input_funnel_available = True
except ImportError:
    input_funnel_available = False
    print("InputFunnel module not found, will use traditional priority system")

# --- MODIFIED: Import TTS components separately ---
try:
    from nami.tts_utils.tts_engine import text_to_speech_file
    from nami.tts_utils.audio_player import play_audio_file
    tts_available = True
except ImportError:
    tts_available = False
    text_to_speech_file = None
    play_audio_file = None

# Global references for clean shutdown
global_input_funnel = None
ngrok_process = None

# --- SECURE NGROK FUNCTIONS ---
def start_ngrok_tunnel():
    """Start ngrok tunnel with security features from config.py"""
    global ngrok_process
    
    if SECURITY_NOTIFICATIONS:
        print("🔒 Starting secure ngrok tunnel for sound effects...")
        if NGROK_AUTH_ENABLED:
            print(f"🔐 Authentication enabled for user: {NGROK_AUTH_USERNAME}")
        if NGROK_BIND_TLS:
            print("🛡️ HTTPS-only mode enabled")
        if not NGROK_INSPECT:
            print("🔍 Web inspection interface disabled for privacy")
    
    try:
        # Build ngrok command with security options
        cmd = ["ngrok", "http", "8002"]
        
        # Add authentication if enabled in config
        if NGROK_AUTH_ENABLED and NGROK_AUTH_USERNAME and NGROK_AUTH_PASSWORD:
            auth_string = f"{NGROK_AUTH_USERNAME}:{NGROK_AUTH_PASSWORD}"
            cmd.extend(["-auth", auth_string])
            
        # Force HTTPS if enabled in config
        if NGROK_BIND_TLS:
            cmd.append("-bind-tls=true")
            
        # Disable inspection if configured
        if not NGROK_INSPECT:
            cmd.append("-inspect=false")
            
        # Add logging
        cmd.extend(["--log=stdout"])
        
        if SECURITY_NOTIFICATIONS:
            print(f"🚀 Running ngrok with security options from config.py")
        
        # Start ngrok in background
        ngrok_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait a moment for ngrok to start
        time.sleep(3)
        
        # Get the public URL from ngrok's API
        response = requests.get("http://localhost:4040/api/tunnels", timeout=5)
        tunnels = response.json()
        
        if tunnels.get("tunnels"):
            tunnel_info = tunnels["tunnels"][0]
            public_url = tunnel_info["public_url"]
            
            # Security logging
            if SECURITY_NOTIFICATIONS:
                print(f"✅ Secure tunnel active: {public_url}")
                if NGROK_AUTH_ENABLED:
                    print(f"🔐 Protected with username: {NGROK_AUTH_USERNAME}")
                    print(f"🔑 Password from config: {NGROK_AUTH_PASSWORD}")
                    print("   To change password: update NGROK_AUTH_PASSWORD in config.py and restart")
                
                # Check if HTTPS
                if public_url.startswith("https://"):
                    print("🔒 Tunnel is using HTTPS encryption")
                else:
                    print("⚠️ Warning: Tunnel is using HTTP (not encrypted)")
                    
            return public_url
        else:
            print("❌ No ngrok tunnels found")
            return None
            
    except subprocess.CalledProcessError:
        print("❌ Failed to start ngrok - make sure it's installed (brew install ngrok)")
        return None
    except requests.exceptions.RequestException:
        print("❌ ngrok started but API not accessible")
        return None
    except Exception as e:
        print(f"❌ Error starting secure ngrok: {e}")
        return None

def stop_ngrok():
    """Stop the ngrok process"""
    global ngrok_process
    if ngrok_process:
        if SECURITY_NOTIFICATIONS:
            print("🔒 Stopping secure ngrok tunnel...")
        ngrok_process.terminate()
        try:
            ngrok_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ngrok_process.kill()
        ngrok_process = None

def check_tunnel_security():
    """Check and display current security status"""
    try:
        response = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        tunnels = response.json()
        
        if not tunnels.get("tunnels"):
            if SECURITY_NOTIFICATIONS:
                print("ℹ️ No active tunnels to check")
            return False
            
        tunnel = tunnels["tunnels"][0]
        url = tunnel["public_url"]
        
        if SECURITY_NOTIFICATIONS:
            print(f"\n🔍 Security Status:")
            print(f"   Tunnel URL: {url}")
            print(f"   HTTPS: {'✅' if url.startswith('https') else '❌'}")
            print(f"   Auth: {'✅' if NGROK_AUTH_ENABLED else '❌'}")
            print(f"   Inspection: {'🔒 Disabled' if not NGROK_INSPECT else '⚠️ Enabled'}")
            
            if NGROK_AUTH_ENABLED:
                print(f"   Username: {NGROK_AUTH_USERNAME}")
                print(f"   Password: {NGROK_AUTH_PASSWORD}")
                print("   💡 Change password in config.py anytime")
            
        return True
        
    except Exception as e:
        if SECURITY_NOTIFICATIONS:
            print(f"❌ Error checking tunnel security: {e}")
        return False

def hearing_line_processor(line_str):
    """Processes a single line of text from the hearing system."""
    if ("[Microphone Input]" in line_str or
        ("]" in line_str and any(x in line_str for x in ["SPEECH", "MUSIC"]))):

        if "[Microphone Input]" in line_str:
            formatted = line_str.replace("[Microphone Input]", "[HEARING] 🎤")
        else:
            formatted = line_str.replace("[", "[HEARING] 🔊 [", 1)

        print(f"\n{formatted}")
        print("You: ", end="", flush=True)
        process_hearing_line(line_str)
    elif any(x in line_str for x in ["Loading", "Starting", "Initializing", "Error", "Vosk"]):
        print(f"[Hearing] {line_str}")


class FunnelResponseHandler:
    """Handler for funnel responses (including TTS, UI updates, and content filtering)"""
    def __init__(self, generation_func=None, playback_func=None):
        self.generation_func = generation_func
        self.playback_func = playback_func

    def handle_response(self, response, prompt_details, source_info):
        if not response:
            print("Empty response received")
            return

        # --- NEW: Process response through content filter ---
        print(f"[FILTER DEBUG] Original response: {response}")
        filtered_content = process_response_for_content(response)
        
        # Extract the different versions
        tts_version = filtered_content['tts_version']
        twitch_version = filtered_content['twitch_version'] 
        ui_version = filtered_content['ui_version']
        is_censored = filtered_content['is_censored']

        print(f"[FILTER DEBUG] TTS version: {tts_version}")
        print(f"[FILTER DEBUG] Twitch version: {twitch_version}")
        print(f"[FILTER DEBUG] UI version: {ui_version}")
        print(f"[FILTER DEBUG] Is censored: {is_censored}")

        # Log what we're using
        if is_censored:
            print(f"\n[BOT - CENSORED] Original: {response[:50]}...")
            print(f"[BOT - CENSORED] Sending: {tts_version}")
        else:
            print(f"\n[BOT] {tts_version}")
        
        print("You: ", end="", flush=True)

        # --- MODIFIED: Emit to UI with censorship flag ---
        emit_bot_reply(ui_version, prompt_details, is_censored=is_censored)

        # --- MODIFIED: Send filtered version to Twitch ---
        try:
            source = source_info.get('source')
            if source in ['TWITCH_MENTION', 'DIRECT_MICROPHONE']:
                username = source_info.get('username')
                # Format as a reply if it's from a specific user in chat
                if source == 'TWITCH_MENTION' and username:
                    twitch_response = f"@{username} {twitch_version}"
                else:
                    # Otherwise, send the raw response
                    twitch_response = twitch_version
                
                print(f"[FILTER DEBUG] Final Twitch message: {twitch_response}")
                
                # This will automatically handle sound effects and censorship
                send_to_twitch_sync(twitch_response)
        except Exception as e:
            print(f"[TWITCH] Error sending response: {e}")

        # --- MODIFIED: TTS uses filtered version ---
        if self.generation_func and self.playback_func and source_info.get('use_tts', False):
            try:
                # Step 1: Generate the audio file from the TTS version (censored if needed)
                audio_filename = self.generation_func(tts_version)

                if audio_filename:
                    # Step 2: Play the generated file in a non-blocking background thread
                    playback_thread = threading.Thread(
                        target=self.playback_func,
                        args=(audio_filename,),
                        daemon=True
                    )
                    playback_thread.start()
            except Exception as e:
                print(f"[TTS] Error processing TTS: {e}")


def console_input_loop():
    """Run the console input loop with command handling"""
    print(f"{BOTNAME} is ready. Start chatting!")
    while True:
        try:
            command = input("You: ")
            if process_console_command(command):
                break
        except Exception as e:
            print(f"Error in console loop: {e}")
            break


def main():
    """Start the bot with integrated priority system and secure ngrok."""
    global global_input_funnel

    start_vision_process() # Start the vision process
    start_ui_server()
    
    # Give UI server time to start before starting ngrok
    time.sleep(2)
    
    # --- SECURE NGROK WITH CONFIG VALUES ---
    if tts_available:
        ngrok_url = start_ngrok_tunnel()
        if ngrok_url:
            # Show security status
            check_tunnel_security()
            
            # Register cleanup function
            atexit.register(stop_ngrok)
            
            if SECURITY_NOTIFICATIONS:
                print(f"\n🎉 Secure audio server is ready!")
                print(f"🌐 External URL: {ngrok_url}")
                if NGROK_AUTH_ENABLED:
                    print(f"🔐 Authentication required:")
                    print(f"   Username: {NGROK_AUTH_USERNAME}")
                    print(f"   Password: {NGROK_AUTH_PASSWORD}")
                    print(f"   💡 To change password: edit NGROK_AUTH_PASSWORD in config.py and restart")
                else:
                    print("⚠️ No authentication enabled - tunnel is public!")
        else:
            print("⚠️ Sound effects will use fallback text (ngrok not available)")
    
    sys.stdout = LogRedirector(sys.stdout, 'INFO')
    sys.stderr = LogRedirector(sys.stderr, 'ERROR')

    use_funnel = input_funnel_available
    input_funnel = None
    funnel_response_handler = None

    if use_funnel:
        print("Initializing input funnel...")
        funnel_response_handler = FunnelResponseHandler(
            generation_func=text_to_speech_file if tts_available else None,
            playback_func=play_audio_file if tts_available else None
        )
        input_funnel = InputFunnel(
            bot_callback=ask_question,
            response_handler=funnel_response_handler.handle_response,
            min_prompt_interval=2
        )
        global_input_funnel = input_funnel

    init_priority_system(
        llm_callback=ask_question,
        bot_name=BOTNAME,
        enable_bot_core=True,
        funnel_instance=input_funnel if use_funnel else None
    )

    if use_funnel:
        from nami.input_systems.input_handlers import set_input_funnel
        set_input_funnel(input_funnel)
        print("NOTICE: Desktop audio and vision inputs are now context-only by default")

    start_hearing_system(callback=hearing_line_processor)
    start_vision_client()
    init_twitch_bot(funnel=input_funnel)

    print("System initialization complete, ready for input")

    try:
        console_input_loop()
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down gracefully...")
    finally:
        print("Cleaning up resources...")
        if global_input_funnel:
            global_input_funnel.stop()
        stop_hearing_system()
        shutdown_priority_system()
        stop_vision_process() # Stop the vision process
        stop_ngrok() # Stop secure ngrok tunnel
        print("Shutdown complete.")


if __name__ == "__main__":
    main()