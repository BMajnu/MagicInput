# 🚀 MagicInput

**MagicInput** is an upgraded, all-in-one input window for Cursor, Windsurf or any other _agent-mode_ coding assistant that supports tool calls.

It lets you fire off a single request and then iterate — text _and_ screenshots — inside the **same** request, squeezing the maximum value out of your monthly tool-call quota.

> **Note**  MagicInput only shines when your assistant runs in **Agent Mode** (where each follow-up uses tool calls, _not_ new requests).

---

## ✅ What It Does

After the AI finishes a task MagicInput pops up and asks for your next instruction:

```
prompt:
```

1. You type _"add comments"_, _"refactor this"_, paste an image, etc.
2. The AI continues working inside the same session.
3. The loop repeats until **you** stop or the session hits its tool-call limit.

---

## 💡 Why This Matters

Most AI coding tools give you a fixed number of **requests** (e.g. 500 / month) and each request may include up to **25 tool calls**. Saying just "hi" burns a full request and wastes the remaining 24 calls.

With **MagicInput**:

* You start one request.
* You can issue many follow-ups (each consuming only tool calls).
* You therefore get ≈10 × more work out of the exact same quota.

---

## ⚙️ Set-Up (Basic)

1. Copy `MagicInput.py` to your project root.
2. Add `rule.mdc` (or copy the snippet below) to your IDE's **Project Rules** and set it to **always**.
3. Run your assistant in Agent Mode.  That's it — you now have an interactive loop!

```mdc
# rule.mdc (minimal)
When the current task finishes, launch MagicInput and wait for the user's next command.
```

---

## 🧪 Current Version

* ✅ **Plain-text input** in a comfy, resizable text area
* ✅ **Attach multiple screenshots** via drag-and-drop, file picker or direct clipboard paste (<kbd>Ctrl/⌘</kbd>+<kbd>V</kbd>)
* ✅ **Image carousel** with preview, next/prev navigation, removal and counter
* ✅ **Dark ↔ Light theme toggle** with a single click
* ✅ **Custom frameless window** that you can drag anywhere
* ✅ **Minimize to system-tray** on Windows (tray icon with Show / Exit)
* ✅ **Send** & **Send + Close** buttons that print the prompt to stdout and log it to `.MagicInput/`
* ✅ **Hover feedback** on every control for a polished UX
* ✅ **Auto-installs dependencies** (`pillow`, `pystray`, optional `tkinterdnd2`) on first launch
* ✅ **Cross-platform**: tested on Windows, macOS and Linux

---

## 📸 Screenshots

| Dark Theme | Light Theme |
|---|---|
| ![Dark mode preview](.MagicInput/Darkmode.png) | ![Light mode preview](.MagicInput/Lightmode.png) |

---

## 🛠️ Installation

```bash
# clone
git clone https://github.com/cursor-windsarf/MagicInput.git
cd MagicInput

# run with Python 3.8+
python MagicInput.py
```

> The first launch auto-installs missing dependencies (`pillow`, `pystray`, optional `tkinterdnd2`).

---

## 🤖 Example Workflow

1. Start a new chat → _one_ request is opened.
2. MagicInput appears.
3. Type "generate README" + paste screenshot → AI works (tool calls 1-5).
4. MagicInput re-appears.
5. Type "add comments" → AI continues (tool calls 6-8).
6. …repeat up to 25 tool calls then the session gracefully ends.

You accomplished multiple edits inside **one** request 🔥

---

## 🧰 Advanced Tips

* Toggle Dark/Light theme with the 🌗 button.
* Use <kbd>Ctrl</kbd>/<kbd>Cmd</kbd> + <kbd>V</kbd> to paste clipboard images.
* Click the 📷 button or drag files onto the canvas to attach screenshots.
* All prompts & attachments live in a hidden `.MagicInput/` folder alongside the script.

---

## 🙋‍♂️ Developer

MagicInput is maintained by **Badiuzzaman Majnu** (<badiuzzaman.majnu@gmail.com>). Contributions, issues, and pull requests are welcome!

---

## 📜 License

Released under the MIT License – see [`LICENSE`](LICENSE) for full text.
