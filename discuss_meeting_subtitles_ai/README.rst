.. image:: https://img.shields.io/badge/license-LGPL--3-green.svg
    :target: https://www.gnu.org/licenses/lgpl-3.0-standalone.html
    :alt: License: LGPL-3

=================================================
Discuss Meeting Live Subtitles & AI Summaries
=================================================
Real-time speech-to-text closed captioning and AI-powered meeting summaries for Odoo Discuss
video and audio calls (Odoo 19).

Inspired by on-device speech-to-text inference architectures (like Cactus Whistle), this module
provides a privacy-first meeting experience directly inside Odoo Discuss. Speech is transcribed on
your own server by default; Grok STT (xAI) can be chosen instead for cloud transcription.

Key Features
============

Live Subtitles (Closed Captions)
--------------------------------
* **Real-time voice transcription**: spoken words are captured in the browser and displayed as
  subtitles.
* **Speaker identification**: subtitles show the speaker's name next to the text.
* **Participant broadcasting**: captions are sent to the other participants over Odoo's bus.
* **One-click toggle**: turn subtitles on or off from the call action bar with the
  **Subtitle(CC)** button. It is personal: only you see captions, and while anyone has it on,
  everyone in the call is captioned.
* **Transcribe (independent of subtitles)**: the **Transcribe** button records everyone's speech
  into the call's meeting summary, for the whole call. Only internal users can turn it on or off;
  everyone in the call is notified and sees a "Transcribing" indicator. Subtitles alone record
  nothing.

AI Meeting Summaries & Minutes
------------------------------
* **Live transcript history**: timestamped speech transcripts are logged during the call
  (``[10:15:30] Mitchell Admin: ...``).
* **AI summarization**: structured meeting minutes containing:

  * **Executive Summary**: high-level overview of the meeting.
  * **Key Discussion Points**: main topics discussed.
  * **Decisions Made**: resolutions and agreed points.
  * **Action Items & To-Dos**: assigned tasks with owners.

* **Chatter integration**: post meeting minutes to the Discuss channel with a single click.
* **Backend archive**: all meeting summaries and full transcripts are kept under
  ``Discuss > Meeting Summaries``.

Speech-to-Text Engines
----------------------
* **Whisper (default)**: local faster-whisper, run in a worker process on your server that all
  Odoo workers share. Audio never leaves the server, unless **OpenAI Speech Fallback** is enabled:
  then a live caption or uploaded recording the engine fails on (error, busy, not installed) is
  sent to OpenAI instead. It is off by default; an OpenAI key set for summaries alone never sends
  meeting audio.
* **Whistle**: tiny, fast local model (English, German, French, Spanish, Italian, Dutch, Polish).
* **Auto**: Whistle first. Whisper redoes a caption when Whistle hears nothing or is unsure of a
  word (typical on noisy audio), so those captions take longer but come out more accurate.
* **Grok STT (xAI cloud)**: ``grok-voice-transcribe-2.0``, used for live captions and uploaded
  recordings. Needs no server CPU or model download, takes participant names and keywords as key
  terms, and labels each speaker with timestamps in uploaded recordings. Needs an xAI API key.
  **Meeting audio is sent to xAI.** Live partial captions are not used with Grok, as each would
  be a billed request.

AI Provider Options
-------------------
* **Built-in smart summarizer**: heuristic summarizer that needs **no external API key or setup**.
* **OpenAI (ChatGPT)**: high-accuracy summaries with models like ``gpt-4o-mini`` or ``gpt-4o``.
* **Ollama / local LLM (Needle / Llama 3)**: private, on-premise inference without external cloud
  dependencies.

Installation
============
#. Install the Python packages the module needs into the Python environment that runs Odoo::

       pip install faster-whisper cactus-needle

   ``faster-whisper`` runs the Whisper engine and ``cactus-needle`` runs the Whistle engine.
   Install ``cactus-needle``, not ``needle``: the ``needle`` package on PyPI is an unrelated
   CSS-testing tool. Each speech model is downloaded the first time it is used, so the server
   needs internet access once.

#. Add the folder holding this module to ``addons_path`` in ``odoo.conf``::

       addons_path = /path/to/addons,/path/to/custom_addons

#. Update the app list in Odoo:

   * Go to ``Apps > Update App List``.
   * Search for **Discuss Meeting Live Subtitles & AI Summaries**.
   * Click **Activate**.

Usage
=====
* Open any Discuss channel and click **Start Call** / **Video Call**.
* Click **Subtitle(CC)** in the call bar to see live captions, and/or **Transcribe** to record the
  conversation for the meeting summary. The two work independently.
* Click **AI Summary & Notes** (magic wand) to open the meeting assistant, view the live
  transcript and generate an AI meeting summary.
* Click **Post to Channel Chatter** to share the formatted summary with all channel members.

Configuration
=============
* Go to ``Settings > Discuss > Meeting Subtitles & AI Summaries``.
* Choose the speech-to-text engine. For **Grok STT**, enter your xAI API key.
* Add names, places and product terms to **Keywords**: they markedly improve how names are
  recognized (the names of the people in the call are added automatically).
* Choose your preferred AI provider (Built-in, OpenAI, or Ollama/Local).
* Select the speech recognition language.

Company
=======
* `Cybrosys Techno Solutions <https://cybrosys.com/>`__

License
=======
GNU Lesser General Public License, Version 3 (LGPL-3).
(https://www.gnu.org/licenses/lgpl-3.0-standalone.html)
