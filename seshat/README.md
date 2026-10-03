# Seshat

Private, CPU-based face recognition for Home Assistant event images. Enroll familiar people through Home Assistant Ingress and expose recognized names, scores and events through the included Seshat custom integration.

Runs locally on amd64, with persistent SQLite identity records, YuNet detection and SFace embeddings. No cloud recognition, MQTT, GPU or Home Assistant access token required.

Set a random API key of at least 32 characters before starting. Install `custom_components/seshat` from this repository into Home Assistant's configuration directory and restart Core. The app alone does not create sensors. See the repository-root README for the full architecture and installation guide.
