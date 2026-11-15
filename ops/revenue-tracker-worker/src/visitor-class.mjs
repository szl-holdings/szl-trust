// Per-visitor classification: people vs verified bots vs everything else.
// The revenue tracker counts only attested payments; this module adds the
// breakdown so no revenue number is trusted without knowing WHO paid.
//
// Classification is conservative and fail-closed: anything unrecognized is
// "other" (never silently counted as human traffic).

const VERIFIED_BOT_PATTERNS = [
  { match: /GPTBot\//i, label: "openai-gptbot" },
  { match: /OAI-SearchBot\//i, label: "openai-search" },
  { match: /ChatGPT-User\//i, label: "openai-chatgpt-user" },
  { match: /ClaudeBot\//i, label: "anthropic-claudebot" },
  { match: /Claude-Web\//i, label: "anthropic-claude-web" },
  { match: /PerplexityBot\//i, label: "perplexity" },
  { match: /Google-Extended/i, label: "google-extended" },
  { match: /Googlebot\//i, label: "googlebot" },
  { match: /Bingbot\//i, label: "bingbot" },
  { match: /CCBot\//i, label: "ccbot-commoncrawl" },
  { match: /Bytespider\//i, label: "bytespider" },
  { match: /meta-externalagent/i, label: "meta-agent" },
  { match: /Amazonbot\//i, label: "amazonbot" },
  { match: /Applebot(-Extended)?\//i, label: "applebot" },
];

const BROWSER_HINTS = /Mozilla\/5\.0.*(Gecko|Chrome|Safari|Firefox|Edg)/i;

export function classifyVisitor(headers) {
  const ua = String(headers.get("user-agent") || "");
  if (!ua) return { class: "unknown", label: "no-user-agent", human: false };
  for (const { match, label } of VERIFIED_BOT_PATTERNS) {
    if (match.test(ua)) return { class: "verified_bot", label, human: false };
  }
  if (BROWSER_HINTS.test(ua)) return { class: "human_likely", label: "browser", human: true };
  return { class: "other", label: "unrecognized", human: false };
}

// The breakdown dimensions the tracker should log per event:
//   visitor_class  verified_bot | human_likely | other | unknown
//   visitor_label  the specific bot or "browser"
// Every revenue event carries this, so a revenue number can always be
// decomposed into: paid-by-humans vs paid-by-bots before it is trusted.
