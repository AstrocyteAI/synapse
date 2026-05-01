<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getNotificationPreferences,
		updateNotificationPreferences,
		listDeviceTokens,
		registerDeviceToken,
		deleteDeviceToken
	} from '$lib/api/client';
	import type { DeviceToken } from '$lib/api/types';

	// ---------------------------------------------------------------------------
	// State — preferences
	// ---------------------------------------------------------------------------

	let loadingPrefs = $state(true);
	let savingPrefs = $state(false);
	let prefsError = $state('');
	let prefsSaved = $state(false);
	let featureUnavailable = $state(false);

	let emailEnabled = $state(false);
	let emailAddress = $state('');
	let ntfyEnabled = $state(false);

	// ---------------------------------------------------------------------------
	// State — device tokens
	// ---------------------------------------------------------------------------

	let devices = $state<DeviceToken[]>([]);
	let loadingDevices = $state(true);
	let newTopic = $state('');
	let newLabel = $state('');
	let addingDevice = $state(false);
	let addError = $state('');
	let deletingId = $state<string | null>(null);

	// ---------------------------------------------------------------------------
	// Load
	// ---------------------------------------------------------------------------

	onMount(async () => {
		await Promise.all([loadPrefs(), loadDevices()]);
	});

	async function loadPrefs() {
		loadingPrefs = true;
		prefsError = '';
		try {
			const prefs = await getNotificationPreferences();
			emailEnabled = prefs.email_enabled;
			emailAddress = prefs.email_address ?? '';
			ntfyEnabled = prefs.ntfy_enabled;
		} catch (e) {
			const msg = e instanceof Error ? e.message : String(e);
			if (msg.startsWith('501')) {
				featureUnavailable = true;
			} else {
				prefsError = msg;
			}
		} finally {
			loadingPrefs = false;
		}
	}

	async function loadDevices() {
		loadingDevices = true;
		try {
			const res = await listDeviceTokens();
			devices = res.devices;
		} catch {
			// silently fail if EE feature not available
		} finally {
			loadingDevices = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Actions
	// ---------------------------------------------------------------------------

	async function savePrefs() {
		savingPrefs = true;
		prefsError = '';
		prefsSaved = false;
		try {
			await updateNotificationPreferences({
				email_enabled: emailEnabled,
				email_address: emailEnabled ? emailAddress || null : null,
				ntfy_enabled: ntfyEnabled
			});
			prefsSaved = true;
			setTimeout(() => (prefsSaved = false), 3000);
		} catch (e) {
			prefsError = e instanceof Error ? e.message : String(e);
		} finally {
			savingPrefs = false;
		}
	}

	async function addDevice() {
		if (!newTopic.trim()) return;
		addingDevice = true;
		addError = '';
		try {
			const device = await registerDeviceToken(newTopic.trim(), newLabel.trim() || undefined);
			devices = [...devices, device];
			newTopic = '';
			newLabel = '';
		} catch (e) {
			addError = e instanceof Error ? e.message : String(e);
		} finally {
			addingDevice = false;
		}
	}

	async function removeDevice(id: string) {
		deletingId = id;
		try {
			await deleteDeviceToken(id);
			devices = devices.filter((d) => d.id !== id);
		} catch {
			// ignore
		} finally {
			deletingId = null;
		}
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleDateString(undefined, {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}
</script>

<div class="mx-auto w-full max-w-2xl px-4 py-8">
	<div class="mb-8">
		<h1 class="text-lg font-semibold text-zinc-100">Notification Settings</h1>
		<p class="mt-1 text-sm text-zinc-500">
			Configure how you receive verdicts and summons from Synapse councils.
		</p>
	</div>

	<!-- EE unavailable banner -->
	{#if featureUnavailable}
		<div class="mb-6 rounded-xl border border-amber-800/40 bg-amber-900/20 px-4 py-3 text-sm text-amber-300">
			<strong>EE Team+ feature.</strong> Notification channels require an Enterprise license.
			<a
				href="https://cerebro.odeoncg.ai"
				target="_blank"
				rel="noopener"
				class="ml-1 underline hover:text-amber-200"
			>
				Learn more →
			</a>
		</div>
	{/if}

	<!-- ----------------------------------------------------------------- -->
	<!-- Preferences card                                                   -->
	<!-- ----------------------------------------------------------------- -->
	<section class="mb-6 rounded-xl border border-zinc-800 bg-zinc-900">
		<div class="border-b border-zinc-800 px-5 py-4">
			<h2 class="text-sm font-medium text-zinc-200">Notification channels</h2>
		</div>

		{#if loadingPrefs}
			<div class="flex items-center gap-2 px-5 py-6 text-sm text-zinc-500">
				<svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
				</svg>
				Loading…
			</div>
		{:else}
			<div class="space-y-5 px-5 py-5">
				<!-- Email -->
				<div>
					<label class="flex items-center gap-3 cursor-pointer">
						<button
							role="switch"
							aria-checked={emailEnabled}
							disabled={featureUnavailable}
							onclick={() => (emailEnabled = !emailEnabled)}
							class="relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors focus:outline-none
								{emailEnabled ? 'bg-indigo-600' : 'bg-zinc-700'}
								{featureUnavailable ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}"
						>
							<span
								class="inline-block h-4 w-4 translate-y-0.5 rounded-full bg-white shadow transition-transform
									{emailEnabled ? 'translate-x-4' : 'translate-x-0.5'}"
							></span>
						</button>
						<span class="text-sm font-medium text-zinc-200">Email notifications</span>
					</label>

					{#if emailEnabled}
						<div class="mt-3 ml-12">
							<input
								type="email"
								bind:value={emailAddress}
								placeholder="you@example.com"
								disabled={featureUnavailable}
								class="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100
									placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none
									disabled:cursor-not-allowed disabled:opacity-50"
							/>
							<p class="mt-1.5 text-xs text-zinc-500">Receive verdict summaries via email.</p>
						</div>
					{/if}
				</div>

				<div class="border-t border-zinc-800"></div>

				<!-- ntfy -->
				<div>
					<label class="flex items-center gap-3 cursor-pointer">
						<button
							role="switch"
							aria-checked={ntfyEnabled}
							disabled={featureUnavailable}
							onclick={() => (ntfyEnabled = !ntfyEnabled)}
							class="relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors focus:outline-none
								{ntfyEnabled ? 'bg-indigo-600' : 'bg-zinc-700'}
								{featureUnavailable ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}"
						>
							<span
								class="inline-block h-4 w-4 translate-y-0.5 rounded-full bg-white shadow transition-transform
									{ntfyEnabled ? 'translate-x-4' : 'translate-x-0.5'}"
							></span>
						</button>
						<span class="text-sm font-medium text-zinc-200">ntfy push notifications</span>
					</label>
					<p class="mt-1.5 ml-12 text-xs text-zinc-500">
						Push verdicts to your ntfy topics.
						<a
							href="https://ntfy.sh"
							target="_blank"
							rel="noopener"
							class="text-indigo-400 hover:text-indigo-300"
						>
							What is ntfy?
						</a>
					</p>
				</div>
			</div>

			<!-- Save -->
			<div class="flex items-center gap-3 border-t border-zinc-800 px-5 py-4">
				<button
					onclick={savePrefs}
					disabled={savingPrefs || featureUnavailable}
					class="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors
						hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
				>
					{savingPrefs ? 'Saving…' : 'Save preferences'}
				</button>
				{#if prefsSaved}
					<span class="text-sm text-emerald-400">✓ Saved</span>
				{/if}
				{#if prefsError}
					<span class="text-sm text-red-400">{prefsError}</span>
				{/if}
			</div>
		{/if}
	</section>

	<!-- ----------------------------------------------------------------- -->
	<!-- Device tokens card                                                 -->
	<!-- ----------------------------------------------------------------- -->
	{#if ntfyEnabled || devices.length > 0}
		<section class="rounded-xl border border-zinc-800 bg-zinc-900">
			<div class="border-b border-zinc-800 px-5 py-4">
				<h2 class="text-sm font-medium text-zinc-200">Registered ntfy topics</h2>
				<p class="mt-0.5 text-xs text-zinc-500">
					Add the ntfy topic you want verdicts pushed to. Use a private topic name.
				</p>
			</div>

			{#if loadingDevices}
				<div class="px-5 py-4 text-sm text-zinc-500">Loading…</div>
			{:else}
				<!-- Existing devices -->
				{#if devices.length > 0}
					<ul class="divide-y divide-zinc-800">
						{#each devices as device (device.id)}
							<li class="flex items-center gap-3 px-5 py-3">
								<div class="min-w-0 flex-1">
									<p class="truncate text-sm text-zinc-200">{device.token}</p>
									<p class="text-xs text-zinc-500">
										{device.device_label ?? 'No label'} · Added {formatDate(device.created_at)}
									</p>
								</div>
								<button
									onclick={() => removeDevice(device.id)}
									disabled={deletingId === device.id}
									aria-label="Remove topic"
									class="flex-shrink-0 rounded-md p-1.5 text-zinc-500 transition-colors
										hover:bg-zinc-800 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-50"
								>
									{#if deletingId === device.id}
										<svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
											<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
											<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
										</svg>
									{:else}
										<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="h-4 w-4">
											<path d="M5.28 4.22a.75.75 0 00-1.06 1.06L6.94 8l-2.72 2.72a.75.75 0 101.06 1.06L8 9.06l2.72 2.72a.75.75 0 101.06-1.06L9.06 8l2.72-2.72a.75.75 0 00-1.06-1.06L8 6.94 5.28 4.22z" />
										</svg>
									{/if}
								</button>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="px-5 py-4 text-sm text-zinc-600">No topics registered yet.</p>
				{/if}

				<!-- Add new topic -->
				<div class="border-t border-zinc-800 px-5 py-4">
					<div class="flex gap-2">
						<input
							type="text"
							bind:value={newTopic}
							placeholder="my-private-topic"
							class="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm
								text-zinc-100 placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none"
						/>
						<input
							type="text"
							bind:value={newLabel}
							placeholder="Label (optional)"
							class="w-36 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm
								text-zinc-100 placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none"
						/>
						<button
							onclick={addDevice}
							disabled={addingDevice || !newTopic.trim() || featureUnavailable}
							class="flex-shrink-0 rounded-lg bg-zinc-700 px-3 py-2 text-sm font-medium text-zinc-200
								transition-colors hover:bg-zinc-600 disabled:cursor-not-allowed disabled:opacity-50"
						>
							{addingDevice ? 'Adding…' : 'Add'}
						</button>
					</div>
					{#if addError}
						<p class="mt-2 text-xs text-red-400">{addError}</p>
					{/if}
					<p class="mt-2 text-xs text-zinc-600">
						Subscribe to this topic in the ntfy app to receive push notifications on your device.
					</p>
				</div>
			{/if}
		</section>
	{/if}

	<!-- Back link -->
	<div class="mt-6">
		<a href="/notifications" class="text-xs text-zinc-600 hover:text-zinc-400">
			← View notification feed
		</a>
	</div>
</div>
