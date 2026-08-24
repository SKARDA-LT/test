from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.')

# Main screen checkbox.
p = root / 'app/src/main/java/lt/skarda/dualtranslate/MainActivity.java'
s = p.read_text()
s = s.replace('import android.widget.Button;\n', 'import android.widget.Button;\nimport android.widget.CheckBox;\n')
s = s.replace('    private static final String PREFS = "dual_translate_prefs";\n',
              '    private static final String PREFS = "dual_translate_prefs";\n'
              '    private static final String PREF_AUTO_TRANSLATE = "automatic_translation_enabled";\n')
s = s.replace('    private EditText apiKey;\n', '    private EditText apiKey;\n    private CheckBox automaticTranslation;\n')
s = s.replace(
    '        TextView sub = text("Automatic EN -> Lithuanian + Russian translation for selected text in Android apps, with a dedicated ElevenReader fallback.", 16, false);',
    '        TextView sub = text("EN -> Lithuanian + Russian translation for selected text, with automatic and manual ElevenReader modes.", 16, false);')
anchor = '''        root.addView(accessibility, matchWrap(dp(12)));\n\n'''
ui = anchor + '''        automaticTranslation = new CheckBox(this);\n        automaticTranslation.setText("Automatic translation after text selection");\n        automaticTranslation.setTextSize(17);\n        automaticTranslation.setTextColor(Color.rgb(30, 30, 30));\n        automaticTranslation.setPadding(0, dp(12), 0, dp(2));\n        automaticTranslation.setChecked(getSharedPreferences(PREFS, MODE_PRIVATE)\n                .getBoolean(PREF_AUTO_TRANSLATE, true));\n        automaticTranslation.setOnCheckedChangeListener((button, checked) -> {\n            getSharedPreferences(PREFS, MODE_PRIVATE).edit()\n                    .putBoolean(PREF_AUTO_TRANSLATE, checked).apply();\n            Toast.makeText(this, checked\n                    ? "Automatic translation enabled"\n                    : "Automatic translation disabled. In ElevenReader, tap Copy to translate.",\n                    Toast.LENGTH_SHORT).show();\n        });\n        root.addView(automaticTranslation);\n\n        TextView automaticHelp = text(\n                "Checked: selection translates automatically, including ElevenReader screen recognition. " +\n                "Unchecked: automatic translation is stopped; in ElevenReader select text and tap Copy.",\n                14, false);\n        automaticHelp.setPadding(dp(4), 0, 0, dp(12));\n        root.addView(automaticHelp);\n\n'''
if anchor not in s:
    raise RuntimeError('MainActivity UI anchor not found')
s = s.replace(anchor, ui, 1)
s = s.replace(
    '        TextView how = text("Enable only Dual Translate v15 in Accessibility. In normal apps it reads Android selection or its PROCESS_TEXT action. In ElevenReader it detects the custom Copy / Select all / Add pronunciation toolbar, reads the highlighted ElevenReader selection from an Accessibility screenshot using on-device OCR. Manual Copy still works as a fallback.", 15, false);',
    '        TextView how = text("Enable only Dual Translate v16 in Accessibility. With the checkbox on, normal selection and ElevenReader highlighted text translate automatically. With it off, automatic selection and screenshot recognition are disabled; ElevenReader translates only after you tap Copy.", 15, false);')
s = s.replace("Clipboard is used only for ElevenReader's dedicated automatic Copy fallback.",
              "Clipboard is used only after you tap Copy in ElevenReader.")
s = s.replace('Dual Translate v15', 'Dual Translate v16')
p.write_text(s)

# Accessibility service: manual ElevenReader Copy is always allowed; everything else obeys the checkbox.
p = root / 'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s = p.read_text()
s = s.replace('    private static final String PREFS = "dual_translate_prefs";\n',
              '    private static final String PREFS = "dual_translate_prefs";\n'
              '    private static final String PREF_AUTO_TRANSLATE = "automatic_translation_enabled";\n')
old = '''    public static boolean submitExternalSelection(String text, String route) {\n        SelectionTranslateService s = INSTANCE;\n        if (s == null) return false;\n        s.handler.post(() -> {\n            s.saveDiagnostic(route + " delivered selected text: “" + trimForLog(text) + "”");\n            s.queueTranslation(text);\n        });\n        return true;\n    }\n'''
new = '''    public static boolean submitExternalSelection(String text, String route) {\n        SelectionTranslateService s = INSTANCE;\n        if (s == null) return false;\n        s.handler.post(() -> {\n            boolean manualCopy = route != null &&\n                    route.toLowerCase(Locale.ROOT).contains("elevenreader manual copy");\n            if (!manualCopy && !s.isAutomaticTranslationEnabled()) {\n                s.saveDiagnostic("Automatic translation is OFF. In ElevenReader, tap Copy to translate.");\n                return;\n            }\n            s.saveDiagnostic(route + " delivered selected text: “" + trimForLog(text) + "”");\n            s.queueTranslation(text);\n        });\n        return true;\n    }\n\n    private boolean isAutomaticTranslationEnabled() {\n        return getSharedPreferences(PREFS, MODE_PRIVATE)\n                .getBoolean(PREF_AUTO_TRANSLATE, true);\n    }\n'''
if old not in s:
    raise RuntimeError('submitExternalSelection block not found')
s = s.replace(old, new, 1)
s = s.replace(
    '        saveDiagnostic("v15 service connected. Gmail uses normal Android selection. ElevenReader highlighted text is read from an Accessibility screenshot with on-device OCR; manual Copy remains a fallback.");',
    '        saveDiagnostic(isAutomaticTranslationEnabled()\n'
    '                ? "v16 service connected. Automatic translation is ON; ElevenReader manual Copy is also available."\n'
    '                : "v16 service connected. Automatic translation is OFF; ElevenReader works after manual Copy.");')
anchor = '''        boolean isElevenReader = ELEVEN_READER_PACKAGE.equals(pkg);\n        if (isElevenReader) elevenReaderSeenUntil = now + 9000;\n\n        if (type == AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED) {\n'''
gate = '''        boolean isElevenReader = ELEVEN_READER_PACKAGE.equals(pkg);\n        if (isElevenReader) elevenReaderSeenUntil = now + 9000;\n\n        if (type == AccessibilityEvent.TYPE_VIEW_CLICKED && isElevenReader && isCopyEvent(event)) {\n            saveDiagnostic("v16: ElevenReader Copy clicked. Waiting for clipboard update.");\n            handler.postDelayed(this::handleClipboardChanged, 100);\n            return;\n        }\n\n        if (!isAutomaticTranslationEnabled()) {\n            if (type == AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED ||\n                    type == AccessibilityEvent.TYPE_VIEW_LONG_CLICKED ||\n                    (isElevenReader && type == AccessibilityEvent.TYPE_TOUCH_INTERACTION_END)) {\n                saveDiagnostic("Automatic translation is OFF. In ElevenReader, tap Copy to translate.");\n            }\n            return;\n        }\n\n        if (type == AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED) {\n'''
if anchor not in s:
    raise RuntimeError('event anchor not found')
s = s.replace(anchor, gate, 1)
s = s.replace('''        if (type == AccessibilityEvent.TYPE_VIEW_CLICKED && isElevenReader && isCopyEvent(event)) {\n            saveDiagnostic("v7: ElevenReader Copy click accessibility event detected. Waiting for clipboard update.");\n            handler.postDelayed(this::handleClipboardChanged, 100);\n            return;\n        }\n\n''', '', 1)
s = s.replace('            if (selected != null) queueTranslation(selected);\n',
              '            if (selected != null) queueAutomaticTranslation(selected);\n', 1)
s = s.replace('                            queueTranslation(selected);\n',
              '                            queueAutomaticTranslation(selected);\n', 1)
s = s.replace('                queueTranslation(selected);\n',
              '                queueAutomaticTranslation(selected);\n', 1)
s = s.replace('    private void tryElevenReaderAutoCopy() {\n        long now',
              '    private void tryElevenReaderAutoCopy() {\n        if (!isAutomaticTranslationEnabled()) return;\n        long now', 1)
s = s.replace('    private void requestElevenScreenshotOcr() {\n        removePopup();',
              '    private void requestElevenScreenshotOcr() {\n        if (!isAutomaticTranslationEnabled()) return;\n        removePopup();', 1)
s = s.replace('    private void recognizeElevenSelection(Bitmap bitmap) {\n        TextRecognizer recognizer',
              '    private void recognizeElevenSelection(Bitmap bitmap) {\n        if (!isAutomaticTranslationEnabled()) {\n            try { bitmap.recycle(); } catch (Exception ignored) {}\n            return;\n        }\n        TextRecognizer recognizer', 1)
s = s.replace('    private void scanActiveWindowForSelection() {\n        AccessibilityNodeInfo root',
              '    private void scanActiveWindowForSelection() {\n        if (!isAutomaticTranslationEnabled()) return;\n        AccessibilityNodeInfo root', 1)
s = s.replace('    private void scanForSelectionUi() {\n        long now',
              '    private void scanForSelectionUi() {\n        if (!isAutomaticTranslationEnabled()) return;\n        long now', 1)
old = '''    private void queueTranslation(String raw) {\n        String text = normalize(raw);\n        if (text == null) return;\n        candidate = text;\n        if (pendingSelection != null) handler.removeCallbacks(pendingSelection);\n        pendingSelection = () -> {\n            String finalText = candidate;\n            if (finalText == null) return;\n            long now = SystemClock.uptimeMillis();\n            if (finalText.equals(lastTranslated) && now - lastTranslatedAt < 4500) return;\n            lastTranslated = finalText;\n            lastTranslatedAt = now;\n            actionCooldownUntil = now + 2500;\n            translateAndShow(finalText);\n        };\n        handler.postDelayed(pendingSelection, DEBOUNCE_MS);\n    }\n'''
new = '''    private void queueAutomaticTranslation(String raw) {\n        if (isAutomaticTranslationEnabled()) queueTranslation(raw, true);\n    }\n\n    private void queueTranslation(String raw) {\n        queueTranslation(raw, false);\n    }\n\n    private void queueTranslation(String raw, boolean automatic) {\n        if (automatic && !isAutomaticTranslationEnabled()) return;\n        String text = normalize(raw);\n        if (text == null) return;\n        candidate = text;\n        if (pendingSelection != null) handler.removeCallbacks(pendingSelection);\n        pendingSelection = () -> {\n            if (automatic && !isAutomaticTranslationEnabled()) return;\n            String finalText = candidate;\n            if (finalText == null) return;\n            long now = SystemClock.uptimeMillis();\n            if (finalText.equals(lastTranslated) && now - lastTranslatedAt < 4500) return;\n            lastTranslated = finalText;\n            lastTranslatedAt = now;\n            actionCooldownUntil = now + 2500;\n            translateAndShow(finalText);\n        };\n        handler.postDelayed(pendingSelection, DEBOUNCE_MS);\n    }\n'''
if old not in s:
    raise RuntimeError('queueTranslation block not found')
s = s.replace(old, new, 1)
s = s.replace('Open Dual Translate v6 and add your Google Cloud Translation API key.',
              'Open Dual Translate v16 and add your Google Cloud Translation API key.')
s = s.replace('v7: clipboard changed while ElevenReader is active.',
              'v16: clipboard changed while ElevenReader is active.')
s = s.replace('Dual Translate v15', 'Dual Translate v16').replace('v15:', 'v16:')
p.write_text(s)

# New separately installable version.
p = root / 'app/build.gradle'
s = p.read_text().replace("applicationId 'lt.skarda.dualtranslate.v15'", "applicationId 'lt.skarda.dualtranslate.v16'")
s = s.replace('versionCode 15', 'versionCode 16').replace("versionName '15.0'", "versionName '16.0'")
p.write_text(s)
for name in ['app/src/main/AndroidManifest.xml', 'app/src/main/res/values/strings.xml',
             'app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java',
             'app/src/main/java/lt/skarda/dualtranslate/ClipboardCaptureActivity.java']:
    p = root / name
    p.write_text(p.read_text().replace('Dual Translate v15', 'Dual Translate v16'))
