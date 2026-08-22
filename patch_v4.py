from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
p = root / 'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s = p.read_text()

s = s.replace('    private static final String ELEVEN_READER_PACKAGE = "io.elevenlabs.readerapp";\n', '    private static final String ELEVEN_READER_PACKAGE = "io.elevenlabs.readerapp";\n    private static final String CHATGPT_PACKAGE = "com.openai.chatgpt";\n')
s = s.replace('    private long armedUntil;\n    private long actionCooldownUntil;\n    private long overflowCooldownUntil;\n    private long shareFallbackAfter;\n', '    private long actionCooldownUntil;\n')
s = s.replace('    private long copyFallbackCooldownUntil;\n', '    private long copyFallbackCooldownUntil;\n    private long chatGptArmedUntil;\n    private long chatGptToolbarFirstSeen;\n    private long chatGptCopyCooldownUntil;\n')
s = s.replace('saveDiagnostic("v3 service connected. Standard selection is enabled for all apps; ElevenReader also uses an automatic Copy capture fallback.");', 'saveDiagnostic("v4 service connected. Standard non-editable text selection is enabled for all apps. ElevenReader uses a dedicated automatic Copy fallback. Generic Share/More automation is disabled.");')

start = s.index('    @Override\n    public void onAccessibilityEvent(AccessibilityEvent event) {')
end = s.index('    private void scheduleScans(long... delays) {', start)
new_method = '''    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) return;
        CharSequence pkgCs = event.getPackageName();
        String pkg = pkgCs == null ? "" : pkgCs.toString();
        if (pkg.equals(getPackageName())) return;

        int type = event.getEventType();
        long now = SystemClock.uptimeMillis();
        boolean isElevenReader = ELEVEN_READER_PACKAGE.equals(pkg);
        boolean isChatGpt = CHATGPT_PACKAGE.equals(pkg);
        if (isElevenReader) elevenReaderSeenUntil = now + 9000;

        if (type == AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED) {
            AccessibilityNodeInfo src = event.getSource();
            if (isEditableNode(src)) {
                saveDiagnostic(describeEvent(event, "Ignored selection inside an editable text field"));
                return;
            }
            String selected = extractFromEvent(event);
            saveDiagnostic(describeEvent(event, selected == null ? "SELECTION event; Android did not expose the selected characters" : "SELECTION: “" + trimForLog(selected) + "”"));
            if (selected != null) queueTranslation(selected);
            if (isElevenReader) scheduleCustomScans(100, 300, 620, 950);
            else handler.postDelayed(this::scanActiveWindowForSelection, 120);
            return;
        }

        if (type == AccessibilityEvent.TYPE_VIEW_LONG_CLICKED) {
            AccessibilityNodeInfo src = event.getSource();
            if (isEditableNode(src)) {
                saveDiagnostic(describeEvent(event, "Ignored long-click inside an editable text field"));
                return;
            }
            if (isChatGpt) chatGptArmedUntil = now + 5000;
            saveDiagnostic(describeEvent(event, isElevenReader ? "ElevenReader long-click — looking only for its custom Copy toolbar" : "LONG CLICK — checking for selected non-editable text"));
            if (isElevenReader || isChatGpt) scheduleCustomScans(140, 360, 680, 1000);
            handler.postDelayed(this::scanActiveWindowForSelection, 140);
            return;
        }

        if (type == AccessibilityEvent.TYPE_TOUCH_INTERACTION_END) {
            handler.postDelayed(this::scanActiveWindowForSelection, 120);
            if (isElevenReader || (isChatGpt && now < chatGptArmedUntil)) scheduleCustomScans(160, 420, 760);
            return;
        }

        if (type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED ||
                type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
                type == AccessibilityEvent.TYPE_WINDOWS_CHANGED) {
            if (isElevenReader || (isChatGpt && now < chatGptArmedUntil)) handler.postDelayed(this::scanForCustomSelectionUi, 100);
            return;
        }

        if (type == AccessibilityEvent.TYPE_VIEW_CLICKED) {
            if (isElevenReader) handler.postDelayed(this::scanForCustomSelectionUi, 120);
        }
    }

    private void scheduleCustomScans(long... delays) {
        for (long d : delays) handler.postDelayed(this::scanForCustomSelectionUi, d);
    }

'''
s = s[:start] + new_method + s[end:]
start2 = s.index('    private void scheduleScans(long... delays) {')
end2 = s.index('    @Override\n    public void onInterrupt()', start2)
s = s[:start2] + s[end2:]

s = s.replace('    private String extractFromNode(AccessibilityNodeInfo node) {\n        if (node == null) return null;\n', '    private String extractFromNode(AccessibilityNodeInfo node) {\n        if (node == null || isEditableNode(node)) return null;\n')

start = s.index('    private void scanForSelectionUi() {')
end = s.index('    private void launchClipboardCapture()', start)
custom = '''    private void scanForCustomSelectionUi() {
        long now = SystemClock.uptimeMillis();
        if (now < actionCooldownUntil) return;

        List<AccessibilityWindowInfo> windows;
        try { windows = getWindows(); } catch (Exception e) { windows = null; }
        if (windows == null || windows.isEmpty()) {
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root != null) inspectCustomSelectionRoot(root, now);
            return;
        }
        for (AccessibilityWindowInfo w : windows) {
            AccessibilityNodeInfo root = w.getRoot();
            if (root != null && inspectCustomSelectionRoot(root, now)) return;
        }
    }

    private boolean inspectCustomSelectionRoot(AccessibilityNodeInfo root, long now) {
        if (now < elevenReaderSeenUntil) {
            AccessibilityNodeInfo erCopy = findNode(root, "Copy", true);
            AccessibilityNodeInfo erSelectAll = findNode(root, "Select all", true);
            AccessibilityNodeInfo erPronunciation = findNode(root, "Add pronunciation", true);
            boolean elevenToolbar = erCopy != null && erSelectAll != null && erPronunciation != null;
            if (elevenToolbar) {
                if (elevenToolbarFirstSeen == 0) {
                    elevenToolbarFirstSeen = now;
                    saveDiagnostic("ElevenReader custom selection toolbar detected. Waiting briefly for the selection handles to settle.");
                    handler.postDelayed(this::scanForCustomSelectionUi, 520);
                    return true;
                }
                if (now - elevenToolbarFirstSeen >= 430 && now >= copyFallbackCooldownUntil) {
                    if (clickNodeOrParent(erCopy)) {
                        copyFallbackCooldownUntil = now + 4200;
                        actionCooldownUntil = now + 900;
                        elevenToolbarFirstSeen = 0;
                        saveDiagnostic("ElevenReader fallback: clicked Copy automatically; capturing only that selected phrase.");
                        handler.postDelayed(this::launchClipboardCapture, 170);
                        return true;
                    }
                }
            } else if (elevenToolbarFirstSeen != 0 && now - elevenToolbarFirstSeen > 2200) {
                elevenToolbarFirstSeen = 0;
            }
        }

        if (now < chatGptArmedUntil && !hasFocusedEditableNode(root)) {
            AccessibilityNodeInfo copy = findNode(root, "Copy", true);
            AccessibilityNodeInfo selectAll = findNode(root, "Select all", true);
            if (copy != null && selectAll != null) {
                if (chatGptToolbarFirstSeen == 0) {
                    chatGptToolbarFirstSeen = now;
                    handler.postDelayed(this::scanForCustomSelectionUi, 500);
                    return true;
                }
                if (now - chatGptToolbarFirstSeen >= 400 && now >= chatGptCopyCooldownUntil) {
                    if (clickNodeOrParent(copy)) {
                        chatGptCopyCooldownUntil = now + 4200;
                        actionCooldownUntil = now + 900;
                        chatGptToolbarFirstSeen = 0;
                        saveDiagnostic("ChatGPT selected-text fallback: clicked Copy automatically after a non-editable long press.");
                        handler.postDelayed(this::launchClipboardCapture, 170);
                        return true;
                    }
                }
            }
        }
        return false;
    }

    private boolean isEditableNode(AccessibilityNodeInfo node) {
        if (node == null) return false;
        try {
            if (node.isEditable()) return true;
            CharSequence cls = node.getClassName();
            if (cls != null) {
                String c = cls.toString();
                if (c.contains("EditText") || c.contains("TextInput")) return true;
            }
        } catch (Exception ignored) {}
        return false;
    }

    private boolean hasFocusedEditableNode(AccessibilityNodeInfo root) {
        if (root == null) return false;
        Deque<AccessibilityNodeInfo> q = new ArrayDeque<>();
        q.add(root);
        int visited = 0;
        while (!q.isEmpty() && visited < 1200) {
            AccessibilityNodeInfo n = q.removeFirst();
            visited++;
            try { if (n.isFocused() && isEditableNode(n)) return true; } catch (Exception ignored) {}
            for (int i = 0; i < n.getChildCount(); i++) {
                AccessibilityNodeInfo c = n.getChild(i);
                if (c != null) q.addLast(c);
            }
        }
        return false;
    }

'''
s = s[:start] + custom + s[end:]
s = s.replace('Open Dual Translate v3 and add your Google Cloud Translation API key.', 'Open Dual Translate v4 and add your Google Cloud Translation API key.')
p.write_text(s)

cap = root / 'app/src/main/java/lt/skarda/dualtranslate/ClipboardCaptureActivity.java'
cap.write_text(cap.read_text().replace('SelectionTranslateService.submitExternalSelection(text, "ElevenReader automatic Copy fallback");', 'SelectionTranslateService.submitExternalSelection(text, "Automatic Copy fallback");'))

manifest = root / 'app/src/main/AndroidManifest.xml'
manifest.write_text(manifest.read_text().replace('Dual Translate v3', 'Dual Translate v4'))

build = root / 'app/build.gradle'
b = build.read_text().replace("applicationId 'lt.skarda.dualtranslate.v3'", "applicationId 'lt.skarda.dualtranslate.v4'")
b = b.replace('versionCode 3', 'versionCode 4').replace("versionName '3.0'", "versionName '4.0'")
build.write_text(b)

main = root / 'app/src/main/java/lt/skarda/dualtranslate/MainActivity.java'
m = main.read_text().replace('Dual Translate v3', 'Dual Translate v4').replace('v3 automatically presses Copy', 'v4 automatically presses Copy')
m = m.replace('Clipboard is used only as an automatic ElevenReader fallback because ElevenReader does not expose its selected range through the normal Android selection API.', 'Clipboard is used only for package-specific automatic Copy fallbacks. Generic Share/More automation is disabled, and editable text fields are ignored.')
main.write_text(m)

recv = root / 'app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java'
recv.write_text(recv.read_text().replace('Dual Translate v3', 'Dual Translate v4'))
strings = root / 'app/src/main/res/values/strings.xml'
strings.write_text(strings.read_text().replace('Dual Translate v3', 'Dual Translate v4'))
