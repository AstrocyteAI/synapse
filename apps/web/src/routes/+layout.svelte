<script lang="ts">
	import '../app.css';
	import { getToken } from '$lib/api/client';
	import { getNotificationFeed } from '$lib/api/client';
	import { backendStore } from '$lib/stores/backend.svelte';
	import BackendBadge from '$lib/components/BackendBadge.svelte';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';

	let { children } = $props();

	const navLinks = [
		{ href: '/', label: 'Chat' },
		{ href: '/councils', label: 'Councils' },
		{ href: '/memory', label: 'Memory' },
		{ href: '/analytics', label: 'Analytics' }
	];

	// ---------------------------------------------------------------------------
	// Notification bell — unread count derived from localStorage last-seen time
	// ---------------------------------------------------------------------------

	const LAST_SEEN_KEY = 'synapse_notif_last_seen';

	let unreadCount = $state(0);

	async function refreshUnreadCount() {
		if (!getToken()) return;
		try {
			const feed = await getNotificationFeed(20);
			const lastSeen = localStorage.getItem(LAST_SEEN_KEY);
			const cutoff = lastSeen ? new Date(lastSeen) : new Date(0);
			unreadCount = feed.items.filter((item) => new Date(item.occurred_at) > cutoff).length;
		} catch {
			// silently ignore — bell is best-effort
		}
	}

	onMount(() => {
		// Fetch backend metadata once at app load (X-3) — drives BackendBadge
		// and any multi_tenant / billing UI gating downstream.
		backendStore.load();

		refreshUnreadCount();
		// Re-check every 60 s while the tab is open
		const interval = setInterval(refreshUnreadCount, 60_000);
		return () => clearInterval(interval);
	});

	// When the user navigates to /notifications, mark everything read
	$effect(() => {
		if (($page.url.pathname as string) === '/notifications') {
			localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString());
			unreadCount = 0;
		}
	});
</script>

<svelte:head>
	<title>Synapse</title>
</svelte:head>

<div class="flex h-screen flex-col">
	<!-- Nav -->
	<header class="flex shrink-0 items-center gap-6 border-b border-zinc-800 px-5 py-3">
		<a href="/" class="flex items-center gap-2 text-sm font-semibold text-zinc-100">
			<span class="text-indigo-400">✦</span>
			Synapse
		</a>

		<nav class="flex gap-1">
			{#each navLinks as link}
				<a
					href={link.href}
					class="rounded-lg px-3 py-1.5 text-sm transition-colors
						{$page.url.pathname === link.href
						? 'bg-zinc-800 text-zinc-100'
						: 'text-zinc-400 hover:text-zinc-200'}"
				>
					{link.label}
				</a>
			{/each}
		</nav>

		<div class="ml-auto flex items-center gap-3">
			<BackendBadge />

			<!-- Notification bell -->
			<a
				href="/notifications"
				class="relative flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
				aria-label="Notifications"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="h-4 w-4"
				>
					<path
						d="M10 2a6 6 0 00-6 6v2.197l-1.447 2.17A1 1 0 003.382 14H7a3 3 0 006 0h3.618a1 1 0 00.829-1.633L16 10.197V8a6 6 0 00-6-6z"
					/>
				</svg>
				{#if unreadCount > 0}
					<span
						class="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-indigo-500 text-[10px] font-bold text-white"
					>
						{unreadCount > 9 ? '9+' : unreadCount}
					</span>
				{/if}
			</a>

			<!-- Settings gear -->
			<a
				href="/settings/notifications"
				class="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
				aria-label="Settings"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="h-4 w-4"
				>
					<path
						fill-rule="evenodd"
						d="M7.84 1.804A1 1 0 018.82 1h2.36a1 1 0 01.98.804l.31 1.55a6.5 6.5 0 011.38.807l1.5-.5a1 1 0 011.17.48l1.18 2.044a1 1 0 01-.23 1.258l-1.215.98a6.546 6.546 0 010 1.614l1.215.98a1 1 0 01.23 1.258l-1.18 2.044a1 1 0 01-1.17.48l-1.5-.5a6.5 6.5 0 01-1.38.807l-.31 1.55a1 1 0 01-.98.804H8.82a1 1 0 01-.98-.804l-.31-1.55a6.5 6.5 0 01-1.38-.807l-1.5.5a1 1 0 01-1.17-.48L2.3 11.558a1 1 0 01.23-1.258l1.215-.98a6.546 6.546 0 010-1.614l-1.215-.98a1 1 0 01-.23-1.258L3.48 3.424a1 1 0 011.17-.48l1.5.5a6.5 6.5 0 011.38-.807l.31-1.55zM10 13a3 3 0 100-6 3 3 0 000 6z"
						clip-rule="evenodd"
					/>
				</svg>
			</a>

			<span class="text-xs text-zinc-600">
				{getToken() ? '● connected' : '○ no token'}
			</span>
		</div>
	</header>

	<!-- Page content -->
	<main class="flex min-h-0 flex-1 flex-col">
		{@render children()}
	</main>
</div>
