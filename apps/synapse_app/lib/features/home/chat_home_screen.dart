import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config/server_store.dart';
import '../../core/platform/platform_details.dart';
import '../../core/providers/services.dart';
import '../../core/routing/app_paths.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_typography.dart';
import '../conversations/conversation_ref.dart';
import '../conversations/conversations_provider.dart';

/// The first screen users see when they open Synapse.
///
/// Modeled on Slack / Microsoft Teams: a sidebar (channels / spaces /
/// councils) on the left, a main content panel on the right. When
/// disconnected from a server, the main panel shows a welcome card
/// with a "Connect to server" CTA — *not* a bare URL form.
///
/// Once the user is connected and signed in, the sidebar will populate
/// with their councils and the main panel will show the currently
/// selected conversation. Today (pre-Phase 4 Drift), it shows
/// placeholder content; the real conversation list lands when we
/// wire the offline-first message store.
class ChatHomeScreen extends ConsumerStatefulWidget {
  const ChatHomeScreen({super.key});

  @override
  ConsumerState<ChatHomeScreen> createState() => _ChatHomeScreenState();
}

class _ChatHomeScreenState extends ConsumerState<ChatHomeScreen> {
  late Future<_ConnectionState> _connection;

  @override
  void initState() {
    super.initState();
    _connection = _loadConnection();
  }

  Future<_ConnectionState> _loadConnection() async {
    final serverStore = ref.read(serverStoreProvider);
    final tokenStore = ref.read(tokenStoreProvider);
    final url = await serverStore.getUrl();
    final token = await tokenStore.getToken();
    final isCerebro = await serverStore.getIsCerebro();
    return _ConnectionState(
      serverUrl: url,
      hasToken: token != null,
      isCerebro: isCerebro,
    );
  }

  void _refreshConnection() {
    // Reload the connection snapshot AND blow away the cached
    // conversation list so it re-fetches against the (possibly newly
    // configured) server.
    ref.invalidate(conversationsProvider);
    setState(() {
      _connection = _loadConnection();
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDesktop = PlatformDetails().isDesktop;
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: isDesktop ? _buildDesktopLayout() : _buildMobileLayout(),
      ),
    );
  }

  // ── Desktop: persistent sidebar + main panel ────────────────────────
  Widget _buildDesktopLayout() {
    return Row(
      children: [
        _Sidebar(onConnectionChanged: _refreshConnection),
        const VerticalDivider(width: 1, color: AppColors.surfaceElevated),
        Expanded(
          child: FutureBuilder<_ConnectionState>(
            future: _connection,
            builder: (context, snap) {
              if (!snap.hasData) {
                return const Center(child: CircularProgressIndicator());
              }
              return _MainPanel(
                connection: snap.data!,
                onConnectionChanged: _refreshConnection,
              );
            },
          ),
        ),
      ],
    );
  }

  // ── Mobile: drawer-based sidebar, main panel takes the screen ──────
  Widget _buildMobileLayout() {
    return FutureBuilder<_ConnectionState>(
      future: _connection,
      builder: (context, snap) {
        if (!snap.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        return Scaffold(
          backgroundColor: AppColors.background,
          appBar: AppBar(
            title: const Text('Synapse'),
            backgroundColor: AppColors.surface,
          ),
          drawer: Drawer(
            backgroundColor: AppColors.surface,
            child: _Sidebar(onConnectionChanged: _refreshConnection),
          ),
          body: _MainPanel(
            connection: snap.data!,
            onConnectionChanged: _refreshConnection,
          ),
        );
      },
    );
  }
}

class _ConnectionState {
  const _ConnectionState({
    required this.serverUrl,
    required this.hasToken,
    required this.isCerebro,
  });
  final String? serverUrl;
  final bool hasToken;
  final bool isCerebro;

  bool get isConnected => serverUrl != null && hasToken;
}

// ── Sidebar ───────────────────────────────────────────────────────────

class _Sidebar extends ConsumerWidget {
  const _Sidebar({required this.onConnectionChanged});
  final VoidCallback onConnectionChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      width: 260,
      color: AppColors.surface,
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
            child: Row(
              children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: const BoxDecoration(
                    color: AppColors.brand,
                    shape: BoxShape.circle,
                  ),
                  alignment: Alignment.center,
                  child: const Icon(Icons.hub, size: 16, color: Colors.white),
                ),
                const SizedBox(width: AppSpacing.sm),
                const Text('Synapse', style: AppTypography.title),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          Expanded(child: _ConversationList()),
          const Divider(
            height: 1,
            thickness: 1,
            color: AppColors.surfaceElevated,
          ),
          const SizedBox(height: AppSpacing.xs),
          _SidebarSection(title: 'Knowledge', children: [
            _SidebarItem(
              icon: Icons.memory_outlined,
              label: 'Memory',
              onTap: () => context.go(AppPaths.memory),
            ),
            _SidebarItem(
              icon: Icons.bar_chart_outlined,
              label: 'Analytics',
              onTap: () => context.go(AppPaths.analytics),
            ),
          ]),
          const SizedBox(height: AppSpacing.xs),
          const Divider(
            height: 1,
            thickness: 1,
            color: AppColors.surfaceElevated,
          ),
          const SizedBox(height: AppSpacing.xs),
          _SidebarItem(
            icon: Icons.notifications_outlined,
            label: 'Notifications',
            onTap: () => context.go(AppPaths.notifications),
          ),
          _SidebarItem(
            icon: Icons.settings_outlined,
            label: 'Settings',
            onTap: () => context.go(AppPaths.settings),
          ),
        ],
      ),
    );
  }
}

class _SidebarSection extends StatelessWidget {
  const _SidebarSection({required this.title, required this.children});
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.xs,
          ),
          child: Text(
            title.toUpperCase(),
            style: AppTypography.caption.copyWith(
              color: AppColors.textTertiary,
              letterSpacing: 0.6,
            ),
          ),
        ),
        ...children,
      ],
    );
  }
}

class _SidebarItem extends StatelessWidget {
  const _SidebarItem({
    required this.icon,
    required this.label,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      hoverColor: AppColors.surfaceHover,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          children: [
            Icon(icon, size: 18, color: AppColors.textSecondary),
            const SizedBox(width: AppSpacing.sm),
            Text(label, style: AppTypography.body),
          ],
        ),
      ),
    );
  }
}

// ── Main panel ────────────────────────────────────────────────────────

class _MainPanel extends ConsumerWidget {
  const _MainPanel({
    required this.connection,
    required this.onConnectionChanged,
  });
  final _ConnectionState connection;
  final VoidCallback onConnectionChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.xxl),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Welcome to Synapse', style: AppTypography.display),
              const SizedBox(height: AppSpacing.sm),
              Text(
                connection.isConnected
                    ? 'Your team is connected. Open a council or start a new conversation.'
                    : 'Synapse is a multi-agent deliberation system — Slack-grade chat where humans and AI agents collaborate to make decisions.',
                style: AppTypography.body.copyWith(
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(height: AppSpacing.xl),
              if (!connection.isConnected)
                _ConnectCard(
                  serverUrl: connection.serverUrl,
                  hasToken: connection.hasToken,
                  onConnectionChanged: onConnectionChanged,
                )
              else
                _ConnectedActions(),
            ],
          ),
        ),
      ),
    );
  }
}

class _ConnectCard extends StatelessWidget {
  const _ConnectCard({
    required this.serverUrl,
    required this.hasToken,
    required this.onConnectionChanged,
  });
  final String? serverUrl;
  final bool hasToken;
  final VoidCallback onConnectionChanged;

  @override
  Widget build(BuildContext context) {
    final needsServer = serverUrl == null;
    final needsLogin = serverUrl != null && !hasToken;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppSpacing.sm),
        border: Border.all(color: AppColors.surfaceElevated),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.bolt_outlined,
                color: AppColors.brand,
                size: 20,
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                needsServer ? 'Connect your workspace' : 'Sign in to continue',
                style: AppTypography.heading,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            needsServer
                ? 'Point Synapse at your Cerebro backend to load your councils, memory, and team.'
                : 'Connected to $serverUrl. Sign in to load your team.',
            style: AppTypography.body.copyWith(
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.brand,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg,
                vertical: AppSpacing.sm,
              ),
            ),
            onPressed: () async {
              if (needsServer) {
                await context.push(AppPaths.serverSetup);
              } else if (needsLogin) {
                await context.push(AppPaths.login);
              }
              onConnectionChanged();
            },
            icon: const Icon(Icons.arrow_forward, size: 16),
            label: Text(needsServer ? 'Connect to server' : 'Sign in'),
          ),
        ],
      ),
    );
  }
}

class _ConnectedActions extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.brand,
            foregroundColor: Colors.white,
          ),
          onPressed: () => context.go(AppPaths.councilList),
          icon: const Icon(Icons.forum_outlined, size: 16),
          label: const Text('Open councils'),
        ),
        const SizedBox(width: AppSpacing.sm),
        OutlinedButton.icon(
          onPressed: () => context.go(AppPaths.councilCreate),
          icon: const Icon(Icons.add, size: 16),
          label: const Text('New council'),
        ),
      ],
    );
  }
}

// Silence unused-import lint for ServerStore — kept for documentation
// of where the connection state actually lives.
// ignore: unused_element
typedef _Keep = ServerStore;

// ── Conversation list (sidebar body) ──────────────────────────────────

class _ConversationList extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(conversationsProvider);

    return async.when(
      // Loading: small inline indicator at the top of the section.
      loading: () => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _sectionHeader('Conversations'),
          const Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: SizedBox(
              height: 16,
              width: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        ],
      ),
      // Error: inline retry. Don't shout — many failures here are
      // "not connected yet."
      error: (err, _) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _sectionHeader('Conversations'),
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            child: Row(
              children: [
                const Expanded(
                  child: Text(
                    'Couldn’t load conversations.',
                    style: AppTypography.caption,
                  ),
                ),
                TextButton(
                  onPressed: () => ref.invalidate(conversationsProvider),
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
        ],
      ),
      data: (items) {
        final councils = items
            .where((c) => c.kind == ConversationKind.council)
            .toList();
        final chats =
            items.where((c) => c.kind == ConversationKind.chat).toList();

        if (items.isEmpty) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _sectionHeader('Conversations'),
              const Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.sm,
                ),
                child: Text(
                  'No conversations yet. Start a council to begin.',
                  style: AppTypography.caption,
                ),
              ),
            ],
          );
        }

        return ListView(
          padding: EdgeInsets.zero,
          children: [
            if (councils.isNotEmpty) ...[
              _sectionHeaderWithAction(
                'Councils',
                actionIcon: Icons.add,
                actionTooltip: 'New council',
                onAction: () => context.go(AppPaths.councilCreate),
              ),
              for (final c in councils)
                _ConversationTile(
                  ref: c,
                  onTap: () => context.go(AppPaths.councilDetail(c.id)),
                ),
              const SizedBox(height: AppSpacing.sm),
            ],
            if (chats.isNotEmpty) ...[
              _sectionHeader('Chats'),
              for (final c in chats)
                _ConversationTile(
                  ref: c,
                  onTap: () => context.go(AppPaths.chatSessionDetail(c.id)),
                ),
            ],
          ],
        );
      },
    );
  }

  Widget _sectionHeader(String title) => Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        child: Text(
          title.toUpperCase(),
          style: AppTypography.caption.copyWith(
            color: AppColors.textTertiary,
            letterSpacing: 0.6,
          ),
        ),
      );

  Widget _sectionHeaderWithAction(
    String title, {
    required IconData actionIcon,
    required String actionTooltip,
    required VoidCallback onAction,
  }) =>
      Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.md,
          AppSpacing.xs,
          AppSpacing.xs,
          AppSpacing.xs,
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                title.toUpperCase(),
                style: AppTypography.caption.copyWith(
                  color: AppColors.textTertiary,
                  letterSpacing: 0.6,
                ),
              ),
            ),
            IconButton(
              icon: Icon(actionIcon, size: 16, color: AppColors.textSecondary),
              tooltip: actionTooltip,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(
                minWidth: 28,
                minHeight: 28,
              ),
              onPressed: onAction,
            ),
          ],
        ),
      );
}

class _ConversationTile extends StatelessWidget {
  const _ConversationTile({required this.ref, required this.onTap});
  final ConversationRef ref;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isCouncil = ref.kind == ConversationKind.council;
    return InkWell(
      onTap: onTap,
      hoverColor: AppColors.surfaceHover,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              isCouncil ? Icons.forum_outlined : Icons.chat_bubble_outline,
              size: 16,
              color: AppColors.textSecondary,
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    ref.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.body,
                  ),
                  if (isCouncil && ref.status != null) ...[
                    const SizedBox(height: 2),
                    _StatusPill(
                      status: ref.status!,
                      conflictDetected: ref.conflictDetected,
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status, required this.conflictDetected});
  final String status;
  final bool conflictDetected;

  Color get _color {
    switch (status) {
      case 'draft':
        return AppColors.statusDraft;
      case 'running':
        return AppColors.statusRunning;
      case 'waiting_contributions':
        return AppColors.statusWaitingContributions;
      case 'pending_approval':
        return AppColors.statusPendingApproval;
      case 'closed':
        return conflictDetected
            ? AppColors.statusFailed
            : AppColors.statusClosed;
      case 'failed':
        return AppColors.statusFailed;
      default:
        return AppColors.statusDraft;
    }
  }

  String get _label {
    switch (status) {
      case 'waiting_contributions':
        return 'waiting';
      case 'pending_approval':
        return 'pending';
      default:
        return status;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.xs,
        vertical: 1,
      ),
      decoration: BoxDecoration(
        color: _color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(AppSpacing.xxs),
      ),
      child: Text(
        _label,
        style: AppTypography.caption.copyWith(
          color: _color,
          fontSize: 10,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
