<div align="center">
<br>

# ◈𝐌𝐂𝐎𝐏𝐘

[![Version](https://img.shields.io/badge/Version-v1.0.0-c4a7e7?style=for-the-badge&labelColor=1a1a2e)](https://github.com/MaaruAX/MCopy/releases)
[![Status](https://img.shields.io/badge/Status-Stable-c4a7e7?style=for-the-badge&labelColor=1a1a2e)](https://github.com/MaaruAX/MCopy)
![free](https://img.shields.io/badge/Works_on_FREE_Resolve-1a1a2e?style=for-the-badge&labelColor=1a1a2e)
<br>

**Cross-platform Fusion node preset manager for DaVinci Resolve**
*Save, search, and instantly recall node graphs with a single click*

<br>

![Windows](https://img.shields.io/badge/Windows-9ccfd8?style=flat-square&logo=windows&logoColor=1a1a2e)
&nbsp;
![macOS](https://img.shields.io/badge/macOS-ebbcba?style=flat-square&logo=apple&logoColor=1a1a2e)
&nbsp;
![Linux](https://img.shields.io/badge/Linux-f6c177?style=flat-square&logo=linux&logoColor=1a1a2e)
&nbsp;
![Python](https://img.shields.io/badge/Python_3.9+-c4a7e7?style=flat-square&logo=python&logoColor=1a1a2e)
&nbsp;
![Resolve](https://img.shields.io/badge/DaVinci_Resolve_18+-eb6f92?style=flat-square&logoColor=1a1a2e)

<br>
</div>

![What is MCopy](https://img.shields.io/badge/◈_WHAT_IS_MCOPY-eb6f92?style=flat-square&labelColor=1a1a2e)

MCopy is an elegant, ultra-fast preset manager designed for DaVinci Resolve and Fusion editors. Developed as part of the MMarket ecosystem, it bridges your system clipboard with a lightweight local SQLite database to index, search, and organize complex node trees. 

Instead of cluttering your power bins or saving endless settings files, copy your node chains inside Fusion, hit capture in MCopy, and build a localized, searchable library of utility setups, custom expressions, and complex node structures.

<br>

![Features](https://img.shields.io/badge/◈_FEATURES_&_STYLING-f6c177?style=flat-square&labelColor=1a1a2e)

![Capture Clipboard](https://img.shields.io/badge/Capture_Clipboard-9ccfd8?style=flat-square&labelColor=26233a) &nbsp; Grab any selected nodes from Fusion immediately using standard copying behaviors.

![Instant Presets](https://img.shields.io/badge/Instant_Presets-f6c177?style=flat-square&labelColor=26233a) &nbsp; Save captured graphs with customized names, notes, metadata, and timestamps.

![FTS5 Search Engine](https://img.shields.io/badge/FTS5_Search-eb6f92?style=flat-square&labelColor=26233a) &nbsp; Real-time, lightning-fast database searching using native SQLite virtual tables.

![Quick Paste](https://img.shields.io/badge/Quick_Paste-c4a7e7?style=flat-square&labelColor=26233a) &nbsp; Paste presets directly back into your clipboard with one click, ready for Fusion viewport deployment.

![Visual Themes](https://img.shields.io/badge/Themes_Included-9ccfd8?style=flat-square&labelColor=26233a) &nbsp; Beautiful built-in templates matching Rosé Pine, MMarket, and Gruvbox aesthetics.

![Multi-Language UI](https://img.shields.io/badge/Localized-f6c177?style=flat-square&labelColor=26233a) &nbsp; Full built-in translations for English, Spanish, German, and Hindi.

<br>

![Execution Modes](https://img.shields.io/badge/◈_EXECUTION_MODES-9ccfd8?style=flat-square&labelColor=1a1a2e)

MCopy supports two core capture methodologies designed to align with both standard and advanced automation workflows:

| ![Clipboard Mode](https://img.shields.io/badge/Clipboard_Mode-c4a7e7?style=flat-square&labelColor=1a1a2e) | ![Scripting Pro Mode](https://img.shields.io/badge/Scripting_Pro_Mode-9ccfd8?style=flat-square&labelColor=1a1a2e) |
| :--- | :--- |
| `• Traditional Ctrl+C / Ctrl+V pipeline` <br> `• Works out of the box on all system variants` <br> `• Zero additional external configuration required` | `• Hands-free API-level capture` <br> `• Utilizes native DaVinci Scripting modules` <br> `• Bypasses manual copy and paste workflows` |

<br>

![Installation](https://img.shields.io/badge/◈_INSTALLATION-c4a7e7?style=flat-square&labelColor=1a1a2e)

Follow these steps to set up and run MCopy locally on your computer:

```bash
# 1. Clone the repository
git clone https://github.com/MaaruAX/MCopy.git

# 2. Navigate to the project directory
cd MCopy

# 3. Install required Python packages
pip install -r requirements.txt

# 4. Launch the application
python main.py
```

*Note: If running on Windows, make sure `pywin32` is installed to ensure fast, native access to the system clipboard utilities.*

<br>

![Requirements](https://img.shields.io/badge/◈_REQUIREMENTS-ebbcba?style=flat-square&labelColor=1a1a2e)

| Platform / Tool | Minimum System Specifications |
| :--- | :--- |
| ![Python Badge](https://img.shields.io/badge/Python-eb6f92?style=flat-square&labelColor=1a1a2e) | Version 3.9 or higher |
| ![PySide6 Badge](https://img.shields.io/badge/PySide6-c4a7e7?style=flat-square&labelColor=1a1a2e) | PySide6 with QtWebEngine components |
| ![Resolve Badge](https://img.shields.io/badge/Resolve-9ccfd8?style=flat-square&labelColor=1a1a2e) | DaVinci Resolve or Fusion Studio 17+ |

<br>

<details>
<summary><img src="https://img.shields.io/badge/◈_TROUBLESHOOTING-f6c177?style=flat-square&labelColor=1a1a2e" alt="Troubleshooting Badge" /></summary>

### Empty or Black GUI Viewport
MCopy forces GPU hardware acceleration settings before initializing. If you encounter rendering problems or empty windows, update your system graphics drivers or modify the hardware acceleration flags located inside `main.py`'s entry block.

### Clipboard Issues on Linux Distributions
On Linux systems, the PySide integration relies on system clipboard fallbacks. Verify that either `xclip` or `xsel` utilities are installed and available inside your system's path variables:
```bash
sudo apt-get install xclip
```

### Pro Scripting Connectivity
The "Scripting (Pro)" pipeline relies on the external Python integration capabilities provided in DaVinci Resolve Studio. Standard clipboard capture mode remains fully compatible with both the Free and Studio editions of DaVinci Resolve.
</details>

<br>

<div align="center">

[![OSS](https://img.shields.io/badge/Open_Source-26233a?style=for-the-badge&labelColor=1a1a2e)](https://github.com/MaaruAX/MCopy)
[![Discord](https://img.shields.io/badge/Discord_Support-5865F2?style=for-the-badge&labelColor=1a1a2e)](https://discord.com/invite/dvZ9nvN79Y)
[![releases](https://img.shields.io/badge/Releases-eb6f92?style=for-the-badge)](https://codeberg.org/MaaruAx/MCopy/releases)

<sub>Part of the MMarket ecosystem • Created with love for the DaVinci Resolve community.</sub>
</div>