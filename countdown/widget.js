// Countdown widget for the Scriptable app (iOS/iPadOS).
//
// Setup:
//   1. Install Scriptable (free, App Store).
//   2. Open Scriptable, tap "+", paste this whole file, name the script
//      "Countdown", save.
//   3. Long-press your home screen -> tap "+" -> find Scriptable -> pick a
//      size (Medium recommended) -> add it.
//   4. Long-press the new widget -> "Edit Widget" -> set Script to
//      "Countdown" -> set Parameter to "Occasion,MM/DD/YYYY",
//      e.g.  Christmas,12/25/2026
//
// The widget calls the live countdown app (rice-mgmt-803.onrender.com) to
// get a Claude-designed theme for the occasion, same as the web app. iOS
// refreshes widgets roughly every 15-60 minutes, not every second, so the
// countdown updates periodically rather than ticking live.

const API_BASE = "https://rice-mgmt-803.onrender.com";

function parseParam(raw) {
  if (!raw) return null;
  const commaIndex = raw.indexOf(",");
  if (commaIndex === -1) return null;
  const occasion = raw.slice(0, commaIndex).trim();
  const dateStr = raw.slice(commaIndex + 1).trim();
  if (!occasion || !dateStr) return null;
  const match = dateStr.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!match) return null;
  const [, month, day, year] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  if (isNaN(date.getTime())) return null;
  return { occasion, date };
}

async function fetchTheme(occasion, date) {
  const url = `${API_BASE}/api/countdown?target=${encodeURIComponent(date.toISOString())}&occasion=${encodeURIComponent(occasion)}`;
  const req = new Request(url);
  req.timeoutInterval = 8;
  try {
    return await req.loadJSON();
  } catch (e) {
    return null;
  }
}

function formatRemaining(ms) {
  if (ms <= 0) return { days: 0, done: true };
  return { days: Math.ceil(ms / 86400000), done: false };
}

const DEFAULT_THEME = {
  hero: "⏳",
  bg_from: "#0F172A",
  bg_to: "#1E293B",
  text: "#E2E8F0",
  accent: "#38BDF8",
};

async function createWidget() {
  const family = config.widgetFamily || "medium"; // no family when previewing in-app
  const isSmall = family === "small";
  const pad = isSmall ? 10 : 14;

  const widget = new ListWidget();
  widget.setPadding(pad, pad, pad, pad);

  const parsed = parseParam(args.widgetParameter);
  if (!parsed) {
    widget.backgroundColor = new Color(DEFAULT_THEME.bg_from);
    const text = widget.addText("Long-press → Edit Widget → set Parameter to:\nOccasion,MM/DD/YYYY\ne.g. Christmas,12/25/2026");
    text.textColor = Color.white();
    text.font = Font.mediumSystemFont(isSmall ? 11 : 13);
    return widget;
  }

  const { occasion, date } = parsed;
  const result = await fetchTheme(occasion, date);
  const theme = (result && result.theme) || DEFAULT_THEME;

  const gradient = new LinearGradient();
  gradient.colors = [new Color(theme.bg_from), new Color(theme.bg_to)];
  gradient.locations = [0, 1];
  widget.backgroundGradient = gradient;

  const hero = widget.addText(theme.hero || DEFAULT_THEME.hero);
  hero.font = Font.systemFont(isSmall ? 22 : 30);
  hero.centerAlignText();
  widget.addSpacer(isSmall ? 2 : 4);

  const title = widget.addText(occasion);
  title.textColor = new Color(theme.text || DEFAULT_THEME.text);
  title.font = Font.boldSystemFont(isSmall ? 14 : 18);
  title.centerAlignText();
  title.lineLimit = isSmall ? 1 : 2;
  title.minimumScaleFactor = 0.6;
  widget.addSpacer(isSmall ? 2 : 6);

  const remainingMs = date.getTime() - Date.now();
  const { days, done } = formatRemaining(remainingMs);
  const countText = done ? "🎉 It's here! 🎉" : `${days} day${days === 1 ? "" : "s"}`;
  const count = widget.addText(countText);
  count.textColor = new Color(theme.accent || DEFAULT_THEME.accent);
  count.font = Font.boldSystemFont(done ? (isSmall ? 13 : 16) : (isSmall ? 18 : 22));
  count.centerAlignText();
  count.lineLimit = 1;
  count.minimumScaleFactor = 0.6;

  widget.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);
  return widget;
}

const widget = await createWidget();
if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  widget.presentMedium();
}
Script.complete();
