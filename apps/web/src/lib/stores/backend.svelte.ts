/**
 * Backend metadata store (X-3).
 *
 * Fetched once at app load via `GET /v1/info`. Components read it through
 * the exported `backendStore` to know whether the deployment is Synapse
 * single-tenant or Cerebro multi-tenant, and to gate UI on feature flags.
 *
 * Usage:
 *   import { backendStore } from '$lib/stores/backend.svelte';
 *   onMount(() => backendStore.load());
 *   // later: {#if backendStore.info?.multi_tenant} ... {/if}
 */

import { getBackendInfo } from '$lib/api/client';
import type { BackendInfo } from '$lib/api/types';

class BackendStore {
	info = $state<BackendInfo | null>(null);
	loading = $state(false);
	error = $state<string | null>(null);

	async load(): Promise<void> {
		if (this.info || this.loading) return;
		this.loading = true;
		this.error = null;
		try {
			this.info = await getBackendInfo();
		} catch (e) {
			this.error = e instanceof Error ? e.message : String(e);
		} finally {
			this.loading = false;
		}
	}

	// Convenience getters
	get isMultiTenant(): boolean {
		return this.info?.multi_tenant ?? false;
	}
	get isCerebro(): boolean {
		return this.info?.backend === 'cerebro';
	}
	get hasBilling(): boolean {
		return this.info?.billing ?? false;
	}
	/** "jwt_hs256" | "jwt_oidc" | "local" — defaults to jwt_hs256 until loaded. */
	get authMode(): string {
		return this.info?.auth_mode ?? 'jwt_hs256';
	}
}

export const backendStore = new BackendStore();
