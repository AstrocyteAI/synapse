"""Chat-with-tools surface — session lifecycle + agent loop.

Mirrors ``priv/contracts/chat-api-v1.openapi.json`` (Cerebro side) which both
backends implement under Model A parity. This package contains:

  * ``api_models`` — Pydantic request/response shapes
  * ``sessions``   — session CRUD service layer
  * ``messages``   — message append + agent loop (TBD next commit)
  * ``forks``      — conversation fork support (TBD next commit)

The append-only ``thread_events`` substrate (see ``synapse.db.models.Thread``
and ``ThreadEvent``) is the source of truth for chat history. ChatSession is
a thin metadata wrapper.
"""
