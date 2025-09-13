from flask import Flask, render_template, request, jsonify
import subprocess
import threading
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
import base64
import platform
from dotenv import load_dotenv

load_dotenv()  # take environment variables

app = Flask(__name__)

# Global variables
streaming_process = None
streaming_active = False
preview_driver = None
current_url = ""
stream_key = ""
is_windows = platform.system() == "Windows"

chromerdriver_path = os.getenv('CHROMEDRIVER_PATH',ChromeDriverManager().install())

class WebsiteStreamer:
    def __init__(self):
        self.ffmpeg_process = None
        self.browser_process = None
        self.browser_driver = None
        
    def setup_headless_browser(self, url):
        """Setup headless browser untuk streaming - BENAR-BENAR HEADLESS"""
        try:
            # Setup Chrome options untuk Windows - FULLY HEADLESS
            chrome_options = Options()
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-renderer-backgrounding')
            chrome_options.add_argument('--disable-features=TranslateUI')
            chrome_options.add_argument('--disable-ipc-flooding-protection')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--window-position=-2000,-2000')  # Off-screen
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_argument('--force-device-scale-factor=1')
            chrome_options.add_argument('--run-all-compositor-stages-before-draw')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-plugins')
            chrome_options.add_argument('--disable-default-apps')
            
            # IMPORTANT: Suppress all UI elements
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            
            try:
                self.browser_driver = webdriver.Chrome(service=Service(chromerdriver_path),options=chrome_options)
            except Exception as e:
                print(f"Chrome failed, trying Firefox: {e}")
                # Fallback ke Firefox - JUGA HEADLESS
                firefox_options = FirefoxOptions()
                firefox_options.add_argument('--headless')
                firefox_options.add_argument('--width=1920')
                firefox_options.add_argument('--height=1080')
                firefox_options.add_argument('--display=:99')  # Virtual display
                
                self.browser_driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()),options=firefox_options)
            
            print(f"Loading URL: {url}")
            self.browser_driver.get(url)
            print("Page loaded successfully")
            return True
            
        except Exception as e:
            print(f"Error setting up browser: {e}")
            return False
    
    def start_ffmpeg_stream_windows(self, youtube_key):
        """Start FFmpeg streaming di Windows using desktop capture"""
        try:
            # Windows menggunakan desktop capture
            ffmpeg_cmd = [
                'ffmpeg',
                '-f', 'gdigrab' if os.name == "nt" else "x11grab",
                '-framerate', '30',
                '-i', 'default',
                '-f', 'lavfi', 
                '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-b:v', '2500k',
                '-maxrate', '2500k',
                '-bufsize', '5000k',
                '-pix_fmt', 'yuv420p',
                '-f', 'flv',
                f'rtmp://a.rtmp.youtube.com/live2/{youtube_key}'
            ]
            
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            return True
            
        except Exception as e:
            print(f"Error starting FFmpeg: {e}")
            return False
    
    def start_ffmpeg_stream_window_specific(self, youtube_key, window_title="Google Chrome"):
        """Stream specific browser window"""
        try:
            # Capture specific window (lebih efisien)
            ffmpeg_cmd = [
                'ffmpeg',
                 '-f', 'gdigrab' if os.name == "nt" else "x11grab",
                '-framerate', '30',
                '-i', f'title={window_title}',  # Capture specific window
                '-f', 'lavfi', 
                '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-b:v', '2000k',
                '-maxrate', '2000k',
                '-bufsize', '4000k',
                '-pix_fmt', 'yuv420p',
                '-f', 'flv',
                f'rtmp://a.rtmp.youtube.com/live2/{youtube_key}'
            ]
            
            self.ffmpeg_process = subprocess.Popen(ffmpeg_cmd)
            return True
            
        except Exception as e:
            print(f"Error starting window capture: {e}")
            return False
    
    def stop_streaming(self):
        """Stop all streaming processes"""
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=5)
            except:
                self.ffmpeg_process.kill()
        
        if self.browser_driver:
            try:
                self.browser_driver.quit()
            except:
                pass

streamer = WebsiteStreamer()

def get_website_preview(url):
    """Generate preview screenshot of website"""
    global preview_driver
    
    try:
        if not preview_driver:
            chrome_options = Options()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--force-device-scale-factor=1')
            chrome_options.add_argument("--disable-gpu")
            
            try:
                preview_driver = webdriver.Chrome(service=Service(chromerdriver_path),options=chrome_options)
            except Exception as e:
                print(f"Chrome preview failed: {e}")
                # Fallback ke Firefox
                firefox_options = FirefoxOptions()
                firefox_options.add_argument('--headless')
                firefox_options.add_argument('--width=1920')
                firefox_options.add_argument('--height=1080')
                preview_driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()),options=firefox_options)
        
        preview_driver.get(url)
        time.sleep(3)  # Wait for page load
        
        # Take screenshot
        screenshot = preview_driver.get_screenshot_as_png()
        
        # Convert to base64 for web display
        screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
        return screenshot_b64
        
    except Exception as e:
        print(f"Error generating preview: {e}")
        return None

def check_ffmpeg():
    """Check if FFmpeg is available"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except:
        return False

@app.route('/')
def index():
    ffmpeg_available = check_ffmpeg()
    return render_template('index.html', ffmpeg_available=ffmpeg_available, is_windows=is_windows)

@app.route('/preview', methods=['POST'])
def preview_website():
    global current_url
    
    data = request.json
    url = data.get('url', '')
    current_url = url
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    screenshot_b64 = get_website_preview(url)
    
    if screenshot_b64:
        return jsonify({
            'success': True, 
            'screenshot': f'data:image/png;base64,{screenshot_b64}',
            'url': url
        })
    else:
        return jsonify({'success': False, 'error': 'Failed to generate preview'})

@app.route('/start_stream', methods=['POST'])
def start_stream():
    global streaming_active, current_url, stream_key
    
    if streaming_active:
        return jsonify({'success': False, 'error': 'Stream already active'})
    
    if not check_ffmpeg():
        return jsonify({'success': False, 'error': 'FFmpeg not found. Please install FFmpeg first.'})
    
    data = request.json
    stream_key = data.get('stream_key', '')
    capture_mode = data.get('capture_mode', 'desktop')  # 'desktop' or 'window'
    
    if not stream_key or not current_url:
        return jsonify({'success': False, 'error': 'Missing stream key or URL'})
    
    # Start streaming in background thread
    def start_streaming():
        global streaming_active
        streaming_active = True
        
        # Setup browser OTOMATIS dengan URL yang sudah di-preview
        print(f"🔄 Setting up headless browser for: {current_url}")
        if streamer.setup_headless_browser(current_url):
            print("✅ Headless browser ready")
            time.sleep(3)  # Wait for page to fully load
            
            if capture_mode == 'window':
                if streamer.start_ffmpeg_stream_window_specific(stream_key):
                    print("✅ Window capture streaming started")
                else:
                    streaming_active = False
                    print("❌ Failed to start window capture")
            else:
                # Desktop capture mode - browser sudah buka di background
                print("✅ Browser loaded in headless mode, starting desktop capture...")
                if streamer.start_ffmpeg_stream_windows(stream_key):
                    print("✅ Desktop capture streaming started")
                else:
                    streaming_active = False
                    print("❌ Failed to start desktop capture")
        else:
            streaming_active = False
            print("❌ Failed to setup headless browser")
    
    streaming_thread = threading.Thread(target=start_streaming)
    streaming_thread.daemon = True
    streaming_thread.start()
    
    time.sleep(2)  # Give it time to start
    
    if streaming_active:
        return jsonify({'success': True, 'message': 'Streaming started'})
    else:
        return jsonify({'success': False, 'error': 'Failed to start streaming'})

@app.route('/stop_stream', methods=['POST'])
def stop_stream():
    global streaming_active
    
    if not streaming_active:
        return jsonify({'success': False, 'error': 'No active stream'})
    
    streamer.stop_streaming()
    streaming_active = False
    
    return jsonify({'success': True, 'message': 'Streaming stopped'})

@app.route('/status')
def get_status():
    return jsonify({
        'streaming': streaming_active,
        'current_url': current_url,
        'has_stream_key': bool(stream_key),
        'ffmpeg_available': check_ffmpeg(),
        'platform': platform.system()
    })

@app.route('/logs')
def get_logs():
    """Get FFmpeg logs for monitoring"""
    if streamer.ffmpeg_process and streaming_active:
        try:
            # Read the stderr where FFmpeg outputs its logs
            stderr_output = streamer.ffmpeg_process.stderr
            if stderr_output:
                # Read up to 4KB of logs to avoid overwhelming response
                logs = stderr_output.read1(4096).decode('utf-8', errors='replace')
                return jsonify({'logs': logs})
            return jsonify({'logs': 'Waiting for FFmpeg output...'})
        except Exception as e:
            return jsonify({'logs': f'Error reading logs: {str(e)}'})
    else:
        return jsonify({'logs': 'FFmpeg not running'})

@app.route('/test_browser')
def test_browser():
    """Test endpoint untuk cek browser"""
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        driver = webdriver.Chrome(options=chrome_options)
        driver.get('https://www.google.com')
        title = driver.title
        driver.quit()
        return jsonify({'success': True, 'message': f'Browser test successful. Title: {title}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("🚀 Starting Website Streaming Server (Windows Version)...")
    print(f"🖥️  Platform: {platform.system()}")
    print(f"📡 Access web interface at: http://localhost:5000")
    
    # Check dependencies
    if not check_ffmpeg():
        print("⚠️  Warning: FFmpeg not found. Streaming will not work.")
        print("   Download FFmpeg from: https://ffmpeg.org/download.html")
    
    # try:
    #     webdriver.Chrome(options=Options())
    #     print("✅ Chrome WebDriver available")
    # except:
    #     print("⚠️  Warning: Chrome WebDriver not found")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    finally:
        # Cleanup on exit
        if preview_driver:
            preview_driver.quit()
        if streaming_active:
            streamer.stop_streaming()