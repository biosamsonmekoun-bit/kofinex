"""Cycle de vie d'un abonnement (docs/LOT12_SAAS_CONCEPTION.md, § 5.1 et § 8.1).

Le moteur d'abonnement est interne à KOFINEX : une passerelle de paiement n'écrit jamais l'état. L'activation n'a
lieu que sur un paiement vérifié par le serveur (événement `payment_verified`, étape 12B). La base impose les mêmes
transitions pour les opérations offertes au client (fonctions SQL de la migration 0018)."""

from __future__ import annotations

from datetime import datetime

STATES = ("trialing", "incomplete", "active", "past_due", "suspended", "canceled", "expired")
LIVE = ("trialing", "incomplete", "active", "past_due", "suspended")   # un seul par organisation (index unique)

# (état de départ, événement) → état d'arrivée ; None : création
TRANSITIONS: dict[tuple[str | None, str], str] = {
    (None, "start_trial"): "trialing",
    (None, "order_created"): "incomplete",
    ("trialing", "payment_verified"): "active",
    ("incomplete", "payment_verified"): "active",
    ("trialing", "trial_expired"): "expired",
    ("incomplete", "order_expired"): "expired",
    ("active", "due_unpaid"): "past_due",
    ("past_due", "payment_verified"): "active",
    ("past_due", "grace_ended"): "suspended",
    ("suspended", "payment_verified"): "active",
    # résiliation demandée par l'owner : effet à la date prévue (fin d'essai ou de période)
    ("trialing", "cancel_effective"): "canceled",
    ("active", "cancel_effective"): "canceled",
    # suspension prolongée au-delà du délai fixé par l'administrateur (aucun délai fixé : jamais)
    ("suspended", "cancel_effective"): "canceled",
}
# résiliation immédiate par l'administrateur, motif obligatoire (étape 12C)
for _s in LIVE:
    TRANSITIONS[(_s, "admin_cancel")] = "canceled"

# l'owner peut demander la résiliation (effet différé) et la retirer tant qu'elle n'a pas pris effet
CANCELLABLE = ("trialing", "active")


class TransitionError(ValueError):
    pass


def transition(state: str | None, event: str) -> str:
    try:
        return TRANSITIONS[(state, event)]
    except KeyError:
        raise TransitionError(f"Transition interdite : {state or 'création'} → {event}") from None


def effective_state(state: str, now: datetime, trial_end: datetime | None, cancel_at: datetime | None) -> str:
    """État à appliquer à l'instant `now`, même si la bascule planifiée n'a pas encore été écrite en base
    (les tâches planifiées arrivent avec l'étape 12B) : un essai échu vaut `expired`, une résiliation échue
    vaut `canceled`."""
    if state not in STATES:
        raise TransitionError(f"État inconnu : {state}")
    if cancel_at is not None and now >= cancel_at and state in CANCELLABLE:
        return "canceled"
    if state == "trialing" and trial_end is not None and now >= trial_end:
        return "expired"
    return state


def access(state: str | None, has_data: bool) -> str:
    """Accès donné par l'état (§ 8.1) : 'full', 'read_only' ou 'none'."""
    if state in ("trialing", "active", "past_due"):
        return "full"
    if state == "suspended":
        return "read_only"
    if state in (None, "incomplete", "expired", "canceled"):
        return "read_only" if has_data else "none"
    raise TransitionError(f"État inconnu : {state}")
