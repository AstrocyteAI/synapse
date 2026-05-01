/**
 * Auth state derived from the JWT in localStorage.
 *
 * Provides reactive access to roles + tenant for components that need to
 * gate UI on whether the user is an admin (e.g. the W8 admin panel link).
 *
 * Usage:
 *   import { authStore } from '$lib/stores/auth.svelte';
 *   {#if authStore.isAdmin} ... {/if}
 *
 * The store re-reads the token whenever `refresh()` is called — typically
 * after login/logout. Components that mount once at app load can read it
 * directly.
 */

import { getToken } from '$lib/api/client';

interface AuthClaims {
	sub: string;
	synapse_roles?: string[] | string;
	synapse_tenant?: string | null;
}

class AuthStore {
	claims = $state<AuthClaims | null>(null);

	constructor() {
		this.refresh();
	}

	refresh(): void {
		const token = getToken();
		if (!token) {
			this.claims = null;
			return;
		}
		try {
			const [, payload] = token.split('.');
			if (!payload) {
				this.claims = null;
				return;
			}
			const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
			this.claims = decoded as AuthClaims;
		} catch {
			this.claims = null;
		}
	}

	get roles(): string[] {
		const r = this.claims?.synapse_roles;
		if (!r) return [];
		return Array.isArray(r) ? r : [r];
	}

	get isAdmin(): boolean {
		return this.roles.includes('admin') || this.roles.includes('super_admin');
	}

	get tenantId(): string | null {
		return this.claims?.synapse_tenant ?? null;
	}

	get principal(): string | null {
		return this.claims?.sub ? `user:${this.claims.sub}` : null;
	}
}

export const authStore = new AuthStore();
