'use client';

interface ProvisionalBannerProps {
  visible: boolean;
}

export function ProvisionalBanner({ visible }: ProvisionalBannerProps) {
  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
    >
      Rankings are provisional by verdict count. Final rankings use ground-truth correlation.
    </div>
  );
}
