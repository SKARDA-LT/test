# Dual Translate for ElevenReader

Android app prototype that watches text selection events only from ElevenReader (`io.elevenlabs.readerapp`) using an Accessibility Service.

Behavior:
- select English text in ElevenReader;
- after ~650 ms the complete selected phrase is translated;
- both Lithuanian and Russian results are shown together in an accessibility overlay;
- no clipboard monitoring is used;
- the Google Cloud Translation API key is entered locally in the installed app and is not stored in this repository.

The build workflow creates a debug APK artifact for testing on Android.
