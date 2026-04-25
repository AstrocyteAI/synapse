# Integrations — messaging platforms

This document defines the messaging platform integrations for Synapse. Each integration brings council capabilities into the platforms where teams already work.

**Phase 1:** Slack · Discord · Telegram
**Phase 2:** Teams · Google Chat
**Phase 3:** Lark (larksuite + feishu.cn) · WeCom
**Phase 4:** WhatsApp Business · Mattermost · Line

For the chat interaction model (Modes 1–3), see `chat.md`. For the backend event system that drives outbound notifications, see `architecture.md`.

---

## 1. Design principles

**Meet teams where they are.** Council creation, verdict delivery, and follow-up questions should all be possible without leaving the platform teams already use.

**Integrations are thin adapters.** Each integration translates platform-specific events (slash commands, button clicks, mentions) into Synapse API calls, and formats Synapse events (stage progress, verdicts) into platform-native UI (Slack blocks, Adaptive Cards, Lark cards). Business logic lives in the Synapse backend, not in the integration.

**The backend does not know which platform sent a request.** Integrations call the same REST and WebSocket API as the web and desktop clients. They are consumers of the public Synapse API.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     Messaging Platforms                          │
│  Slack · Discord · Telegram · Teams · Google Chat               │
│  Lark · WeCom · WhatsApp · Mattermost · Line                    │
└────┬─────────────────────────────────────────────────────────────┘
     │ webhooks / bot events (inbound)
┌────▼─────────────────────────────────────────────────────────────┐
│              Integration Services (one per platform)             │
│   apps/integrations/{slack,discord,telegram,teams,…}/           │
└────────────────────────┬─────────────────────────────────────────┘
                         │  REST API calls
                         │  WebSocket (for live council streaming)
┌────────────────────────▼────────────────────────────────┐
│                  Synapse Backend                        │
│   Council Engine · Chat · Memory · Event Bus            │
└────────────────────────┬────────────────────────────────┘
                         │  outbound webhook events
                         │  (council_closed, stage_complete, etc.)
┌────────────────────────▼────────────────────────────────┐
│              Integration Services (outbound)            │
│   Format → post verdict card to channel                 │
└─────────────────────────────────────────────────────────┘
```

Each integration service is a lightweight Python app that:
1. Receives inbound events from its platform (slash commands, button clicks, mentions)
2. Calls the Synapse backend REST API
3. Receives outbound webhook events from Synapse
4. Formats and posts platform-native cards/messages to channels

---

## 3. Backend event bus

The Synapse backend emits webhook events to registered integration endpoints when council lifecycle events occur.

**Webhook registration** (in `synapse.yaml`):

```yaml
integrations:
  webhooks:
    - name: slack-workspace-acme
      url: ${SLACK_INTEGRATION_WEBHOOK_URL}
      secret: ${SLACK_INTEGRATION_WEBHOOK_SECRET}
      events:
        - council_closed
        - stage_complete
        - member_added
    - name: teams-channel-engineering
      url: ${TEAMS_INTEGRATION_WEBHOOK_URL}
      secret: ${TEAMS_INTEGRATION_WEBHOOK_SECRET}
      events:
        - council_closed
```

**Event payload:**

```json
{
  "event": "council_closed",
  "council_id": "cncl_abc123",
  "session": {
    "question": "Should we use event sourcing for the order service?",
    "verdict": "The council recommends event sourcing …",
    "confidence": "high",
    "member_count": 3,
    "closed_at": "2025-11-03T14:22:00Z"
  },
  "metadata": {
    "topic_tag": "architecture",
    "council_type": "llm",
    "started_by": "user:alice"
  }
}
```

Events are delivered with HMAC-SHA256 signatures (same pattern as GitHub webhooks). Integrations verify the signature before processing.

---

## 4. Capabilities (all platforms)

| Capability | How |
|-----------|-----|
| Start a council | Slash command / mention with question |
| Watch stage progress | Progress updates posted to thread as stages complete |
| Receive verdict | Rich card posted to channel when council closes |
| Approve / promote to precedents | Button on verdict card |
| Reject verdict | Button on verdict card |
| Ask follow-up (Mode 3) | Reply to verdict card → Synapse `reflect()` |
| Recall a precedent | Slash command / mention with query |
| List recent councils | Slash command |

---

## 5. Slack integration

**Technology:** Python + [Slack Bolt](https://slack.dev/bolt-python/)

**App configuration:**
- Slash commands: `/council`, `/recall`
- Event subscriptions: `app_mention`, `message.channels` (for threaded replies to verdict cards)
- Interactive components: buttons on verdict cards
- Bot scopes: `chat:write`, `commands`, `channels:history`, `reactions:write`

**Commands:**

```
/council Should we adopt a microservices architecture?
  → Starts a council; posts progress to channel thread

/council --members gpt-4o,claude,gemini --chairman claude-opus
  → Start with custom members

/recall What did we decide about GraphQL?
  → Calls Synapse recall; posts top 3 precedent hits as a card
```

**Verdict card (Block Kit):**

```
┌─────────────────────────────────────────────────────┐
│ 🏛 Council verdict — Architecture decision          │
│                                                     │
│ Question: Should we adopt microservices?            │
│                                                     │
│ Verdict: The council recommends a modular monolith  │
│ as the starting point, with clear service           │
│ boundaries for future extraction.                   │
│                                                     │
│ Confidence: High · 3 members · 4 min               │
│                                                     │
│ [✓ Approve]  [✗ Reject]  [View full council →]     │
└─────────────────────────────────────────────────────┘
```

Threaded replies to the verdict card are handled as Mode 3 chat — each reply calls `POST /v1/councils/{id}/chat` and the synthesised answer is posted back in the thread.

**Stage progress (threaded, collapsible):**

```
[Stage 1 — gathering]  GPT-4o · Claude · Gemini responding …  ✓
[Stage 2 — ranking]    Peer review complete — Claude ranked #1
[Stage 3 — synthesis]  Verdict ready ↑
```

---

## 6. Microsoft Teams integration

**Technology:** Python + [Microsoft Bot Framework SDK](https://github.com/microsoft/botbuilder-python)

**App configuration:**
- Bot registered in Azure Bot Service
- Deployed to Teams channel via Teams App manifest
- Message extension for `/council` and `/recall` commands
- Adaptive Cards for verdict display

**Commands:**

```
@Synapse council Should we migrate to Kubernetes?
  → Starts a council in the current channel

@Synapse recall event sourcing decisions
  → Returns top precedent hits as an Adaptive Card

@Synapse list
  → Lists recent councils in this team's workspace
```

**Verdict card (Adaptive Card):**

```json
{
  "type": "AdaptiveCard",
  "body": [
    { "type": "TextBlock", "text": "🏛 Council Verdict", "weight": "Bolder" },
    { "type": "TextBlock", "text": "Should we migrate to Kubernetes?" },
    { "type": "TextBlock", "text": "Verdict: The council recommends a phased migration …" },
    { "type": "FactSet", "facts": [
      { "title": "Confidence", "value": "High" },
      { "title": "Members", "value": "3" }
    ]}
  ],
  "actions": [
    { "type": "Action.Submit", "title": "✓ Approve", "data": { "action": "approve", "council_id": "…" } },
    { "type": "Action.Submit", "title": "✗ Reject", "data": { "action": "reject", "council_id": "…" } },
    { "type": "Action.OpenUrl", "title": "View full council", "url": "…" }
  ]
}
```

Replies to the verdict card in the Teams thread are handled as Mode 3 chat.

**Teams-specific:** councils can be scoped to a Team (maps to a Synapse tenant) and a Channel (maps to a memory bank tag). Verdicts are stored with `tenant_id` and `channel_tag` so recall is scoped by default.

---

## 7. Lark (Feishu) integration

**Technology:** Python + [Lark Open Platform SDK](https://open.larksuite.com/document)

**App configuration:**
- Lark Custom App with bot capability
- Event subscriptions: `im.message.receive_v1` (messages and commands)
- Card interactive callbacks for approve/reject buttons
- Bot added to target chats/channels

**Commands:**

```
/council Should we use DDD for the payment service?
  → Starts a council; posts progress card to chat

/recall payment architecture decisions
  → Returns precedent hits as a Lark interactive card

@Synapse list
  → Lists recent councils
```

**Verdict card (Lark Interactive Card):**

```
┌─────────────────────────────────────────────────────┐
│ 🏛 议会结论 / Council verdict                        │
│                                                     │
│ 问题 / Question:                                    │
│ Should we use DDD for the payment service?          │
│                                                     │
│ 结论 / Verdict:                                     │
│ The council recommends DDD for the payment service  │
│ given its complex domain rules and bounded          │
│ contexts around settlement and reconciliation.      │
│                                                     │
│ 置信度: 高 / Confidence: High  ·  成员: 3 members   │
│                                                     │
│ [✓ 批准 Approve]  [✗ 拒绝 Reject]  [查看详情 View →] │
└─────────────────────────────────────────────────────┘
```

Lark messages sent in reply to the verdict card are handled as Mode 3 chat.

**Lark-specific:** Lark supports both `larksuite.com` (international) and `feishu.cn` (China). The integration supports both endpoints via environment configuration (`LARK_BASE_URL`).

---

## 8. Telegram integration

**Technology:** Python + [python-telegram-bot](https://python-telegram-bot.org/) v21+

**Positioning:** Telegram has the best bot API of any platform — it is fast to implement, well-documented, and has a massive developer and open-source audience. It ships in Phase 1 alongside Slack and Discord.

**App configuration:**
- Bot created via BotFather; token stored as `TELEGRAM_BOT_TOKEN`
- Slash commands registered via `setMyCommands`
- Inline keyboard buttons for verdict interaction
- Webhook mode (preferred over polling for production)
- Group and private chat support

**Commands:**

```
/council Should we migrate our auth service to OAuth2?
  → Starts a council; posts stage progress as sequential messages

/council --members gpt-4o,claude,gemini Should we adopt GraphQL?
  → Custom members

/recall authentication architecture decisions
  → Returns top 3 precedent hits as a formatted message

/councils
  → Lists recent councils in this chat
```

**Verdict message + inline keyboard:**

```
🏛 Council Verdict

Question
Should we migrate our auth service to OAuth2?

Verdict
The council recommends OAuth2 with PKCE for the auth
service. All three members converged on security and
standards compliance as the primary drivers.

Confidence: High  ·  Members: 3  ·  Duration: 4m 12s

[✓ Approve]  [✗ Reject]  [View full council]
```

Replies to the verdict message in the same chat are handled as Mode 3 chat. In group chats, users must reply to the specific verdict message (using Telegram's reply feature) to trigger Mode 3.

**Stage progress** — posted as a single message that is edited in place as stages complete:

```
🏛 Council in progress…
✓ Stage 1 — gathering     3/3 responses collected
✓ Stage 2 — ranking       peer review complete
⟳ Stage 3 — synthesis    chairman working…
```

**Telegram-specific considerations:**

- **Group vs private chats:** `/council` works in both. Group chats scope memory to the chat ID; private chats are personal councils with no group scoping.
- **Supergroups and topics:** Telegram supergroups with topics (forum mode) scope councils to the topic ID for more granular memory separation.
- **Message length:** Telegram has a 4096-character message limit. Long verdicts are split across multiple messages automatically.
- **No native threading:** unlike Slack/Discord, Telegram does not have reply threads. Mode 3 chat uses message replies as the trigger instead.
- **Bot username:** users can also start councils via inline mode (`@SynapseBot Should we use Kafka?`) in any chat without adding the bot.

---

## 9. Discord integration

**Technology:** Python + [Pycord](https://pycord.dev/) (`py-cord`) — a maintained fork of `discord.py` with full slash command and component support.

**Positioning:** Discord is the most likely platform for developers and open-source communities to discover Synapse before adopting it at work. It should be prioritised alongside Slack rather than treated as a later phase.

**App configuration:**
- Discord Application with Bot user
- Slash commands registered per-guild via Discord Interactions API
- Message components (buttons) for verdict interaction
- Thread auto-creation on verdict messages for Mode 3 chat
- Intents: `guilds`, `guild_messages`, `message_content`

**Commands:**

```
/council question: Should we adopt a monorepo structure?
  → Starts a council; posts stage progress to channel

/council question: Should we use Rust for the parser?
           members: gpt-4o,claude,gemini
           chairman: claude-opus
  → Start with custom members and chairman

/recall query: monorepo decisions
  → Returns top precedent hits as an embed

/councils
  → Lists recent councils in this server
```

**Verdict embed + components:**

```
┌─────────────────────────────────────────────────────────┐
│ 🏛 Council Verdict                                      │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│ Question                                                │
│ Should we adopt a monorepo structure?                   │
│                                                         │
│ Verdict                                                 │
│ The council recommends a monorepo with Turborepo.       │
│ All three members agreed on the tooling benefits for    │
│ a team of this size.                                    │
│                                                         │
│ Confidence   Members   Duration                         │
│ High         3         3 min 42 sec                     │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│ [✓ Approve]  [✗ Reject]  [View full council]           │
└─────────────────────────────────────────────────────────┘
```

The verdict message automatically spawns a **Discord thread** titled "Follow-up — [question]". All messages in that thread are handled as Mode 3 chat (`POST /v1/councils/{id}/chat` → Astrocyte `reflect()`). This maps naturally to how Discord communities already discuss announcements.

**Stage progress** is posted as sequential edits to a single "council in progress" message, keeping the channel clean:

```
🏛 Council in progress — Should we adopt a monorepo structure?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Stage 1 — gathering    3 responses collected
⟳ Stage 2 — ranking     peer review in progress …
  Stage 3 — synthesis
```

**Discord-specific considerations:**

- **Guild → tenant mapping:** each Discord server (guild) maps to a Synapse tenant. Guild ID is the tenant key.
- **Channel → memory scope:** verdicts are tagged with the channel ID so `/recall` is scoped to the current channel by default. Use `/recall --global` to search across all channels.
- **Server boost / Nitro:** Discord file size limits affect whether full council transcripts can be attached. For large councils, a link to the web UI is used instead of a file attachment.
- **DM support:** `/council` in a DM with the bot runs a personal council with no channel scoping — useful for individual exploration before bringing a question to the team.
- **Rate limits:** Discord's interaction response window is 3 seconds. The initial `/council` response is an immediate acknowledgement ("Starting council…"); stage updates arrive as follow-up messages using the interaction token's 15-minute window.

---

## 10. Phase 2 — Teams and Google Chat

### Microsoft Teams

**Technology:** Python + Microsoft Bot Framework SDK. See section 6 for full detail.

Teams completes the enterprise suite alongside Slack. Primary audience: organisations running Microsoft 365.

### Google Chat

**Technology:** Python + [Google Chat API](https://developers.google.com/workspace/chat) (HTTP webhooks + Cards v2).

**Key characteristics:**
- Space-scoped bots — Synapse bot is added to a Google Chat Space (equivalent to a Slack channel)
- Slash commands: `/council`, `/recall`
- Cards v2 for verdict display with action buttons (approve, reject, view)
- Thread-based Mode 3 chat via reply events in the Space
- Google Workspace identity — user email maps to Synapse principal directly
- Space ID → Synapse tenant; thread ID → council session scope

---

## 11. Phase 3 — Lark and WeCom

### Lark (Feishu)

**Technology:** Python + Lark Open Platform SDK. See section 7 for full detail.

Targets both `larksuite.com` (international) and `feishu.cn` (China) via `LARK_BASE_URL` config.

### WeCom (企业微信 / Enterprise WeChat)

**Technology:** Python + [WeCom API](https://developer.work.weixin.qq.com/).

**Key characteristics:**
- Corporate WeChat — distinct from consumer WeChat; has full bot and webhook support
- Application registered in the WeCom admin console
- Text + Markdown messages for stage progress and verdicts (WeCom card support is more limited than Lark)
- Button interactions via WeCom's menu and interactive message APIs
- Enterprise ID → Synapse tenant; department/group → memory bank tag
- Natural pairing with Lark feishu.cn — organisations using one often use the other

---

## 12. Phase 4 — WhatsApp Business, Mattermost, Line

### WhatsApp Business

**Technology:** Python + [Meta Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/).

- Requires Meta Business account and verified phone number
- Message templates (pre-approved by Meta) for outbound verdict notifications
- Interactive buttons for approve/reject
- Global reach — critical for SE Asia, LATAM, Middle East, Africa markets
- No slash commands; keyword-based triggers (`council:` prefix) or button menus

### Mattermost

**Technology:** Python + Mattermost REST API + outgoing webhooks.

- Open-source Slack alternative; self-hosted by compliance-sensitive organisations
- Near-identical interaction model to Slack (slash commands, attachments, interactive dialogs)
- Lowest implementation cost of any platform — Mattermost's API is Slack-compatible enough that most Slack integration code ports directly
- Appeals to orgs that cannot use cloud-hosted Slack/Teams for compliance reasons

### Line

**Technology:** Python + [Line Messaging API](https://developers.line.biz/en/docs/messaging-api/).

- Dominant in Japan, Thailand, Taiwan, Indonesia
- Flex Messages for rich verdict cards with buttons
- Line Official Account required (business registration)
- Reply token model — responses must be sent within a short window of the user's message
- Group chat, multi-person chat, and 1:1 chat all supported

---

## 13. Project structure

```
synapse/
└── apps/
    └── integrations/
        │
        │  ── Phase 1 ──────────────────────────────────────────
        ├── slack/
        │   ├── synapse_slack/
        │   │   ├── app.py          # Slack Bolt app
        │   │   ├── commands.py     # /council, /recall handlers
        │   │   ├── events.py       # Inbound webhook handlers
        │   │   ├── blocks.py       # Block Kit card builders
        │   │   └── client.py       # Synapse API client
        │   ├── pyproject.toml
        │   └── Dockerfile
        │
        ├── discord/
        │   ├── synapse_discord/
        │   │   ├── app.py          # Pycord bot entrypoint
        │   │   ├── commands.py     # /council, /recall, /councils
        │   │   ├── events.py       # Interaction handlers
        │   │   ├── embeds.py       # Embed + component builders
        │   │   ├── threads.py      # Verdict thread + Mode 3 relay
        │   │   └── client.py       # Synapse API client
        │   ├── pyproject.toml
        │   └── Dockerfile
        │
        ├── telegram/
        │   ├── synapse_telegram/
        │   │   ├── app.py          # python-telegram-bot entrypoint
        │   │   ├── commands.py     # /council, /recall, /councils
        │   │   ├── events.py       # Webhook + reply handlers
        │   │   ├── messages.py     # Message + inline keyboard builders
        │   │   └── client.py       # Synapse API client
        │   ├── pyproject.toml
        │   └── Dockerfile
        │
        │  ── Phase 2 ──────────────────────────────────────────
        ├── teams/
        │   ├── synapse_teams/
        │   │   ├── app.py          # Bot Framework adapter
        │   │   ├── bot.py          # Activity handler
        │   │   ├── commands.py     # @mention + message extension handlers
        │   │   ├── cards.py        # Adaptive Card builders
        │   │   └── client.py       # Synapse API client
        │   ├── pyproject.toml
        │   └── Dockerfile
        │
        ├── google_chat/
        │   ├── synapse_google_chat/
        │   │   ├── app.py          # FastAPI webhook receiver
        │   │   ├── commands.py     # Slash command handlers
        │   │   ├── cards.py        # Cards v2 builders
        │   │   └── client.py       # Synapse API client
        │   ├── pyproject.toml
        │   └── Dockerfile
        │
        │  ── Phase 3 ──────────────────────────────────────────
        ├── lark/
        │   ├── synapse_lark/
        │   │   ├── app.py          # Lark event dispatcher
        │   │   ├── commands.py     # /council, /recall, @mention
        │   │   ├── events.py       # Inbound webhook handlers
        │   │   ├── cards.py        # Lark interactive card builders
        │   │   └── client.py       # Synapse API client
        │   ├── pyproject.toml
        │   └── Dockerfile
        │
        ├── wecom/
        │   ├── synapse_wecom/
        │   │   ├── app.py          # WeCom event receiver
        │   │   ├── commands.py     # Command + menu handlers
        │   │   ├── messages.py     # Markdown + card builders
        │   │   └── client.py       # Synapse API client
        │   ├── pyproject.toml
        │   └── Dockerfile
        │
        │  ── Phase 4 ──────────────────────────────────────────
        ├── whatsapp/               # Meta Cloud API
        ├── mattermost/             # Mattermost webhooks (Slack-compatible)
        └── line/                   # Line Messaging API
```

Each integration's `client.py` is a thin wrapper around the Synapse REST API. A shared `synapse-client-py` package will be extracted after Phase 1 ships to eliminate duplication across integrations.

---

## 14. Capability matrix

| Capability | Slack | Discord | Telegram | Teams | G Chat | Lark | WeCom |
|-----------|:-----:|:-------:|:--------:|:-----:|:------:|:----:|:-----:|
| Start council via command | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Custom members / chairman | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Stage progress updates | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Verdict card in channel | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Approve / promote to precedents | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Reject verdict | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Mode 3 chat (reply to verdict) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Recall precedent via command | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Channel-scoped recall | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Auto-thread on verdict | — | ✓ | — | — | — | — | — |
| DM / personal council | — | ✓ | ✓ | — | — | — | — |
| Inline bot mode | — | — | ✓ | — | — | — | — |
| Feishu/CN endpoint | — | — | — | — | — | ✓ | — |
| Workspace identity (SSO) | — | — | — | ✓ | ✓ | ✓ | ✓ |
| Human join council in-channel | — | — | — | — | — | — | — |

Human-in-the-loop council participation (Mode 2) is out of scope for messaging integrations in Phase 1. Thread/reply-based Mode 3 chat covers the common case across all platforms.

---

## 15. Phases

| Phase | Platforms | Rationale |
|-------|-----------|-----------|
| **Phase 1** | Slack · Discord · Telegram | Developer audience; best bot APIs; fastest to ship |
| **Phase 2** | Teams · Google Chat | Enterprise suite; completes workplace coverage |
| **Phase 3** | Lark · WeCom | Asian market; feishu.cn + enterprise WeChat |
| **Phase 4** | WhatsApp Business · Mattermost · Line | Global reach; self-hosted; SE Asian markets |
| **Phase 5** | `synapse-client-py` extracted; Mode 2 (human join) from channels | Shared client library; full human-in-the-loop across all platforms |

---

## Further reading

- [Chat](chat.md) — Mode 3 chat with verdict (the interaction model used by thread replies)
- [Architecture](architecture.md) — backend event bus, webhook registration, outbound events
- [Project structure](project-structure.md) — integrations directory layout
