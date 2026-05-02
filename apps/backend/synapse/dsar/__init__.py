"""S-DSAR — Data Subject Access Request lifecycle for single-tenant Synapse.

This package implements the *basic* DSAR tier:

  * One queue per deployment (no cross-tenant view)
  * HMAC-SHA256 fulfilment certificates
  * Single-system erasure (Synapse Postgres + one Astrocyte gateway call)

For JWS-detached certificates, cross-tenant DSAR queues, or
multi-system erasure attestation, see Cerebro Enterprise:
``cerebro/docs/_design/control-plane.md``.

Public surface:

  * ``state_machine.create / approve / reject / mark_completed`` — the
    pending → approved → completed (or rejected) lifecycle, with
    ``InvalidStatusTransition`` raised on out-of-order transitions.
  * ``worker.run_erasure`` — called when a request is marked completed;
    cleans up Synapse-side rows for the subject and POSTs to Astrocyte
    ``/v1/dsar/forget_principal``. Updates the certificate with the
    final action list.
  * ``certificate.build_and_sign`` / ``certificate.verify`` — HMAC-SHA256
    canonical-JSON signing (deterministic — sorted keys, stripped
    whitespace) so an external auditor can verify a certificate against
    the deployment's signing secret.
"""

from synapse.dsar import certificate, state_machine, worker
from synapse.dsar.state_machine import InvalidStatusTransition

__all__ = [
    "InvalidStatusTransition",
    "certificate",
    "state_machine",
    "worker",
]
