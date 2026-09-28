import base64
import os
import time
from playwright.sync_api import sync_playwright

def record_demo():
    os.makedirs("demo_recording", exist_ok=True)
    
    # Load lo-fi track audio bytes
    audio_b64 = ""
    if os.path.exists("lofi_track.wav"):
        with open("lofi_track.wav", "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir="demo_recording/",
            record_video_size={"width": 1280, "height": 800}
        )
        page = context.new_page()

        print("Navigating to http://localhost:8080...")
        page.goto("http://localhost:8080")
        page.wait_for_selector("header")

        # Inject and play upbeat lo-fi background music track
        if audio_b64:
            print("Playing upbeat lo-fi background music in browser context...")
            page.evaluate("""(b64Data) => {
                try {
                    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    const binary = atob(b64Data);
                    const bytes = new Uint8Array(binary.length);
                    for (let i = 0; i < binary.length; i++) {
                        bytes[i] = binary.charCodeAt(i);
                    }
                    audioCtx.decodeAudioData(bytes.buffer, (buffer) => {
                        const source = audioCtx.createBufferSource();
                        source.buffer = buffer;
                        source.loop = true;
                        
                        // Set comfortable background volume
                        const gainNode = audioCtx.createGain();
                        gainNode.gain.value = 0.35;
                        source.connect(gainNode);
                        gainNode.connect(audioCtx.destination);

                        source.start(0);
                    });
                } catch(e) {
                    console.error('Audio playback error:', e);
                }
            }""", audio_b64)

        time.sleep(2)

        # Demo Step 1: Click Beach Destinations prompt chip
        print("Executing Prompt 1: Beach Destinations...")
        chips = page.query_selector_all(".prompt-chip")
        if chips:
            chips[0].click()
        else:
            page.fill("#input", "Recommend top destinations for a coastal beach trip")
            page.click("button[type='submit']")

        # Wait for agent response
        print("Waiting for agent response to Prompt 1...")
        time.sleep(8)

        # Demo Step 2: Richer prompt showing tool calls & budget calculation
        print("Executing Prompt 2: Richer prompt (Budget calculation & Weather lookup)...")
        page.fill("#input", "Calculate a 5-day budget for 2 people visiting Kyoto and check the current weather in Kyoto")
        time.sleep(1)
        page.click("button[type='submit']")

        # Wait for agent response
        print("Waiting for agent response to Prompt 2...")
        time.sleep(12)

        print("Closing browser context to finalize demo video recording...")
        context.close()
        browser.close()
        print("Demo video recording with lo-fi background music complete!")

if __name__ == "__main__":
    record_demo()
