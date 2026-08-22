from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
svc = root / 'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s = svc.read_text()

start = s.find('    private String chooseHighlightedOcrText(Text result, Bitmap bitmap) {')
end = s.find('    private boolean containsLetter(String s) {', start)
if start < 0 or end < 0:
    raise RuntimeError('Could not locate v14 OCR selection method')

replacement = r'''    private static final class OcrSelectionToken {
        final String text;
        final Rect box;
        final int lineOrder;
        final double grayRatio;

        OcrSelectionToken(String text, Rect box, int lineOrder, double grayRatio) {
            this.text = text;
            this.box = box;
            this.lineOrder = lineOrder;
            this.grayRatio = grayRatio;
        }
    }

    private static final class VisibleTextCandidate {
        final String text;
        final Rect box;

        VisibleTextCandidate(String text, Rect box) {
            this.text = text;
            this.box = box;
        }
    }

    private static final class WordToken {
        final String original;
        final String normalized;

        WordToken(String original, String normalized) {
            this.original = original;
            this.normalized = normalized;
        }
    }

    private static final class MatchWindow {
        final String text;
        final double score;

        MatchWindow(String text, double score) {
            this.text = text;
            this.score = score;
        }
    }

    private String chooseHighlightedOcrText(Text result, Bitmap bitmap) {
        if (result == null || bitmap == null) return null;

        // ElevenReader uses a neutral grey background for the user's Android text selection.
        // Its playback/current-reading highlight is blue. v15 classifies the background under
        // every OCR word instead of selecting whichever OCR word merely happens to be closest
        // to the floating toolbar.
        ArrayList<OcrSelectionToken> selected = new ArrayList<>();
        Rect toolbar = new Rect(lastElevenToolbarRect);
        int lineOrder = 0;

        for (Text.TextBlock block : result.getTextBlocks()) {
            for (Text.Line line : block.getLines()) {
                for (Text.Element element : line.getElements()) {
                    String text = element.getText() == null ? "" : element.getText().trim();
                    Rect box = element.getBoundingBox();
                    if (text.isEmpty() || box == null || box.isEmpty() || !containsLetter(text)) continue;
                    if (isSelectionToolbarWord(text)) continue;

                    double grayRatio = manualSelectionGrayRatio(bitmap, box);
                    double distance = toolbar.isEmpty() ? 0.0 : rectDistance(box, toolbar);

                    // The selected background produces a ratio around 0.8-1.0. Normal black
                    // book text, the dark toolbar, and ElevenReader's blue reading highlight
                    // remain far below this threshold.
                    if (grayRatio >= 0.34 && (toolbar.isEmpty() || distance <= dp(260))) {
                        selected.add(new OcrSelectionToken(text, new Rect(box), lineOrder, grayRatio));
                    }
                }
                lineOrder++;
            }
        }

        if (selected.isEmpty()) {
            saveDiagnostic("v15: selection toolbar detected, but no neutral-grey selected text was found. Manual Copy remains available.");
            return null;
        }

        selected = keepConnectedSelectionCluster(selected, toolbar);
        if (selected.isEmpty()) return null;

        Collections.sort(selected, (a, b) -> {
            if (a.lineOrder != b.lineOrder) return Integer.compare(a.lineOrder, b.lineOrder);
            return Integer.compare(a.box.left, b.box.left);
        });

        Rect selectionBounds = new Rect();
        StringBuilder approximateBuilder = new StringBuilder();
        int lastLine = -1;
        for (OcrSelectionToken token : selected) {
            if (selectionBounds.isEmpty()) selectionBounds.set(token.box); else selectionBounds.union(token.box);
            appendOcrToken(approximateBuilder, token.text, lastLine != token.lineOrder && lastLine >= 0);
            lastLine = token.lineOrder;
        }

        String approximate = normalize(approximateBuilder.toString());
        if (approximate == null) return null;

        // OCR can be partially obstructed by the white selection handles. ElevenReader normally
        // still exposes the complete page/paragraph text to Accessibility even though it hides
        // the selected range. Fuzzy-align the grey-selected OCR words with that exact source text
        // to restore words hidden by a handle and preserve the precise beginning and ending.
        String exact = recoverExactSelectionFromAccessibility(approximate, selectionBounds, selected.size());
        if (exact != null && !exact.trim().isEmpty()) {
            saveDiagnostic("v15: exact selected text recovered: “" + trimForLog(exact) + "” (OCR was “" + trimForLog(approximate) + "”).");
            return exact;
        }

        saveDiagnostic("v15: exact selected text read from grey highlight: “" + trimForLog(approximate) + "”.");
        return approximate;
    }

    private boolean isSelectionToolbarWord(String text) {
        String low = text == null ? "" : text.trim().toLowerCase(Locale.ROOT);
        return low.equals("copy") || low.equals("select") || low.equals("all") ||
                low.equals("add") || low.equals("pronunciation") ||
                low.equals("select all") || low.equals("add pronunciation");
    }

    private double manualSelectionGrayRatio(Bitmap bitmap, Rect original) {
        int pad = Math.max(2, dp(1));
        Rect box = new Rect(
                Math.max(0, original.left - pad),
                Math.max(0, original.top - pad),
                Math.min(bitmap.getWidth(), original.right + pad),
                Math.min(bitmap.getHeight(), original.bottom + pad));
        if (box.isEmpty()) return 0.0;

        int stepX = Math.max(1, box.width() / 24);
        int stepY = Math.max(1, box.height() / 16);
        int valid = 0;
        int neutralGrey = 0;

        for (int y = box.top; y < box.bottom; y += stepY) {
            for (int x = box.left; x < box.right; x += stepX) {
                int c;
                try { c = bitmap.getPixel(x, y); } catch (Exception ignored) { continue; }
                int r = Color.red(c), g = Color.green(c), b = Color.blue(c);
                int lum = (r * 299 + g * 587 + b * 114) / 1000;

                // Ignore the white letters and white drag handles; classify the background.
                if (lum > 228) continue;
                valid++;

                int max = Math.max(r, Math.max(g, b));
                int min = Math.min(r, Math.min(g, b));
                int chroma = max - min;
                if (lum >= 52 && lum <= 190 && chroma <= 28) neutralGrey++;
            }
        }
        return valid == 0 ? 0.0 : (double) neutralGrey / (double) valid;
    }

    private ArrayList<OcrSelectionToken> keepConnectedSelectionCluster(ArrayList<OcrSelectionToken> all, Rect toolbar) {
        if (all.size() <= 1) return all;

        OcrSelectionToken anchor = all.get(0);
        double bestDistance = toolbar.isEmpty() ? 0.0 : rectDistance(anchor.box, toolbar);
        for (OcrSelectionToken token : all) {
            double d = toolbar.isEmpty() ? -token.grayRatio : rectDistance(token.box, toolbar);
            if (d < bestDistance) {
                bestDistance = d;
                anchor = token;
            }
        }

        ArrayList<OcrSelectionToken> cluster = new ArrayList<>();
        cluster.add(anchor);
        boolean changed;
        do {
            changed = false;
            for (OcrSelectionToken candidate : all) {
                if (cluster.contains(candidate)) continue;
                for (OcrSelectionToken member : cluster) {
                    int lineGap = Math.abs(candidate.lineOrder - member.lineOrder);
                    int verticalGap = Math.max(0, Math.max(member.box.top - candidate.box.bottom, candidate.box.top - member.box.bottom));
                    int allowedGap = Math.max(dp(22), Math.max(member.box.height(), candidate.box.height()) * 2);
                    if (lineGap <= 2 && verticalGap <= allowedGap) {
                        cluster.add(candidate);
                        changed = true;
                        break;
                    }
                }
            }
        } while (changed);

        // In case ML Kit assigned unusual block order, include any additional grey-selected word
        // whose physical bounds are immediately adjacent to the selected cluster.
        Rect union = new Rect();
        for (OcrSelectionToken token : cluster) {
            if (union.isEmpty()) union.set(token.box); else union.union(token.box);
        }
        Rect expandedUnion = new Rect(
                Math.max(0, union.left - dp(80)),
                Math.max(0, union.top - dp(70)),
                union.right + dp(80),
                union.bottom + dp(70));
        for (OcrSelectionToken token : all) {
            if (!cluster.contains(token) && Rect.intersects(expandedUnion, token.box)) cluster.add(token);
        }
        return cluster;
    }

    private void appendOcrToken(StringBuilder out, String token, boolean newLine) {
        String value = token == null ? "" : token.trim();
        if (value.isEmpty()) return;
        if (out.length() == 0) {
            out.append(value);
            return;
        }
        boolean punctuationOnly = value.matches("^[,.;:!?%\\)\\]\\}]+$");
        char previous = out.charAt(out.length() - 1);
        boolean afterOpening = previous == '(' || previous == '[' || previous == '{' || previous == '“' || previous == '‘';
        if (!punctuationOnly && !afterOpening) out.append(' ');
        out.append(value);
    }

    private String recoverExactSelectionFromAccessibility(String approximate, Rect selectionBounds, int expectedWordCount) {
        ArrayList<VisibleTextCandidate> candidates = new ArrayList<>();
        try {
            AccessibilityNodeInfo active = getRootInActiveWindow();
            if (active != null) collectVisibleElevenText(active, candidates, selectionBounds, 0);
        } catch (Exception ignored) {}
        try {
            java.util.List<AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                for (AccessibilityWindowInfo window : windows) {
                    try {
                        AccessibilityNodeInfo root = window.getRoot();
                        if (root != null) collectVisibleElevenText(root, candidates, selectionBounds, 0);
                    } catch (Exception ignored) {}
                }
            }
        } catch (Exception ignored) {}

        if (candidates.isEmpty()) return null;
        Collections.sort(candidates, (a, b) -> {
            int top = Integer.compare(a.box.top, b.box.top);
            return top != 0 ? top : Integer.compare(a.box.left, b.box.left);
        });

        MatchWindow best = null;
        for (VisibleTextCandidate candidate : candidates) {
            MatchWindow match = findBestTextWindow(candidate.text, approximate, expectedWordCount);
            if (match != null && (best == null || match.score < best.score)) best = match;
        }

        // Some accessibility implementations expose each visual line as a separate node. Test
        // combinations of adjacent visible nodes so a selection spanning two or more lines is
        // recovered as one exact phrase.
        int count = Math.min(candidates.size(), 100);
        for (int i = 0; i < count; i++) {
            StringBuilder joined = new StringBuilder();
            Rect joinedBounds = new Rect();
            for (int j = i; j < Math.min(count, i + 7); j++) {
                VisibleTextCandidate candidate = candidates.get(j);
                if (!joinedBounds.isEmpty()) {
                    int gap = Math.max(0, candidate.box.top - joinedBounds.bottom);
                    if (gap > dp(180)) break;
                }
                if (joinedBounds.isEmpty()) joinedBounds.set(candidate.box); else joinedBounds.union(candidate.box);
                String normalizedCandidate = normalize(candidate.text);
                if (normalizedCandidate == null) continue;
                if (joined.length() > 0) joined.append(' ');
                joined.append(normalizedCandidate);
                MatchWindow match = findBestTextWindow(joined.toString(), approximate, expectedWordCount);
                if (match != null && (best == null || match.score < best.score)) best = match;
            }
        }

        if (best == null) return null;
        double limit = expectedWordCount <= 2 ? 0.56 : 0.46;
        return best.score <= limit ? normalize(best.text) : null;
    }

    private void collectVisibleElevenText(AccessibilityNodeInfo node,
                                          ArrayList<VisibleTextCandidate> out,
                                          Rect selectionBounds,
                                          int depth) {
        if (node == null || depth > 16 || out.size() >= 180) return;
        try {
            CharSequence pkgCs = node.getPackageName();
            String pkg = pkgCs == null ? "" : pkgCs.toString();
            if (ELEVEN_READER_PACKAGE.equals(pkg)) {
                Rect box = new Rect();
                try { node.getBoundsInScreen(box); } catch (Exception ignored) {}
                if (!box.isEmpty() && (selectionBounds == null || selectionBounds.isEmpty() ||
                        rectDistance(box, selectionBounds) <= dp(520) || Rect.intersects(box, selectionBounds))) {
                    addVisibleCandidate(node.getText(), box, out);
                    CharSequence description = node.getContentDescription();
                    if (description != null && (node.getText() == null ||
                            !description.toString().equals(node.getText().toString()))) {
                        addVisibleCandidate(description, box, out);
                    }
                }
            }

            int childCount = Math.min(node.getChildCount(), 120);
            for (int i = 0; i < childCount; i++) {
                AccessibilityNodeInfo child = null;
                try { child = node.getChild(i); } catch (Exception ignored) {}
                collectVisibleElevenText(child, out, selectionBounds, depth + 1);
            }
        } catch (Exception ignored) {}
    }

    private void addVisibleCandidate(CharSequence raw, Rect box, ArrayList<VisibleTextCandidate> out) {
        if (raw == null) return;
        String text = normalize(raw.toString());
        if (text == null || text.length() < 2 || isSelectionToolbarWord(text)) return;
        String low = text.toLowerCase(Locale.ROOT);
        if (low.equals("tap card to close") || low.equals("start") || low.matches("^\\d+[hm:s .-]*left$")) return;

        for (VisibleTextCandidate existing : out) {
            if (existing.text.equals(text) && rectDistance(existing.box, box) < dp(10)) return;
        }
        out.add(new VisibleTextCandidate(text, new Rect(box)));
    }

    private MatchWindow findBestTextWindow(String candidateText, String approximate, int expectedWordCount) {
        ArrayList<WordToken> candidate = splitWordTokens(candidateText);
        ArrayList<WordToken> target = splitWordTokens(approximate);
        if (candidate.isEmpty() || target.isEmpty()) return null;

        int expected = Math.max(1, expectedWordCount > 0 ? expectedWordCount : target.size());
        int minLength = expected == 1 ? 1 : Math.max(1, expected - 3);
        int maxLength = expected == 1 ? 1 : Math.min(candidate.size(), expected + 3);
        MatchWindow best = null;

        for (int length = minLength; length <= maxLength; length++) {
            for (int start = 0; start + length <= candidate.size(); start++) {
                ArrayList<WordToken> window = new ArrayList<>(candidate.subList(start, start + length));
                double sequence = tokenSequenceDistance(target, window);
                double boundary = 0.16 * (tokenDistance(target.get(0).normalized, window.get(0).normalized) +
                        tokenDistance(target.get(target.size() - 1).normalized, window.get(window.size() - 1).normalized));
                double lengthPenalty = 0.055 * Math.abs(length - expected);
                double score = sequence + boundary + lengthPenalty;
                if (best == null || score < best.score) {
                    StringBuilder exact = new StringBuilder();
                    for (WordToken token : window) {
                        if (exact.length() > 0) exact.append(' ');
                        exact.append(token.original);
                    }
                    best = new MatchWindow(exact.toString(), score);
                }
            }
        }
        return best;
    }

    private ArrayList<WordToken> splitWordTokens(String text) {
        ArrayList<WordToken> result = new ArrayList<>();
        if (text == null) return result;
        String cleaned = text.replace('\u00A0', ' ').replace('\n', ' ').replace('\r', ' ');
        for (String raw : cleaned.split("\\s+")) {
            if (raw == null || raw.trim().isEmpty()) continue;
            String normalized = normalizeWordToken(raw);
            if (!normalized.isEmpty()) result.add(new WordToken(raw.trim(), normalized));
        }
        return result;
    }

    private String normalizeWordToken(String raw) {
        if (raw == null) return "";
        String value = raw.toLowerCase(Locale.ROOT).replace('’', '\'').replace('‘', '\'');
        int start = 0;
        int end = value.length();
        while (start < end && !Character.isLetterOrDigit(value.charAt(start))) start++;
        while (end > start && !Character.isLetterOrDigit(value.charAt(end - 1))) end--;
        return start >= end ? "" : value.substring(start, end);
    }

    private double tokenSequenceDistance(ArrayList<WordToken> target, ArrayList<WordToken> candidate) {
        int n = target.size(), m = candidate.size();
        double[] previous = new double[m + 1];
        double[] current = new double[m + 1];
        for (int j = 0; j <= m; j++) previous[j] = j;

        for (int i = 1; i <= n; i++) {
            current[0] = i;
            for (int j = 1; j <= m; j++) {
                double substitution = previous[j - 1] + tokenDistance(target.get(i - 1).normalized, candidate.get(j - 1).normalized);
                double deletion = previous[j] + 1.0;
                double insertion = current[j - 1] + 1.0;
                current[j] = Math.min(substitution, Math.min(deletion, insertion));
            }
            double[] swap = previous;
            previous = current;
            current = swap;
        }
        return previous[m] / Math.max(1.0, Math.max(n, m));
    }

    private double tokenDistance(String a, String b) {
        if (a == null) a = "";
        if (b == null) b = "";
        if (a.equals(b)) return 0.0;
        int max = Math.max(a.length(), b.length());
        if (max == 0) return 0.0;
        return (double) characterEditDistance(a, b) / (double) max;
    }

    private int characterEditDistance(String a, String b) {
        int[] previous = new int[b.length() + 1];
        int[] current = new int[b.length() + 1];
        for (int j = 0; j <= b.length(); j++) previous[j] = j;
        for (int i = 1; i <= a.length(); i++) {
            current[0] = i;
            for (int j = 1; j <= b.length(); j++) {
                int cost = a.charAt(i - 1) == b.charAt(j - 1) ? 0 : 1;
                current[j] = Math.min(previous[j] + 1,
                        Math.min(current[j - 1] + 1, previous[j - 1] + cost));
            }
            int[] swap = previous;
            previous = current;
            current = swap;
        }
        return previous[b.length()];
    }

'''

s = s[:start] + replacement + s[end:]

# Remove the previous translation overlay before taking a new screenshot; otherwise an old card
# can cover the newly selected word near the top of the screen and confuse OCR.
needle = '''    private void requestElevenScreenshotOcr() {\n        if (Build.VERSION.SDK_INT < 30) {'''
replacement_request = '''    private void requestElevenScreenshotOcr() {\n        removePopup();\n        if (Build.VERSION.SDK_INT < 30) {'''
if needle not in s:
    raise RuntimeError('Could not locate screenshot request method')
s = s.replace(needle, replacement_request, 1)

s = s.replace('v14:', 'v15:')
s = s.replace('v14 service connected.', 'v15 service connected.')
svc.write_text(s)

b = root / 'app/build.gradle'
t = b.read_text()
t = t.replace("applicationId 'lt.skarda.dualtranslate.v14'", "applicationId 'lt.skarda.dualtranslate.v15'")
t = t.replace('versionCode 14', 'versionCode 15').replace("versionName '14.0'", "versionName '15.0'")
b.write_text(t)

for fp in [
    'app/src/main/AndroidManifest.xml',
    'app/src/main/res/values/strings.xml',
    'app/src/main/java/lt/skarda/dualtranslate/MainActivity.java',
    'app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java'
]:
    q = root / fp
    z = q.read_text().replace('Dual Translate v14', 'Dual Translate v15')
    q.write_text(z)
