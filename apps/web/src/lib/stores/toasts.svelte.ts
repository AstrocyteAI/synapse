// Lightweight in-app toast stack. Singleton state — mounted once by the
// app layout via <ToastHost /> and shoved into via `toasts.push({...})`
// from anywhere (polling loops, mutation handlers, etc.).
//
// We deliberately do NOT pull in a toast library — the surface is tiny
// (one stack, auto-dismiss, click-through to a deep link) and adding
// melt/bits-ui just for this would balloon the bundle for one feature.

export interface Toast {
	id: string;
	title: string;
	body?: string;
	/** Optional deep link — click navigates and dismisses. */
	href?: string;
	/** Visual tone — drives the stripe colour. */
	tone?: 'info' | 'awaited' | 'success' | 'warning';
	/** Auto-dismiss after this many ms. `null` = sticky until clicked. */
	ttlMs?: number | null;
}

class ToastStore {
	items = $state<Toast[]>([]);

	push(toast: Omit<Toast, 'id'>) {
		const id =
			(globalThis.crypto?.randomUUID?.() ??
				`toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);
		const full: Toast = { ttlMs: 7000, tone: 'info', ...toast, id };
		this.items = [...this.items, full];

		if (full.ttlMs && full.ttlMs > 0) {
			setTimeout(() => this.dismiss(id), full.ttlMs);
		}
	}

	dismiss(id: string) {
		this.items = this.items.filter((t) => t.id !== id);
	}

	clear() {
		this.items = [];
	}
}

export const toasts = new ToastStore();
