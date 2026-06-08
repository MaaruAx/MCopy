<div align="center">

<br>

# ◈ MCopy

![early-access](https://img.shields.io/badge/⚠_EARLY_ACCESS-ff6b6b?style=for-the-badge&labelColor=1a1a2e)
&nbsp;
![version](https://img.shields.io/badge/version-1.0-f5c842?style=for-the-badge&labelColor=1a1a2e)
&nbsp;
![free](https://img.shields.io/badge/Works_on_FREE_Resolve-31c48d?style=for-the-badge&labelColor=1a1a2e)

<br>

**A Fusion node preset manager for DaVinci Resolve.**

*Copy any node group. Save it. Paste it into any composition, forever.*

<br>

![Windows](https://img.shields.io/badge/Windows-f5c842?style=flat-square&logo=windows&logoColor=1a1a2e)
&nbsp;
![macOS](https://img.shields.io/badge/macOS-f5c842?style=flat-square&logo=apple&logoColor=1a1a2e)
&nbsp;
![Linux](https://img.shields.io/badge/Linux-f5c842?style=flat-square&logo=linux&logoColor=1a1a2e)
&nbsp;
![Python](https://img.shields.io/badge/Python_3.9+-f5c842?style=flat-square&logo=python&logoColor=1a1a2e)
&nbsp;
![Resolve](https://img.shields.io/badge/DaVinci_Resolve_18+-f5c842?style=flat-square&logoColor=1a1a2e)

<br>

> ⚠️ **Early access release.** Bugs are expected and features are actively being added. Your feedback directly shapes what gets built next — see how to reach us below.

<br>

</div>

---

## ![what](https://img.shields.io/badge/◈_WHAT_IS_MCOPY-f5c842?style=flat-square&labelColor=1a1a2e)

Every Fusion artist has node groups they rebuild from scratch over and over — a glow setup, a recolor stack, a particular merge chain. **MCopy is a persistent library for all of them.**

Copy any nodes in Fusion, capture them in MCopy, give them a name. Done. They're stored locally and searchable by name or description. Next time you need them, select the preset, hit Paste, and Ctrl+V in Fusion. Works on both the free and Studio editions of DaVinci Resolve.

<table>
<tr>
<td>

![capture](https://img.shields.io/badge/Capture_&_Save-f5c842?style=flat-square&labelColor=26233a)

```
Ctrl+C in Fusion → Capture in MCopy
Name it, add an optional description
Saved locally, available forever
```

</td>
<td>

![search](https://img.shields.io/badge/Search_&_Paste-555?style=flat-square&labelColor=26233a)

```
Full-text search across names & descriptions
Select any preset → Paste
Ctrl+V in Fusion — done
```

</td>
</tr>
</table>

---

## ![features](https://img.shields.io/badge/◈_FEATURES-f5c842?style=flat-square&labelColor=1a1a2e)

![presets](https://img.shields.io/badge/Persistent_preset_library-f5c842?style=flat-square&labelColor=26233a) &nbsp;Presets are stored in a local SQLite database — they survive restarts, updates, and reinstalls.

![fts](https://img.shields.io/badge/Full--text_search-555?style=flat-square&labelColor=26233a) &nbsp;Powered by SQLite FTS5. Search by name or description with prefix matching — type `glo` to find anything with "glow" in it.

![source](https://img.shields.io/badge/Source_tracking-f5c842?style=flat-square&labelColor=26233a) &nbsp;Each preset shows a badge marking whether it was captured from the clipboard or via the scripting API — useful when you build up a large library over time.

![themes](https://img.shields.io/badge/3_themes-555?style=flat-square&labelColor=26233a) &nbsp;MMarket (default), Rosé Pine, and Gruvbox. Swap at any time from Settings without restarting.

![accent](https://img.shields.io/badge/Custom_accent_color-f5c842?style=flat-square&labelColor=26233a) &nbsp;Color swatches plus a hex input. Applied instantly across the entire UI.

![fonts](https://img.shields.io/badge/2_display_fonts-555?style=flat-square&labelColor=26233a) &nbsp;Barlow Condensed (default) and Monaspace Neon — both bundled, no internet required.

![i18n](https://img.shields.io/badge/3_languages-f5c842?style=flat-square&labelColor=26233a) &nbsp;English, Español, हिन्दी. Deutsch coming in a future update.

---

## ![modes](https://img.shields.io/badge/◈_CAPTURE_MODES-f5c842?style=flat-square&labelColor=1a1a2e)

![clipboard](https://img.shields.io/badge/Clipboard-f5c842?style=flat-square&labelColor=26233a) &nbsp;The standard workflow. Select your nodes in Fusion → **Ctrl+C** → **Capture** in MCopy → name it → **Save**. To use a preset later, select it and click **Paste** — your nodes are on the clipboard ready for **Ctrl+V** in any Fusion composition.

![scripting](https://img.shields.io/badge/Scripting_Pro_(coming_soon)-555?style=flat-square&labelColor=26233a) &nbsp;Captures and pastes directly without Ctrl+C / Ctrl+V. The scripting mode will talk to Resolve's API layer and handle the data transfer automatically — no manual clipboard steps.

---

## ![install](https://img.shields.io/badge/◈_INSTALLATION-f5c842?style=flat-square&labelColor=1a1a2e)

```bash
python main.py
```

MCopy runs directly — no installer needed.

<details>
<summary>

![trouble](https://img.shields.io/badge/Requirements_/_Troubleshooting-555?style=flat-square&labelColor=26233a)

</summary>

<br>

**Install dependencies manually if needed:**

```bash
pip install PySide6
```

On Linux, also install one of these for clipboard support:

```bash
sudo apt install xclip   # or: sudo apt install xsel
```

**Python from the Microsoft Store will not work.** Download the standard installer from **[python.org/downloads](https://python.org/downloads)** and check *"Add Python to PATH"* during setup.

<br>

> **Still stuck? Join the Discord.** Post your error message and your OS version — most issues are already solved there.

[![discord](https://img.shields.io/badge/Join_the_Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/invite/dvZ9nvN79Y)

<br>

</details>

---

## ![req](https://img.shields.io/badge/◈_REQUIREMENTS-f5c842?style=flat-square&labelColor=1a1a2e)

| | |
|---|---|
| ![resolve](https://img.shields.io/badge/DaVinci_Resolve_18+-f5c842?style=flat-square&labelColor=26233a) | Free or Studio — both work |
| ![python](https://img.shields.io/badge/Python_3.9+-f5c842?style=flat-square&labelColor=26233a) | **Must be the `.exe` installer from [python.org](https://python.org/downloads)** |
| ![pyside](https://img.shields.io/badge/PySide6-555?style=flat-square&labelColor=26233a) | `pip install PySide6` |
| ![xclip](https://img.shields.io/badge/xclip_or_xsel_(Linux_only)-555?style=flat-square&labelColor=26233a) | `sudo apt install xclip` |

---

<div align="center">

<br>

![oss](https://img.shields.io/badge/Free_&_Open_Source-1a1a2e?style=for-the-badge)
&nbsp;
[![discord](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/invite/dvZ9nvN79Y)
&nbsp;
[![releases](https://img.shields.io/badge/Releases-f5c842?style=for-the-badge&labelColor=1a1a2e)](https://codeberg.org/MaaruAx/MCopy/releases)

<br>
<sub>Part of the MMarket ecosystem. Built for the DaVinci Resolve / Fusion community.</sub>
<br><br>

</div>
