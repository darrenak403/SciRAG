// What to tell someone when their model provider refuses a call, and what they can do
// about it. Shared by the chat, failed papers and the connection form.

export type ProviderProblem = {
  title: string;
  hint: string;
  // Whether the fix is in Settings (as opposed to waiting, or at the provider's own site).
  openSettings: boolean;
};

const PROBLEMS: Record<string, ProviderProblem> = {
  invalid_key: {
    title: "Your API key was rejected",
    hint: "Check the key in Settings, or create a new one at your provider.",
    openSettings: true,
  },
  quota_exceeded: {
    title: "Your provider quota is used up",
    hint: "Add credit or wait for the quota to reset at your provider, or switch to another connection.",
    openSettings: true,
  },
  rate_limited: {
    title: "Your provider is limiting requests",
    hint: "Wait a moment and try again.",
    openSettings: false,
  },
  model_not_found: {
    title: "The model isn't available to your key",
    hint: "Choose another model for this connection in Settings.",
    openSettings: true,
  },
  provider_unreachable: {
    title: "Your provider couldn't be reached",
    hint: "This is usually temporary. Try again in a moment.",
    openSettings: false,
  },
  capability_missing: {
    title: "This connection is missing something SciRAG needs",
    hint: "Open Settings to see which check failed.",
    openSettings: true,
  },
  provider_rejected: {
    title: "Your provider rejected the request",
    hint: "Try again. If it keeps happening, test the connection in Settings.",
    openSettings: true,
  },
  provider_not_configured: {
    title: "No model provider is set up",
    hint: "Add your own key in Settings to process papers and ask questions.",
    openSettings: true,
  },
  connection_not_usable: {
    title: "This connection didn't pass its test",
    hint: "Fix the failing checks and test it again.",
    openSettings: true,
  },
};

export function isProviderCode(code: string | null | undefined): boolean {
  return !!code && code in PROBLEMS;
}

/** The explanation for a provider error code, or null when the code is not one. */
export function providerProblem(code: string | null | undefined, detail?: string | null): ProviderProblem | null {
  if (!code || !(code in PROBLEMS)) return null;
  const problem = PROBLEMS[code];
  // The provider's own words name the model; show them rather than a generic line.
  if (code === "model_not_found" && detail) return { ...problem, hint: `${detail} ${problem.hint}` };
  return problem;
}
