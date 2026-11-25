import { useEffect, useState } from "react";
import { RotateCcw, SlidersHorizontal, X } from "lucide-react";
import type {
  DetailLevel,
  FocusLens,
  ResponseFormat,
  UserPreferences,
} from "../types/api";

export const DEFAULT_PREFERENCES: UserPreferences = {
  detail_level: "Balanced",
  response_format: "Structured Bullets & Tables",
  focus_lens: "Security & Compliance",
  custom_instructions: "",
};

const DETAIL_OPTIONS: { value: DetailLevel; desc: string }[] = [
  { value: "Concise", desc: "Brief, high-signal answers" },
  { value: "Balanced", desc: "Clear context & requirements" },
  { value: "Deep Dive", desc: "Full control nuances & caveats" },
];

const FORMAT_OPTIONS: { value: ResponseFormat; desc: string }[] = [
  { value: "Structured Bullets & Tables", desc: "Headings, bullets & tables" },
  { value: "Step-by-Step", desc: "Ordered implementation sequence" },
  { value: "TL;DR First", desc: "Summary first, evidence below" },
];

const LENS_OPTIONS: { value: FocusLens; desc: string }[] = [
  { value: "Security & Compliance", desc: "NIST controls, governance & risk" },
  { value: "AI / Product Engineering", desc: "Architecture & system reliability" },
  { value: "Hands-On Code", desc: "Configs, schemas & checks" },
];

export function formatPreferenceBadge(prefs: UserPreferences): string {
  const shortFormatMap: Record<ResponseFormat, string> = {
    "Structured Bullets & Tables": "Bullets",
    "Step-by-Step": "Steps",
    "TL;DR First": "TL;DR",
  };
  const shortLensMap: Record<FocusLens, string> = {
    "Security & Compliance": "Security",
    "AI / Product Engineering": "Engineering",
    "Hands-On Code": "Code",
  };
  return `Style: ${prefs.detail_level} · ${shortFormatMap[prefs.response_format]} · ${shortLensMap[prefs.focus_lens]}`;
}

interface PreferencesModalProps {
  isOpen: boolean;
  preferences: UserPreferences;
  onClose: () => void;
  onSave: (next: UserPreferences) => void;
}

export function PreferencesModal({
  isOpen,
  preferences,
  onClose,
  onSave,
}: PreferencesModalProps) {
  const [draft, setDraft] = useState<UserPreferences>(preferences);

  useEffect(() => {
    if (isOpen) {
      setDraft(preferences);
    }
  }, [isOpen, preferences]);

  if (!isOpen) return null;

  const handleSave = () => {
    onSave({
      ...draft,
      custom_instructions: (draft.custom_instructions ?? "").trim(),
    });
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[88vh] w-full max-w-xl flex-col rounded-2xl border border-white/10 bg-[#212121] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3.5">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-[#ECECEC]" />
            <h3 className="text-sm font-semibold text-[#ECECEC]">
              Response Preferences
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close preferences modal"
            className="rounded-lg p-1 text-[#9B9B9B] transition hover:bg-[#2F2F2F] hover:text-[#ECECEC]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {/* Detail Level */}
          <section className="space-y-2">
            <div className="text-xs font-semibold text-[#ECECEC]">Detail Level</div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {DETAIL_OPTIONS.map((opt) => {
                const selected = draft.detail_level === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setDraft((prev) => ({ ...prev, detail_level: opt.value }))}
                    className={`rounded-xl border p-3 text-left transition ${
                      selected
                        ? "border-white/30 bg-[#2F2F2F] ring-1 ring-white/20"
                        : "border-white/10 bg-[#171717] hover:border-white/20 hover:bg-[#242424]"
                    }`}
                  >
                    <div className="text-xs font-semibold text-[#ECECEC]">{opt.value}</div>
                    <div className="mt-0.5 text-[11px] text-[#9B9B9B]">{opt.desc}</div>
                  </button>
                );
              })}
            </div>
          </section>

          {/* Response Format */}
          <section className="space-y-2">
            <div className="text-xs font-semibold text-[#ECECEC]">Format</div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {FORMAT_OPTIONS.map((opt) => {
                const selected = draft.response_format === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() =>
                      setDraft((prev) => ({ ...prev, response_format: opt.value }))
                    }
                    className={`rounded-xl border p-3 text-left transition ${
                      selected
                        ? "border-white/30 bg-[#2F2F2F] ring-1 ring-white/20"
                        : "border-white/10 bg-[#171717] hover:border-white/20 hover:bg-[#242424]"
                    }`}
                  >
                    <div className="text-xs font-semibold text-[#ECECEC]">{opt.value}</div>
                    <div className="mt-0.5 text-[11px] text-[#9B9B9B]">{opt.desc}</div>
                  </button>
                );
              })}
            </div>
          </section>

          {/* Focus Lens */}
          <section className="space-y-2">
            <div className="text-xs font-semibold text-[#ECECEC]">Focus Lens</div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {LENS_OPTIONS.map((opt) => {
                const selected = draft.focus_lens === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setDraft((prev) => ({ ...prev, focus_lens: opt.value }))}
                    className={`rounded-xl border p-3 text-left transition ${
                      selected
                        ? "border-white/30 bg-[#2F2F2F] ring-1 ring-white/20"
                        : "border-white/10 bg-[#171717] hover:border-white/20 hover:bg-[#242424]"
                    }`}
                  >
                    <div className="text-xs font-semibold text-[#ECECEC]">{opt.value}</div>
                    <div className="mt-0.5 text-[11px] text-[#9B9B9B]">{opt.desc}</div>
                  </button>
                );
              })}
            </div>
          </section>

          {/* Optional Custom Instructions */}
          <section className="space-y-2">
            <label
              htmlFor="custom-preferences-input"
              className="block text-xs font-semibold text-[#ECECEC]"
            >
              Custom Guidance <span className="font-normal text-[#9B9B9B]">(optional)</span>
            </label>
            <textarea
              id="custom-preferences-input"
              rows={2}
              maxLength={300}
              value={draft.custom_instructions ?? ""}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, custom_instructions: e.target.value }))
              }
              placeholder="e.g., Always call out NIST SP 800-53 control IDs and verification criteria."
              className="w-full resize-none rounded-xl border border-white/10 bg-[#171717] px-3 py-2 text-xs text-[#ECECEC] placeholder-[#9B9B9B] focus:border-white/30 focus:outline-none"
            />
          </section>
        </div>

        <div className="flex items-center justify-between border-t border-white/10 px-5 py-3.5">
          <button
            type="button"
            onClick={() => setDraft(DEFAULT_PREFERENCES)}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-[#9B9B9B] transition hover:bg-[#2F2F2F] hover:text-[#ECECEC]"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset defaults
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-white/10 px-3.5 py-1.5 text-xs font-medium text-[#9B9B9B] transition hover:bg-[#2F2F2F] hover:text-[#ECECEC]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="rounded-xl bg-[#ECECEC] px-4 py-1.5 text-xs font-semibold text-[#171717] transition hover:bg-white"
            >
              Save preferences
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
