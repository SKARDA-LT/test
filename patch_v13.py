from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')

svc=root/'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s=svc.read_text()

# Imports for Accessibility screenshot + on-device OCR.
s=s.replace('import android.graphics.Color;\n', 'import android.graphics.Color;\nimport android.graphics.Bitmap;\n')
s=s.replace('import android.os.Handler;\n', 'import android.os.Handler;\nimport android.os.Build;\n')
s=s.replace('import android.view.Gravity;\n', 'import android.view.Gravity;\nimport android.view.Display;\n')
s=s.replace('import java.util.Locale;\n', '''import java.util.Locale;\nimport java.util.ArrayList;\nimport java.util.Collections;\n\nimport com.google.mlkit.vision.common.InputImage;\nimport com.google.mlkit.vision.text.Text;\nimport com.google.mlkit.vision.text.TextRecognition;\nimport com.google.mlkit.vision.text.TextRecognizer;\nimport com.google.mlkit.vision.text.latin.TextRecognizerOptions;\n''')

# v13 OCR state.
s=s.replace('    private long elevenToolbarSeenAt;\n', '    private long elevenToolbarSeenAt;\n    private long elevenOcrCooldownUntil;\n    private Rect lastElevenToolbarRect = new Rect();\n')

# Replace the v12 automatic-copy method with screenshot OCR trigger.
start=s.find('    private void tryElevenReaderAutoCopy() {')
end=s.find('    private boolean dispatchTap(', start)
if start < 0 or end < 0:
    raise RuntimeError('Could not locate v12 ElevenReader auto block')
replacement=r'''    private void tryElevenReaderAutoCopy() {
        long now = SystemClock.uptimeMillis();
        if (now < elevenOcrCooldownUntil) return;

        String activePackage = lastForegroundPackage;
        try {
            AccessibilityNodeInfo active = getRootInActiveWindow();
            if (active != null && active.getPackageName() != null) activePackage = active.getPackageName().toString();
        } catch (Exception ignored) {}
        if (!ELEVEN_READER_PACKAGE.equals(activePackage)) return;

        Rect toolbar = findElevenToolbarBounds();
        if (toolbar == null) return;
        lastElevenToolbarRect.set(toolbar);
        elevenOcrCooldownUntil = now + 1800;
        saveDiagnostic("v13: ElevenReader selection toolbar detected. Reading the highlighted word directly from the screen; no Copy action is required.");
        handler.postDelayed(this::requestElevenScreenshotOcr, 120);
    }

    private Rect findElevenToolbarBounds() {
        try {
            java.util.List<AccessibilityWindowInfo> windows = getWindows();
            if (windows == null) return null;
            for (AccessibilityWindowInfo w : windows) {
                AccessibilityNodeInfo root = null;
                try { root = w.getRoot(); } catch (Exception ignored) {}
                if (root == null) continue;
                AccessibilityNodeInfo copy = findNode(root, "Copy", true);
                AccessibilityNodeInfo all = findNode(root, "Select all", true);
                AccessibilityNodeInfo pron = findNode(root, "Add pronunciation", true);
                if (copy == null || all == null || pron == null) continue;
                Rect result = new Rect();
                Rect r = new Rect();
                copy.getBoundsInScreen(result);
                all.getBoundsInScreen(r); result.union(r);
                pron.getBoundsInScreen(r); result.union(r);
                return result.isEmpty() ? null : result;
            }
        } catch (Exception ignored) {}
        return null;
    }

    private void requestElevenScreenshotOcr() {
        if (Build.VERSION.SDK_INT < 30) {
            saveDiagnostic("v13: Android version does not support Accessibility screenshots. Manual Copy remains available.");
            return;
        }
        try {
            takeScreenshot(Display.DEFAULT_DISPLAY, getMainExecutor(), new TakeScreenshotCallback() {
                @Override public void onSuccess(ScreenshotResult screenshot) {
                    Bitmap hw = null;
                    Bitmap bitmap = null;
                    try {
                        hw = Bitmap.wrapHardwareBuffer(screenshot.getHardwareBuffer(), screenshot.getColorSpace());
                        if (hw != null) bitmap = hw.copy(Bitmap.Config.ARGB_8888, false);
                    } catch (Exception e) {
                        saveDiagnostic("v13: could not convert Accessibility screenshot: " + e.getClass().getSimpleName());
                    } finally {
                        try { screenshot.getHardwareBuffer().close(); } catch (Exception ignored) {}
                    }
                    if (bitmap == null) return;
                    recognizeElevenSelection(bitmap);
                }

                @Override public void onFailure(int errorCode) {
                    saveDiagnostic("v13: Accessibility screenshot failed, code=" + errorCode + ". Manual Copy still works.");
                }
            });
        } catch (Exception e) {
            saveDiagnostic("v13: Accessibility screenshot exception: " + e.getClass().getSimpleName());
        }
    }

    private void recognizeElevenSelection(Bitmap bitmap) {
        TextRecognizer recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
        InputImage image = InputImage.fromBitmap(bitmap, 0);
        recognizer.process(image)
                .addOnSuccessListener(result -> {
                    try {
                        String selected = chooseHighlightedOcrText(result, bitmap);
                        if (selected != null && !selected.trim().isEmpty()) {
                            saveDiagnostic("v13: screen selection recognized automatically: “" + trimForLog(selected) + "”");
                            queueTranslation(selected);
                        } else {
                            saveDiagnostic("v13: toolbar was detected, but highlighted text could not be identified confidently. Manual Copy remains available.");
                        }
                    } finally {
                        try { recognizer.close(); } catch (Exception ignored) {}
                        try { bitmap.recycle(); } catch (Exception ignored) {}
                    }
                })
                .addOnFailureListener(e -> {
                    saveDiagnostic("v13: on-device text recognition failed: " + e.getClass().getSimpleName());
                    try { recognizer.close(); } catch (Exception ignored) {}
                    try { bitmap.recycle(); } catch (Exception ignored) {}
                });
    }

    private String chooseHighlightedOcrText(Text result, Bitmap bitmap) {
        if (result == null) return null;
        ArrayList<Text.Element> elements = new ArrayList<>();
        Rect ocrCopy = null;
        for (Text.TextBlock block : result.getTextBlocks()) {
            for (Text.Line line : block.getLines()) {
                for (Text.Element el : line.getElements()) {
                    String t = el.getText() == null ? "" : el.getText().trim();
                    if (t.isEmpty()) continue;
                    elements.add(el);
                    if ("copy".equalsIgnoreCase(t)) {
                        Rect b = el.getBoundingBox();
                        if (b != null) ocrCopy = new Rect(b);
                    }
                }
            }
        }
        if (elements.isEmpty()) return null;

        Rect toolbar = new Rect(lastElevenToolbarRect);
        if (ocrCopy != null) {
            // OCR gives us an additional reliable anchor even when Accessibility node bounds are odd.
            int h = Math.max(ocrCopy.height() * 3, dp(54));
            int w = Math.max(dp(430), ocrCopy.width() * 9);
            toolbar.set(Math.max(0, ocrCopy.left - dp(45)), Math.max(0, ocrCopy.centerY() - h / 2),
                    Math.min(bitmap.getWidth(), ocrCopy.left - dp(45) + w), Math.min(bitmap.getHeight(), ocrCopy.centerY() + h / 2));
        }

        double pageLum = estimatePageBackground(bitmap);
        Text.Element best = null;
        double bestScore = -1e9;
        double bestContrast = 0;

        for (Text.Element el : elements) {
            String t = el.getText() == null ? "" : el.getText().trim();
            Rect b = el.getBoundingBox();
            if (b == null || b.isEmpty() || !containsLetter(t)) continue;
            String low = t.toLowerCase(Locale.ROOT);
            if (low.equals("copy") || low.equals("select") || low.equals("all") || low.equals("add") || low.equals("pronunciation")) continue;
            if (!toolbar.isEmpty() && Rect.intersects(expanded(toolbar, dp(18), bitmap), b)) continue;

            double localLum = medianLuminance(bitmap, b);
            double contrast = Math.abs(localLum - pageLum);
            double distance = toolbar.isEmpty() ? 0 : rectDistance(b, toolbar);
            if (distance > dp(420)) continue;

            // Highlighted text has a mid-tone selection background; ordinary book text has page background.
            double score = contrast * 5.0 - distance * 0.22 - Math.max(0, t.length() - 24) * 1.5;
            if (score > bestScore) {
                bestScore = score;
                best = el;
                bestContrast = contrast;
            }
        }

        if (best == null || bestContrast < 16.0) return null;

        // Expand to adjacent highlighted words on the same visual line, so short phrases also work.
        Rect bb = best.getBoundingBox();
        ArrayList<Text.Element> phrase = new ArrayList<>();
        for (Text.Element el : elements) {
            Rect b = el.getBoundingBox();
            if (b == null || b.isEmpty()) continue;
            String t = el.getText() == null ? "" : el.getText().trim();
            if (!containsLetter(t)) continue;
            String low = t.toLowerCase(Locale.ROOT);
            if (low.equals("copy") || low.equals("select") || low.equals("all") || low.equals("add") || low.equals("pronunciation")) continue;
            double contrast = Math.abs(medianLuminance(bitmap, b) - pageLum);
            boolean sameLine = Math.abs(b.centerY() - bb.centerY()) <= Math.max(bb.height(), b.height());
            boolean near = b.right >= bb.left - dp(230) && b.left <= bb.right + dp(230);
            if (sameLine && near && contrast >= Math.max(14.0, bestContrast * 0.55)) phrase.add(el);
        }
        if (phrase.isEmpty()) return best.getText().trim();
        Collections.sort(phrase, (a,b) -> Integer.compare(a.getBoundingBox().left, b.getBoundingBox().left));
        StringBuilder out = new StringBuilder();
        for (Text.Element el : phrase) {
            if (out.length() > 0) out.append(' ');
            out.append(el.getText().trim());
        }
        String value = out.toString().replaceAll("\\s+", " ").trim();
        return value.isEmpty() ? best.getText().trim() : value;
    }

    private boolean containsLetter(String s) {
        if (s == null) return false;
        for (int i = 0; i < s.length(); i++) if (Character.isLetter(s.charAt(i))) return true;
        return false;
    }

    private Rect expanded(Rect r, int pad, Bitmap bitmap) {
        return new Rect(Math.max(0, r.left-pad), Math.max(0, r.top-pad),
                Math.min(bitmap.getWidth(), r.right+pad), Math.min(bitmap.getHeight(), r.bottom+pad));
    }

    private double rectDistance(Rect a, Rect b) {
        int dx = Math.max(0, Math.max(b.left - a.right, a.left - b.right));
        int dy = Math.max(0, Math.max(b.top - a.bottom, a.top - b.bottom));
        return Math.sqrt((double)dx*dx + (double)dy*dy);
    }

    private double estimatePageBackground(Bitmap bitmap) {
        ArrayList<Integer> vals = new ArrayList<>();
        int w = bitmap.getWidth(), h = bitmap.getHeight();
        for (int y = h/5; y < h*4/5; y += Math.max(18, h/45)) {
            addLum(vals, bitmap, Math.max(2, w/40), y);
            addLum(vals, bitmap, Math.min(w-3, w-w/40), y);
        }
        if (vals.isEmpty()) return 0;
        Collections.sort(vals);
        return vals.get(vals.size()/2);
    }

    private double medianLuminance(Bitmap bitmap, Rect box) {
        Rect r = new Rect(Math.max(0, box.left), Math.max(0, box.top),
                Math.min(bitmap.getWidth(), box.right), Math.min(bitmap.getHeight(), box.bottom));
        ArrayList<Integer> vals = new ArrayList<>();
        int sx = Math.max(2, r.width()/14);
        int sy = Math.max(2, r.height()/10);
        for (int y=r.top; y<r.bottom; y+=sy) {
            for (int x=r.left; x<r.right; x+=sx) addLum(vals, bitmap, x, y);
        }
        if (vals.isEmpty()) return 0;
        Collections.sort(vals);
        return vals.get(vals.size()/2);
    }

    private void addLum(ArrayList<Integer> vals, Bitmap bitmap, int x, int y) {
        try {
            int c = bitmap.getPixel(x, y);
            int lum = (Color.red(c)*299 + Color.green(c)*587 + Color.blue(c)*114) / 1000;
            vals.add(lum);
        } catch (Exception ignored) {}
    }

'''
s=s[:start]+replacement+s[end:]

# Replace the older ElevenReader toolbar auto-click block in inspectWindowRoot with OCR trigger only.
block_start=s.find('        // ElevenReader renders its own selection toolbar')
block_end=s.find('        AccessibilityNodeInfo copy = findNode(root, "Copy", true);', block_start)
if block_start < 0 or block_end < 0:
    raise RuntimeError('Could not locate inspectWindowRoot ElevenReader block')
new_block=r'''        // ElevenReader exposes the toolbar labels but hides the selected text range and rejects
        // programmatic Copy. v13 therefore reads the highlighted text visually from an Accessibility screenshot.
        if (now < elevenReaderSeenUntil) {
            AccessibilityNodeInfo erCopy = findNode(root, "Copy", true);
            AccessibilityNodeInfo erSelectAll = findNode(root, "Select all", true);
            AccessibilityNodeInfo erPronunciation = findNode(root, "Add pronunciation", true);
            if (erCopy != null && erSelectAll != null && erPronunciation != null) {
                if (now >= elevenOcrCooldownUntil) {
                    Rect tr = new Rect();
                    Rect rr = new Rect();
                    try {
                        erCopy.getBoundsInScreen(tr);
                        erSelectAll.getBoundsInScreen(rr); tr.union(rr);
                        erPronunciation.getBoundsInScreen(rr); tr.union(rr);
                        lastElevenToolbarRect.set(tr);
                    } catch (Exception ignored) {}
                    elevenOcrCooldownUntil = now + 1800;
                    saveDiagnostic("v13: ElevenReader toolbar detected. Capturing screen to read the highlighted selection directly.");
                    handler.postDelayed(this::requestElevenScreenshotOcr, 120);
                }
                return true;
            }
        }

'''
s=s[:block_start]+new_block+s[block_end:]

s=s.replace('v12 service connected. Gmail uses normal Android selection. In ElevenReader v12 uses Android Accessibility ACTION_COPY on the selected text node; manual Copy remains a fallback.',
'''v13 service connected. Gmail uses normal Android selection. ElevenReader highlighted text is read from an Accessibility screenshot with on-device OCR; manual Copy remains a fallback.''')
svc.write_text(s)

# Add bundled ML Kit Latin text recognizer.
b=root/'app/build.gradle'
t=b.read_text()
t=t.replace("applicationId 'lt.skarda.dualtranslate.v12'", "applicationId 'lt.skarda.dualtranslate.v13'").replace('versionCode 12','versionCode 13').replace("versionName '12.0'","versionName '13.0'")
if 'com.google.mlkit:text-recognition' not in t:
    t += "\n\ndependencies {\n    implementation 'com.google.mlkit:text-recognition:16.0.1'\n}\n"
b.write_text(t)

# ML Kit depends on AndroidX; enable it inside the reconstructed project itself.
gp=root/'gradle.properties'
gpt=gp.read_text() if gp.exists() else ''
if 'android.useAndroidX=true' not in gpt:
    gp.write_text(gpt.rstrip() + '\nandroid.useAndroidX=true\n')

# AccessibilityService.takeScreenshot requires this declared capability.
xml=root/'app/src/main/res/xml/accessibility_service_config.xml'
x=xml.read_text()
if 'android:canTakeScreenshot=' not in x:
    x=x.replace('    android:canRetrieveWindowContent="true"\n', '    android:canRetrieveWindowContent="true"\n    android:canTakeScreenshot="true"\n')
xml.write_text(x)

for fp in ['app/src/main/AndroidManifest.xml','app/src/main/res/values/strings.xml','app/src/main/java/lt/skarda/dualtranslate/MainActivity.java','app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java']:
    q=root/fp
    z=q.read_text().replace('Dual Translate v12','Dual Translate v13')
    z=z.replace('uses Android Accessibility ACTION_COPY directly on the selected ElevenReader text node. Manual Copy still works as a fallback.',
                'reads the highlighted ElevenReader selection from an Accessibility screenshot using on-device OCR. Manual Copy still works as a fallback.')
    q.write_text(z)