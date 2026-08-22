# Dual Translate v4

Android test app for automatic EN -> Lithuanian + Russian translation.

v4 safety changes:
- only one accessibility service should be enabled;
- editable text fields are ignored;
- generic Share/More automation is removed;
- ElevenReader uses a dedicated Copy + Select all + Add pronunciation toolbar detector;
- the Google Cloud Translation API key stays local in the installed app.

The build workflow creates a debug APK artifact for testing on Android.
