<script lang="ts">
	import { goto } from '$app/navigation';
	import { loginLocal, setToken, getToken } from '$lib/api/client';
	import { backendStore } from '$lib/stores/backend.svelte';
	import { onMount } from 'svelte';

	const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

	// Local auth
	let email = $state('');
	let password = $state('');

	// Token paste (dev / API key)
	let tokenInput = $state('');

	let submitting = $state(false);
	let error = $state('');

	onMount(async () => {
		// Already logged in — skip login page
		if (getToken()) {
			goto('/');
			return;
		}
		// Ensure backend info is loaded so we can branch on auth_mode
		await backendStore.load();
	});

	// ── Local email/password ──────────────────────────────────────────────────

	async function handleLocalLogin() {
		if (!email.trim() || !password) return;
		submitting = true;
		error = '';
		try {
			await loginLocal(email.trim(), password);
			goto('/');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Login failed.';
		} finally {
			submitting = false;
		}
	}

	// ── OIDC redirect ─────────────────────────────────────────────────────────

	function handleOidcLogin() {
		// Cerebro handles the OIDC flow server-side; the browser just navigates
		// to /auth/oidc/start which redirects to Casdoor and back.
		const callbackUrl = encodeURIComponent(`${window.location.origin}/`);
		window.location.href = `${API_BASE}/auth/oidc/start?redirect_uri=${callbackUrl}`;
	}

	// ── Token paste (jwt_hs256 / API key) ────────────────────────────────────

	function handleTokenSave() {
		const token = tokenInput.trim();
		if (!token) return;
		setToken(token);
		goto('/');
	}
</script>

<div class="flex flex-1 flex-col items-center justify-center px-4 py-12">
	<div class="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 p-8">
		<div class="mb-6 text-center">
			<span class="text-3xl text-indigo-400">✦</span>
			<h1 class="mt-2 text-xl font-semibold text-zinc-100">Sign in to Synapse</h1>
		</div>

		{#if error}
			<div
				class="mb-4 rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400"
			>
				{error}
			</div>
		{/if}

		{#if backendStore.loading}
			<p class="text-center text-sm text-zinc-500">Loading…</p>

		{:else if backendStore.authMode === 'local'}
			<!-- ── Local email/password form ── -->
			<form onsubmit={(e) => { e.preventDefault(); handleLocalLogin(); }} class="space-y-4">
				<div>
					<label for="email" class="mb-1 block text-xs font-medium text-zinc-400">Email</label>
					<input
						id="email"
						type="email"
						bind:value={email}
						autocomplete="email"
						required
						class="w-full rounded-xl border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500"
						placeholder="you@example.com"
					/>
				</div>
				<div>
					<label for="password" class="mb-1 block text-xs font-medium text-zinc-400">Password</label>
					<input
						id="password"
						type="password"
						bind:value={password}
						autocomplete="current-password"
						required
						class="w-full rounded-xl border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500"
						placeholder="••••••••"
					/>
				</div>
				<button
					type="submit"
					disabled={submitting || !email.trim() || !password}
					class="w-full rounded-xl bg-indigo-600 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
				>
					{submitting ? 'Signing in…' : 'Sign in'}
				</button>
			</form>

		{:else if backendStore.authMode === 'jwt_oidc'}
			<!-- ── OIDC / Casdoor button ── -->
			<button
				onclick={handleOidcLogin}
				class="w-full rounded-xl bg-indigo-600 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
			>
				Sign in with Casdoor
			</button>
			<p class="mt-3 text-center text-xs text-zinc-600">
				You'll be redirected to the identity provider.
			</p>

		{:else}
			<!-- ── Token paste (jwt_hs256 dev mode / API keys) ── -->
			<p class="mb-4 text-sm text-zinc-400">Paste your Synapse JWT or API key to get started.</p>
			<textarea
				bind:value={tokenInput}
				placeholder="eyJ… or sk-…"
				rows="3"
				class="w-full resize-none rounded-xl border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500"
			></textarea>
			<button
				onclick={handleTokenSave}
				disabled={!tokenInput.trim()}
				class="mt-3 w-full rounded-xl bg-indigo-600 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
			>
				Save token
			</button>
		{/if}
	</div>
</div>
