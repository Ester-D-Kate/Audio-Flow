# Audio Flow

A modern, hotkey-driven audio typewriter that sits quietly on your screen. It records your voice, transcribes it using Groq Whisper, formats it into perfect text (or generates content from your instructions), and types it directly where your cursor is.

## 🚀 Getting Started

**For most users (No coding required):**

1. **Download**: Get `Audio Flow.exe` from the [Releases](../../releases) page.
2. **Create Folder**: Make a new folder (e.g., `Audio Flow`) and move the `.exe` into it.
3. **Setup Keys**: Create a `.env` file in that folder. Add your API keys as shown in `.env.example` (e.g., `GROQ_API_KEY=...`).
4. **Setup Config (Optional)**: Create a `config.json` file in the same folder to customize hotkeys.
5. **Run**: Double-click `Audio Flow.exe`. It will automatically load your settings from the folder.

## ✨ Features

- **Two Powerful Modes**:
  - **🎤 Transcribe Mode**: Speak naturally, and it types out clean, punctuated text.
  - **✨ Prompt Mode**: Give instructions (e.g., "Write a polite email declining this offer"), and it generates the content for you.
- **Always-on-Top UI**: A sleek, minimal bar that floats over your work.
- **Global Hotkeys**: Control everything without leaving your current window.
- **Smart Audio**: Uses overlapping segments to ensure not a single word is lost.
- **Multi-Key Support**: Automatically rotates through multiple Groq API keys to handle rate limits.

## 🎮 How to Use

### The Interface
The app starts as a small pill-shaped bar.
- **🎤 (Blue)**: Start Transcription Mode.
- **✨ (Purple)**: Start Prompt Generation Mode.

Once recording, the bar expands to show:
- **Waveform**: Visual feedback of your voice.
- **📤 (Send)**: Stop recording, process, and type the result.
- **⏸ (Pause)**: Pause/Resume recording.
- **✖ (Cancel)**: Discard the current recording.

### Hotkeys
| Action | Default Hotkey | Description |
| :--- | :--- | :--- |
| **Start Transcribe** | `Ctrl` + `Shift` + `L` | Start recording for direct transcription. |
| **Start Prompt** | `Ctrl` + `Shift` + `Alt` + `P` | Start recording instructions for AI generation. |
| **Stop & Send** | `Ctrl` + `Alt` + `S` | Finish recording and paste the result. |
| **Pause/Resume** | `Ctrl` + `Shift` + `Space` | Pause the recording temporarily. |
| **Cancel** | `Ctrl` + `Shift` + `Esc` | Cancel and discard everything. |

*(You can customize these by creating a `config.json` file)*

## 🛠️ Configuration (Optional)

To change hotkeys, create a `config.json` file next to the executable:

```json
{
  "hotkeys": {
    "start": "alt+L",
    "stop": "alt+x",
    "pause": "ctrl+space",
    "cancel": "alt+esc",
    "prompt": "alt+p"
  }
}
```

## 👨‍💻 Development & Building (DAB)

If you want to modify the code or build your own executable, follow these steps.

### Prerequisites
- Python 3.10+
- Install dependencies: `pip install -r requirements.txt`

### 🛡️ Secure Build (Recommended)
*This method keeps your API keys and configuration separate from the executable. It ensures your `.exe` is clean, safe to share, and allows you to change settings without recompiling.*

1. **Compile**:
   Run this command to build the executable (it will NOT bundle your secrets):
   ```bash
   pyinstaller --noconsole --onefile --name "Audio Flow" terminal_app/main.py
   ```

2. **Deploy**:
   - Create a folder (e.g., `Audio Flow`).
   - Move the generated `Audio Flow.exe` (from `dist/`) into it.
   - **Important**: Copy your `.env` and `config.json` files into this same folder.

3. **Run**:
   Launch `Audio Flow.exe`. It will automatically load the environment variables and config from the files in its folder.

### 📦 Bundled Keys (Semi-Secure)
*Includes `.env` (API keys) inside the executable, but keeps `config.json` external. This allows you to change hotkeys without recompiling, while having your keys built-in.*

**⚠️ Warning: This is NOT secure to share publicly. Your API keys can be extracted from the executable.**

1. **Compile**:
   ```bash
   pyinstaller --noconsole --onefile --name "Audio Flow" --add-data ".env;." terminal_app/main.py
   ```

2. **Deploy**:
   - Create a folder.
   - Move `Audio Flow.exe` into it.
   - Create/Copy a `config.json` file into the same folder to customize hotkeys.

### ⚠️ Fully Bundled (Non-Secure)
*Includes BOTH `config.json` and `.env` (API keys) inside the executable. Use this ONLY for personal convenience on your own machine. NEVER share this executable.*
```bash
pyinstaller --noconsole --onefile --name "Audio Flow" --add-data "config.json;." --add-data ".env;." terminal_app/main.py
```
*(Note: On Mac/Linux, use `:` instead of `;` separator)*

## 🏗️ Architecture

- **UI**: Built with PyQt6 for a modern, frameless, transparent look.
- **Audio**: Uses `sounddevice` with overlapping threads to capture continuous audio without gaps.
- **AI**: Powered by Groq (Whisper for transcription, Llama 3 for formatting/generation).
- **Input**: Uses `keyboard` for global hotkeys and `pyautogui` for text insertion.

## ❓ Troubleshooting

If the application crashes or behaves unexpectedly (especially when running without a terminal window), check the `audio_flow.log` file. It is automatically created in the same folder as the executable and contains detailed error messages.

---
