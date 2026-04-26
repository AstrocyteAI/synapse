<script lang="ts">
	import '../app.css';
	import { getToken } from '$lib/api/client';
	import { page } from '$app/stores';

	let { children } = $props();

	const navLinks = [
		{ href: '/', label: 'Chat' },
		{ href: '/councils', label: 'Councils' },
		{ href: '/memory', label: 'Memory' },
		{ href: '/analytics', label: 'Analytics' }
	];
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

		<div class="ml-auto text-xs text-zinc-600">
			{getToken() ? '● connected' : '○ no token'}
		</div>
	</header>

	<!-- Page content -->
	<main class="flex min-h-0 flex-1 flex-col">
		{@render children()}
	</main>
</div>
