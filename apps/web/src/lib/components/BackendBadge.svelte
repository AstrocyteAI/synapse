<script lang="ts">
	/**
	 * Small pill in the nav showing which backend is being used.
	 *
	 * - Synapse single-tenant: "Synapse · v0.1.0" in zinc
	 * - Cerebro multi-tenant: "Cerebro · tenant-acme" in indigo
	 *
	 * Reads from backendStore which is loaded once in +layout.svelte.
	 * Hidden when the store is empty (pre-load or fetch failed).
	 *
	 * Hover reveals the full BackendInfo as a diagnostics tooltip.
	 */
	import { backendStore } from '$lib/stores/backend.svelte';
	import { getToken } from '$lib/api/client';

	// Decode tenant_id from JWT for display in Cerebro mode (no decode lib —
	// just split + base64). Best-effort; null on any failure.
	function tenantFromJwt(): string | null {
		const token = getToken();
		if (!token) return null;
		try {
			const [, payload] = token.split('.');
			if (!payload) return null;
			const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
			return decoded.synapse_tenant ?? null;
		} catch {
			return null;
		}
	}

	const info = $derived(backendStore.info);
	const tenant = $derived(info?.multi_tenant ? tenantFromJwt() : null);
	const tooltip = $derived(
		info
			? `${info.backend} v${info.version} · contract ${info.contract_version}\n` +
				`multi_tenant=${info.multi_tenant} · billing=${info.billing}\n` +
				`features: ${Object.entries(info.features)
					.filter(([, v]) => v)
					.map(([k]) => k)
					.join(', ') || '(none)'}`
			: ''
	);
</script>

{#if info}
	<span
		title={tooltip}
		class="rounded px-2 py-0.5 text-[10px] font-medium tracking-wide
			{info.backend === 'cerebro'
			? 'bg-indigo-500/15 text-indigo-300'
			: 'bg-zinc-800 text-zinc-400'}"
	>
		<span class="capitalize">{info.backend}</span>
		{#if tenant}
			<span class="text-zinc-500"> · </span>{tenant}
		{:else}
			<span class="text-zinc-600"> · v{info.version}</span>
		{/if}
	</span>
{/if}
