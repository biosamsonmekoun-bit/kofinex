"""Fichier des Écritures Comptables (FEC) — DGI Bénin (moteur pur, sans accès à la base).

Texte appliqué : arrêté n° 1085/MEF/CAB/SGM/DGI/DLC/159SGG20 du 23 avril 2020 portant modalités et normes de
présentation du FEC (copie numérisée signée, 6 pages, lue le 19 novembre 2026). Ce n'est PAS le FEC français.

- Art. 2 : écritures validées, classées par ordre chronologique de validation, après inventaire, par livre comptable ;
  écritures de report comprises ; ni écritures de centralisation, ni soldes des comptes de charges et de produits.
- Art. 4 : fichier plat CSV ou TXT ; jeux ASCII, ISO 8859-15 ou EBCDIC ; une ligne = une écriture comptable, terminée par
  retour chariot et/ou fin de ligne ; zones séparées par une tabulation « ou le caractère « » » (second caractère absent
  du texte signé) ; valeurs numériques en caractères, base décimale, signe en premier caractère, virgule décimale, aucun
  séparateur de milliers ; cadrage et remplissage pour les zones de longueur fixe ; dates AAAAMMJJ.
- Art. 5 : 18 champs dans l'ordre, caractère obligatoire de chacun ; Montant / Sens seulement si le système ne tient pas
  MontDebit et MontCredit (KOFINEX les tient : non proposé) ; 3 champs de la comptabilité de trésorerie ; écritures de
  report : premiers numéros et LibEcriture « REPORT ».
- Art. 6 : nom FEC_IFU_AAAAMMJJ (date de clôture) ; fractionnement FEC_IFU_AAAAMMJJ_X, X de 1 à n.
- Art. 7 : documentation (nom, description, signification des champs, jeu de caractères, séparateurs).

Les points du texte qui ne permettent pas de trancher sont listés dans `UNCONFIRMED` : tant qu'il en reste, un fichier
sans anomalie bloquante est déclaré « points réglementaires à confirmer » et jamais « conforme ».
Montants : Decimal uniquement. Aucune écriture n'est modifiée : les contrôles signalent, ils ne corrigent pas.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

SPEC_VERSION = "Arrêté n° 1085/MEF/CAB/SGM/DGI/DLC/159SGG20 du 23 avril 2020 — KOFINEX 2"
GENERATOR_VERSION = "kofinex-fec-bj/2.0"
LOCAL_TZ = ZoneInfo("Africa/Porto-Novo")  # date de validation exprimée à l'heure du Bénin


@dataclass(frozen=True)
class FieldSpec:
    order: int
    name: str
    information: str  # « Information portée par le champ » (art. 5)
    type: str  # Alphanumérique | Date | Numérique
    mandatory: bool  # « Valeur obligatoire (OUI/NON) »
    value_format: str  # « Format de la valeur »
    kofinex_source: str  # origine de la donnée dans KOFINEX


# Article 5 de l'arrêté (tableau des 18 premiers champs)
FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec(1, "CodeJournal", "Le code du journal de l'écriture comptable", "Alphanumérique", True, "", "Code du journal"),
    FieldSpec(2, "LibJournal", "Libellé du journal de l'écriture comptable", "Alphanumérique", True, "", "Intitulé du journal"),
    FieldSpec(
        3,
        "NumEcriture",
        "Numéro séquentiel continu de l'écriture comptable",
        "Alphanumérique",
        True,
        "",
        "Numéro définitif attribué à la validation, continu par journal et par exercice",
    ),
    FieldSpec(
        4, "DateEcriture", "Date de la comptabilisation de l'écriture comptable", "Date", True, "AAAAMMJJ", "Date de l'écriture"
    ),
    FieldSpec(
        5,
        "NumCompte",
        "Numéro du compte de l'écriture comptable",
        "Alphanumérique",
        True,
        "Les trois premiers caractères doivent correspondre à des chiffres respectant les normes du plan comptable SYSCOHADA",
        "Compte du plan de l'entreprise rattaché au plan du référentiel SYSCOHADA publié",
    ),
    FieldSpec(
        6,
        "LibCompte",
        "Libellé du compte de l'écriture comptable",
        "Alphanumérique",
        True,
        "Doit respecter la nomenclature du plan comptable SYSCOHADA",
        "Intitulé du compte dans le plan de l'entreprise",
    ),
    FieldSpec(
        7,
        "NumCompteAux",
        "Numéro du compte auxiliaire de l'écriture comptable",
        "Alphanumérique",
        False,
        "",
        "Code du tiers de la ligne",
    ),
    FieldSpec(
        8,
        "LibCompteAux",
        "Libellé du compte auxiliaire de l'écriture comptable",
        "Alphanumérique",
        False,
        "",
        "Nom du tiers de la ligne",
    ),
    FieldSpec(
        9,
        "RefPiece",
        "Référence de la pièce justificative de l'écriture comptable",
        "Alphanumérique",
        True,
        "",
        "Référence de la pièce saisie sur l'écriture",
    ),
    FieldSpec(
        10,
        "DatePiece",
        "Date de la pièce justificative de l'écriture comptable",
        "Date",
        True,
        "AAAAMMJJ",
        "Date de la pièce saisie sur l'écriture",
    ),
    FieldSpec(
        11,
        "LibEcriture",
        "Libellé de l'écriture comptable",
        "Alphanumérique",
        True,
        "",
        "Libellé de la ligne, à défaut de l'écriture ; « REPORT » pour les écritures de reprise des soldes",
    ),
    FieldSpec(
        12,
        "MontDebit",
        "Le montant au débit de l'écriture comptable",
        "Numérique",
        True,
        "",
        "Montant au débit de la ligne (0,00 si la ligne est au crédit)",
    ),
    FieldSpec(
        13,
        "MontCredit",
        "Le montant au crédit de l'écriture comptable",
        "Numérique",
        True,
        "",
        "Montant au crédit de la ligne (0,00 si la ligne est au débit)",
    ),
    FieldSpec(14, "LetEcriture", "Lettrage de l'écriture comptable", "Alphanumérique", False, "", "Code de lettrage"),
    FieldSpec(15, "DateLetEcriture", "Date de lettrage de l'écriture comptable", "Date", False, "AAAAMMJJ", "Date du lettrage"),
    FieldSpec(
        16,
        "DateValid",
        "Date de validation de l'écriture comptable",
        "Date",
        True,
        "AAAAMMJJ",
        "Date de validation (heure du Bénin)",
    ),
    FieldSpec(
        17,
        "MontDevise",
        "Montant en devise de l'écriture comptable",
        "Numérique",
        False,
        "",
        "Montant en devise de la ligne, si l'opération est en devise",
    ),
    FieldSpec(
        18,
        "CodeDevise",
        "Code de la devise du montant de l'écriture comptable",
        "Alphanumérique",
        False,
        "",
        "Code ISO 4217 de la devise, si l'opération est en devise",
    ),
)
# Comptabilité de trésorerie (contribuable imposable à l'impôt sur le revenu) : champs 19 à 21
CASH_FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec(19, "Date Règlement", "La date de règlement", "Date", True, "AAAAMMJJ", "Non tenue par KOFINEX"),
    FieldSpec(20, "Mode Règlement", "Le mode de règlement", "Alphanumérique", True, "", "Non tenu par KOFINEX"),
    FieldSpec(21, "NatOp", "La nature de l'opération", "Alphanumérique", False, "", "Non tenue par KOFINEX"),
)
FIELDS: tuple[str, ...] = tuple(f.name for f in FIELD_SPECS)
CASH_FIELDS: tuple[str, ...] = tuple(f.name for f in CASH_FIELD_SPECS)

# Art. 4 : « une tabulation ou le caractère « » » — seul le premier séparateur est lisible dans le texte signé
SEPARATORS = {"tab": "\t"}
SEPARATOR_LABELS = {"tab": "Tabulation (caractère de code 9)"}
# Art. 4 : chaque ligne « doit se terminer par retour chariot et/ou Fin de ligne »
RECORD_SEPARATORS = {"crlf": "\r\n", "lf": "\n", "cr": "\r"}
RECORD_LABELS = {
    "crlf": "Retour chariot et fin de ligne (CR LF, codes 13 et 10)",
    "lf": "Fin de ligne (LF, code 10)",
    "cr": "Retour chariot (CR, code 13)",
}
ENCODINGS = {"ascii": "ascii", "iso-8859-15": "iso8859_15"}
ENCODING_LABELS = {"ascii": "ASCII", "iso-8859-15": "ISO 8859-15 (Latin-9)"}
FORMATS = ("txt", "csv")

# Points que le texte ne permet pas de trancher (ou que KOFINEX ne peut pas vérifier automatiquement)
UNCONFIRMED: tuple[dict, ...] = (
    {
        "key": "second_separator",
        "label": "Second caractère séparateur des zones (art. 4)",
        "detail": "Le texte signé indique « une tabulation ou le caractère « » » sans le caractère : "
        "seule la tabulation est proposée.",
    },
    {
        "key": "ebcdic",
        "label": "Encodage EBCDIC (art. 4)",
        "detail": "Autorisé, mais la page de code EBCDIC n'est pas précisée : non proposé (ASCII et ISO 8859-15 le sont).",
    },
    {
        "key": "numbering",
        "label": "Portée de la continuité de NumEcriture (art. 5)",
        "detail": "« Numéro séquentiel continu » : KOFINEX numérote de façon continue par journal et par exercice ; le texte ne "
        "précise pas si la continuité s'entend par journal ou pour tout le fichier.",
    },
    {
        "key": "centralisation",
        "label": "Exclusion des écritures de centralisation et des soldes des comptes de gestion (art. 2)",
        "detail": "KOFINEX ne produit aucune de ces écritures (clôture non livrée) ; "
        "une écriture saisie manuellement à cette fin ne "
        "peut pas être reconnue automatiquement et doit être vérifiée par l'utilisateur.",
    },
)
APPLIED: tuple[dict, ...] = (
    {
        "key": "record_separator",
        "label": "Séparateur des enregistrements (art. 4)",
        "detail": "Retour chariot et/ou fin de ligne : CR LF, LF ou CR, au choix.",
    },
    {
        "key": "header_line",
        "label": "Ligne d'en-tête (art. 4 et 7)",
        "detail": "Aucune : chaque ligne correspond à une écriture comptable ; "
        "les noms des champs figurent dans la documentation.",
    },
    {
        "key": "padding",
        "label": "Cadrage et remplissage (art. 4)",
        "detail": "Applicables aux zones de longueur fixe ; l'article 5 ne fixe aucune longueur : zones de longueur variable, "
        "sans remplissage.",
    },
    {
        "key": "splitting",
        "label": "Fractionnement (art. 6)",
        "detail": "Fichier unique FEC_IFU_AAAAMMJJ ; si l'utilisateur fixe un nombre maximal de lignes, fichiers "
        "FEC_IFU_AAAAMMJJ_1 à FEC_IFU_AAAAMMJJ_n (aucun seuil n'est fixé par le texte).",
    },
    {
        "key": "cash_fields",
        "label": "Champs 19 à 21 (art. 5)",
        "detail": "Date Règlement (date, obligatoire, AAAAMMJJ), Mode Règlement (obligatoire), NatOp (facultatif).",
    },
    {
        "key": "mandatory_fields",
        "label": "Valeurs obligatoires (art. 5)",
        "detail": "Zone obligatoire vide : anomalie bloquante ; zone facultative vide : laissée vide.",
    },
)
SPEC_CONFIRMED = not UNCONFIRMED  # faux tant qu'un point reste à confirmer : jamais « conforme »


@dataclass(frozen=True)
class FecLine:
    """Une ligne d'écriture native validée, telle que lue dans les livres (aucune donnée ajoutée)."""

    entry_id: str
    line_id: str
    journal_code: str
    journal_label: str
    number: str | None
    sequence_no: int | None
    entry_date: date
    line_no: int
    account: str
    account_label: str | None
    debit: Decimal
    credit: Decimal
    validated_at: datetime | None
    origin: str = "manual"
    status: str = "validated"
    piece_ref: str | None = None
    piece_date: date | None = None
    entry_label: str | None = None
    line_label: str | None = None
    aux_code: str | None = None
    aux_label: str | None = None
    requires_third_party: bool = False
    lettering_code: str | None = None
    lettering_date: date | None = None
    currency: str | None = None
    currency_amount: Decimal | None = None
    chart_account: str | None = None  # compte du plan du référentiel auquel le compte est rattaché
    chart_label: str | None = None  # intitulé de ce compte dans le référentiel


@dataclass(frozen=True)
class FecOptions:
    file_format: str
    encoding: str
    record_separator: str
    field_separator: str = "tab"
    accounting_type: str = "accrual"
    max_lines_per_file: int | None = None  # fractionnement (art. 6), à la demande de l'utilisateur

    def validate(self) -> list[str]:
        errs = []
        if self.file_format not in FORMATS:
            errs.append("Format : txt ou csv.")
        if self.encoding not in ENCODINGS:
            errs.append("Encodage : ascii ou iso-8859-15.")
        if self.field_separator not in SEPARATORS:
            errs.append("Séparateur des zones : tabulation (seul séparateur lisible dans l'arrêté).")
        if self.record_separator not in RECORD_SEPARATORS:
            errs.append("Séparateur des enregistrements : crlf, lf ou cr.")
        if self.accounting_type not in ("accrual", "cash"):
            errs.append("Type de comptabilité : accrual (engagement) ou cash (trésorerie).")
        if self.max_lines_per_file is not None and self.max_lines_per_file < 1:
            errs.append("Nombre maximal de lignes par fichier : au moins 1.")
        return errs

    @property
    def specs(self) -> tuple[FieldSpec, ...]:
        return FIELD_SPECS + (CASH_FIELD_SPECS if self.accounting_type == "cash" else ())

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.specs)


@dataclass(frozen=True)
class FyEntry:
    """Écriture validée de l'exercice entier (contrôles de numérotation et de rang des écritures de report)."""

    entry_id: str
    journal_code: str
    sequence_no: int | None
    origin: str
    validated_at: datetime | None


@dataclass
class FecContext:
    ifu: str | None
    country_code: str | None
    framework_code: str | None
    fy_start: date
    fy_end: date
    fy_closed: bool
    period_start: date
    period_end: date
    has_previous_fy: bool
    imported_ledger_active: bool
    pending: dict[str, int] = field(default_factory=dict)  # écritures non validées de la période, par statut
    fy_entries: list[FyEntry] = field(default_factory=list)


@dataclass(frozen=True)
class Anomaly:
    code: str
    severity: str  # blocking | warning
    nature: str
    description: str
    action: str
    entry_id: str | None = None
    number: str | None = None
    entry_date: date | None = None
    journal: str | None = None
    account: str | None = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "nature": self.nature,
            "description": self.description,
            "action": self.action,
            "entry_id": self.entry_id,
            "number": self.number,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "journal": self.journal,
            "account": self.account,
        }


# ---------------------------------------------------------------------------------------------------------- formats
def fmt_date(d: date | None) -> str:
    return d.strftime("%Y%m%d") if d else ""


def fmt_amount(v: Decimal | None) -> str:
    """Valeur numérique en caractères, base décimale, signe en premier caractère, virgule décimale, sans séparateur de
    milliers, zone de longueur variable (« 1234567,50 », « -12,00 »)."""
    if v is None:
        return ""
    if not isinstance(v, Decimal):
        raise TypeError("Montant : Decimal attendu")
    return f"{v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):f}".replace(".", ",")


def validation_date(ts: datetime | None) -> date | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(LOCAL_TZ).date()


def filename(ifu: str, fy_end: date, file_format: str, part: int | None = None) -> str:
    """Art. 6 : FEC_IFU_AAAAMMJJ, ou FEC_IFU_AAAAMMJJ_X pour un fichier scindé."""
    return f"FEC_{ifu}_{fy_end:%Y%m%d}{'' if part is None else f'_{part}'}.{file_format}"


def _utc(ts: datetime | None) -> datetime:
    if ts is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def order_key(ln: FecLine) -> tuple:
    """Art. 2 : ordre chronologique de validation, puis livre (journal), numéro et rang de ligne."""
    return (_utc(ln.validated_at), ln.journal_code, ln.sequence_no or 0, ln.number or "", ln.line_no)


def lib_ecriture(ln: FecLine) -> str:
    if ln.origin == "opening":
        return "REPORT"
    return (ln.line_label or "").strip() or (ln.entry_label or "").strip()


def row(ln: FecLine, opts: FecOptions) -> list[str]:
    values = [
        ln.journal_code,
        ln.journal_label or "",
        ln.number or "",
        fmt_date(ln.entry_date),
        ln.account,
        ln.account_label or "",
        ln.aux_code or "",
        ln.aux_label or "",
        ln.piece_ref or "",
        fmt_date(ln.piece_date),
        lib_ecriture(ln),
        fmt_amount(ln.debit),
        fmt_amount(ln.credit),
        ln.lettering_code or "",
        fmt_date(ln.lettering_date),
        fmt_date(validation_date(ln.validated_at)),
        fmt_amount(ln.currency_amount) if ln.currency else "",
        ln.currency or "",
    ]
    if opts.accounting_type == "cash":
        values += ["", "", ""]  # données non tenues par KOFINEX : jamais inventées (anomalie bloquante)
    return values


def ordered(lines: list[FecLine]) -> list[FecLine]:
    return sorted(lines, key=order_key)


# --------------------------------------------------------------------------------------------------------- contrôles
PENDING_LABELS = {"draft": "brouillon(s)", "submitted": "soumise(s)", "under_review": "en revue", "rejected": "rejetée(s)"}
REENTER = "L'écriture validée n'est pas modifiable : l'extourner puis la ressaisir avec l'information manquante."


def _a(code, severity, nature, description, action, ln: FecLine | None = None, **kw) -> Anomaly:
    if ln is not None:
        kw = {
            "entry_id": ln.entry_id,
            "number": ln.number,
            "entry_date": ln.entry_date,
            "journal": ln.journal_code,
            "account": ln.account,
            **kw,
        }
    return Anomaly(code, severity, nature, description, action, **kw)


def _source_controls(lines: list[FecLine], ctx: FecContext) -> list[Anomaly]:
    out: list[Anomaly] = []
    if ctx.imported_ledger_active and not lines:
        out.append(
            _a(
                "SOURCE_IMPORTED_ONLY",
                "blocking",
                "Source des écritures",
                "Aucune écriture native validée sur la période ; les écritures de l'exercice proviennent d'un grand livre "
                "importé, donc tenu dans un autre logiciel.",
                "Produire le FEC depuis le logiciel où la comptabilité est tenue, ou tenir la comptabilité dans KOFINEX.",
            )
        )
    elif not lines:
        out.append(
            _a(
                "NO_ENTRIES",
                "blocking",
                "Aucune écriture",
                "Aucune écriture validée sur la période.",
                "Valider les écritures de la période ou choisir une autre période.",
            )
        )
    if ctx.imported_ledger_active and lines:
        out.append(
            _a(
                "IMPORTED_NOT_INCLUDED",
                "warning",
                "Source des écritures",
                "Un grand livre importé est actif sur l'exercice : il n'est pas repris, seules les écritures natives "
                "validées le sont (pas de doublon).",
                "Vérifier que la comptabilité n'est pas tenue en double (logiciel externe et KOFINEX).",
            )
        )
    if not (ctx.ifu or "").strip():
        out.append(
            _a(
                "IFU_MISSING",
                "blocking",
                "IFU absent",
                "L'IFU de l'entreprise n'est pas renseigné : le nom FEC_IFU_AAAAMMJJ ne peut pas être formé (art. 6).",
                "Renseigner l'IFU dans les informations de l'entreprise.",
            )
        )
    elif not re.fullmatch(r"[A-Za-z0-9]+", ctx.ifu.strip()):
        out.append(
            _a(
                "IFU_FORMAT",
                "blocking",
                "IFU invalide",
                "L'IFU contient des caractères autres que des lettres et des chiffres ; il n'est pas modifié automatiquement.",
                "Corriger l'IFU dans les informations de l'entreprise.",
            )
        )
    if (ctx.country_code or "").upper() != "BJ":
        out.append(
            _a(
                "COUNTRY_NOT_BJ",
                "warning",
                "Pays de l'entreprise",
                "Le pays de l'entreprise n'est pas le Bénin : le FEC béninois peut ne pas être applicable.",
                "Vérifier le pays renseigné pour l'entreprise.",
            )
        )
    if ctx.framework_code and ctx.framework_code != "SYSCOHADA_REV":
        out.append(
            _a(
                "FRAMEWORK",
                "warning",
                "Référentiel comptable",
                f"L'entreprise relève du référentiel {ctx.framework_code} ; "
                "l'arrêté renvoie au plan comptable SYSCOHADA (champs 5 et 6).",
                "Vérifier l'applicabilité du FEC et la nomenclature des comptes.",
            )
        )
    if not ctx.fy_closed:
        out.append(
            _a(
                "FY_OPEN",
                "warning",
                "Exercice non clôturé",
                "L'exercice n'est pas clôturé : le fichier reflète les "
                "écritures validées à la date de génération, avant les éventuelles opérations d'inventaire restantes (art. 2).",
                "Générer le fichier définitif après l'inventaire et la clôture.",
            )
        )
    pending_total = sum(ctx.pending.values())
    if pending_total:
        detail = ", ".join(f"{n} {PENDING_LABELS.get(s, s)}" for s, n in sorted(ctx.pending.items()) if n)
        out.append(
            _a(
                "PENDING_ENTRIES",
                "warning",
                "Écritures non validées",
                f"{pending_total} écriture(s) de la période ne sont pas validées et ne sont pas reprises ({detail}).",
                "Valider ou rejeter ces écritures avant la génération définitive.",
            )
        )
    return out


def _numbering_controls(lines: list[FecLine], ctx: FecContext) -> list[Anomaly]:
    out: list[Anomaly] = []
    seqs: dict[str, list[int]] = defaultdict(list)
    for e in ctx.fy_entries:
        if e.sequence_no:
            seqs[e.journal_code].append(e.sequence_no)
    for jcode, ns in sorted(seqs.items()):
        counts: dict[int, int] = defaultdict(int)
        for n in ns:
            counts[n] += 1
        dups = sorted(n for n, c in counts.items() if c > 1)
        if dups:
            out.append(
                _a(
                    "NUMBER_DUPLICATE",
                    "blocking",
                    "Numérotation",
                    f"Journal {jcode} : numéro(s) en double {dups[:10]}.",
                    "Signaler l'incident : la numérotation est attribuée par la base à la validation.",
                    journal=jcode,
                )
            )
        missing = sorted(set(range(1, max(ns) + 1)) - set(ns))
        if missing:
            out.append(
                _a(
                    "NUMBER_GAP",
                    "blocking",
                    "Rupture de numérotation",
                    f"Journal {jcode} : numéro(s) séquentiel(s) manquant(s) {missing[:10]}{' …' if len(missing) > 10 else ''} "
                    "(art. 5 : numéro séquentiel continu).",
                    "Rechercher les écritures manquantes ; aucune renumérotation automatique n'est faite.",
                    journal=jcode,
                )
            )
    # Écritures de report : présentes, et portant les premiers numéros (art. 2 et 5)
    reports = [e for e in ctx.fy_entries if e.origin == "opening"]
    others = [e for e in ctx.fy_entries if e.origin != "opening"]
    if ctx.has_previous_fy and ctx.period_start == ctx.fy_start and lines and not reports:
        out.append(
            _a(
                "REPORT_MISSING",
                "blocking",
                "Écritures de report absentes",
                "Aucune écriture de reprise des soldes "
                "de l'exercice antérieur n'est validée, alors qu'un exercice précédent existe (art. 2).",
                "Passer et valider les écritures de report en tête de l'exercice.",
            )
        )
    if reports and others:
        for jcode in sorted({e.journal_code for e in reports}):
            max_rep = max((e.sequence_no or 0) for e in reports if e.journal_code == jcode)
            first_other = min(((e.sequence_no or 0) for e in others if e.journal_code == jcode), default=None)
            if first_other is not None and first_other < max_rep:
                out.append(
                    _a(
                        "REPORT_NOT_FIRST",
                        "blocking",
                        "Rang des écritures de report",
                        f"Journal {jcode} : des écritures "
                        "ordinaires portent des numéros inférieurs à ceux des écritures de report (art. 5 : les écritures "
                        "de reprise portent les premiers numéros).",
                        "Les numéros validés ne sont pas modifiables : passer les écritures de report avant toute autre "
                        "écriture du journal.",
                        journal=jcode,
                    )
                )
        if min(_utc(e.validated_at) for e in others) < max(_utc(e.validated_at) for e in reports):
            out.append(
                _a(
                    "REPORT_NOT_FIRST_IN_FILE",
                    "blocking",
                    "Rang des écritures de report",
                    "Des écritures ordinaires ont "
                    "été validées avant les écritures de report : dans l'ordre chronologique de validation (art. 2), les "
                    "écritures de report ne viennent pas en tête du fichier.",
                    "Valider les écritures de report avant toute autre écriture de l'exercice.",
                )
            )
    return out


def _line_controls(lines: list[FecLine], ctx: FecContext) -> list[Anomaly]:
    out: list[Anomaly] = []
    seen: set[str] = set()
    by_entry: dict[str, list[FecLine]] = defaultdict(list)
    for ln in lines:
        by_entry[ln.entry_id].append(ln)
        if ln.line_id in seen:
            out.append(
                _a("DUPLICATE_LINE", "blocking", "Doublon", "Ligne d'écriture reprise deux fois.", "Signaler l'incident.", ln)
            )
        seen.add(ln.line_id)
        if not ln.journal_code or not (ln.journal_label or "").strip():
            out.append(
                _a(
                    "JOURNAL_MISSING",
                    "blocking",
                    "Journal",
                    "Code ou libellé du journal absent (champs 1 et 2).",
                    "Compléter le journal dans le paramétrage.",
                    ln,
                )
            )
        if not ln.number or not ln.sequence_no:
            out.append(
                _a(
                    "NUMBER_MISSING",
                    "blocking",
                    "Numéro d'écriture",
                    "Écriture validée sans numéro définitif (champ 3).",
                    "Signaler l'incident.",
                    ln,
                )
            )
        if not (ctx.fy_start <= ln.entry_date <= ctx.fy_end):
            out.append(
                _a(
                    "DATE_OUT_OF_FY",
                    "blocking",
                    "Date d'écriture",
                    "Date de l'écriture hors de l'exercice.",
                    "Signaler l'incident.",
                    ln,
                )
            )
        if not re.fullmatch(r"[0-9]{3}[0-9A-Za-z]*", ln.account or "") or not ln.chart_account:
            out.append(
                _a(
                    "ACCOUNT_INVALID",
                    "blocking",
                    "Compte",
                    "Numéro de compte dont les trois premiers caractères ne sont "
                    "pas des chiffres du plan SYSCOHADA, ou compte non rattaché au plan du référentiel (champ 5).",
                    "Rattacher le compte au plan comptable du référentiel.",
                    ln,
                )
            )
        if not (ln.account_label or "").strip():
            out.append(
                _a(
                    "ACCOUNT_LABEL_MISSING",
                    "blocking",
                    "Libellé du compte",
                    "Compte sans intitulé (champ 6).",
                    "Compléter l'intitulé du compte dans le plan comptable.",
                    ln,
                )
            )
        elif ln.chart_account == ln.account and ln.chart_label and ln.account_label.strip() != ln.chart_label.strip():
            out.append(
                _a(
                    "ACCOUNT_LABEL_NOMENCLATURE",
                    "warning",
                    "Nomenclature SYSCOHADA",
                    f"L'intitulé « {ln.account_label} » "
                    f"diffère de celui du plan SYSCOHADA (« {ln.chart_label} ») pour le même numéro (champ 6).",
                    "Vérifier l'intitulé du compte dans le plan comptable de l'entreprise.",
                    ln,
                )
            )
        if not (ln.piece_ref or "").strip():
            out.append(
                _a(
                    "PIECE_REF_MISSING",
                    "blocking",
                    "Pièce justificative",
                    "Référence de la pièce justificative absente (champ 9, obligatoire).",
                    REENTER,
                    ln,
                )
            )
        if ln.piece_date is None:
            out.append(
                _a(
                    "PIECE_DATE_MISSING",
                    "blocking",
                    "Date de la pièce",
                    "Date de la pièce justificative absente (champ 10, obligatoire).",
                    REENTER,
                    ln,
                )
            )
        if not lib_ecriture(ln):
            out.append(_a("LABEL_MISSING", "blocking", "Libellé", "Ligne sans libellé (champ 11).", REENTER, ln))
        if (ln.debit > 0) == (ln.credit > 0) or ln.debit < 0 or ln.credit < 0:
            out.append(
                _a(
                    "AMOUNT_INVALID",
                    "blocking",
                    "Montants",
                    "La ligne doit porter un seul montant, positif, au débit ou au crédit (champs 12 et 13).",
                    "Signaler l'incident.",
                    ln,
                )
            )
        if ln.validated_at is None:
            out.append(
                _a(
                    "VALIDATION_DATE_MISSING",
                    "blocking",
                    "Date de validation",
                    "Écriture sans date de validation (champ 16).",
                    "Signaler l'incident.",
                    ln,
                )
            )
        if ln.requires_third_party and not ln.aux_code:
            out.append(
                _a("AUX_MISSING", "blocking", "Compte auxiliaire", "Compte collectif sans tiers sur la ligne.", REENTER, ln)
            )
        if ln.aux_code and not (ln.aux_label or "").strip():
            out.append(
                _a(
                    "AUX_LABEL_MISSING",
                    "warning",
                    "Compte auxiliaire",
                    "Tiers sans nom (champ 8).",
                    "Compléter le nom du tiers.",
                    ln,
                )
            )
        if (ln.currency is None) != (ln.currency_amount is None):
            out.append(
                _a(
                    "CURRENCY_INCOMPLETE",
                    "blocking",
                    "Devise",
                    "Devise sans montant en devise, ou l'inverse (champs 17 et 18).",
                    "Signaler l'incident.",
                    ln,
                )
            )
        if ln.lettering_code and ln.lettering_date is None:
            out.append(
                _a(
                    "LETTERING_DATE_MISSING",
                    "warning",
                    "Lettrage",
                    "Ligne lettrée sans date de lettrage (champ 15).",
                    "Signaler l'incident.",
                    ln,
                )
            )
    for entry_lines in by_entry.values():
        d = sum((ln.debit for ln in entry_lines), Decimal(0))
        c = sum((ln.credit for ln in entry_lines), Decimal(0))
        if d != c:
            out.append(
                _a(
                    "ENTRY_UNBALANCED",
                    "blocking",
                    "Équilibre",
                    f"Écriture déséquilibrée (débit {fmt_amount(d)}, crédit {fmt_amount(c)}).",
                    "Signaler l'incident.",
                    entry_lines[0],
                )
            )
    return out


def data_controls(lines: list[FecLine], ctx: FecContext) -> list[Anomaly]:
    """Contrôles portant sur les données comptables (indépendants du format choisi)."""
    return _source_controls(lines, ctx) + _numbering_controls(lines, ctx) + _line_controls(lines, ctx)


def format_controls(lines: list[FecLine], opts: FecOptions) -> list[Anomaly]:
    """Contrôles dépendant du format : champs de trésorerie, valeurs obligatoires, jeu de caractères, séparateurs."""
    out: list[Anomaly] = []
    if opts.accounting_type == "cash":
        out.append(
            _a(
                "CASH_DATA_UNAVAILABLE",
                "blocking",
                "Comptabilité de trésorerie",
                "Les champs obligatoires Date Règlement et Mode Règlement (art. 5, champs 19 et 20) ne sont pas tenus par "
                "KOFINEX : ils ne peuvent pas être renseignés sans inventer de données.",
                "Utiliser la comptabilité d'engagement, ou produire le FEC depuis le logiciel qui tient ces informations.",
            )
        )
    codec, sep = ENCODINGS.get(opts.encoding), SEPARATORS.get(opts.field_separator)
    if codec is None or sep is None:
        return out
    reported: set[tuple[str, str, str]] = set()
    cash_names = set(CASH_FIELDS)
    for ln in lines:
        for spec_, value in zip(opts.specs, row(ln, opts), strict=True):
            fname = spec_.name
            if spec_.mandatory and not value and fname not in cash_names and (ln.entry_id, fname, "req") not in reported:
                reported.add((ln.entry_id, fname, "req"))
                out.append(
                    _a(
                        "MANDATORY_EMPTY",
                        "blocking",
                        "Valeur obligatoire",
                        f"La zone {fname} est obligatoire (art. 5) et serait vide.",
                        REENTER,
                        ln,
                    )
                )
            if (sep in value or "\r" in value or "\n" in value) and (ln.entry_id, fname, "sep") not in reported:
                reported.add((ln.entry_id, fname, "sep"))
                out.append(
                    _a(
                        "SEPARATOR_IN_VALUE",
                        "blocking",
                        "Séparateur dans une zone",
                        f"La zone {fname} contient une tabulation ou un saut de ligne : la structure du fichier serait faussée.",
                        "Corriger le libellé à la source (compte, tiers ou journal) ; l'écriture n'est pas modifiée "
                        "automatiquement.",
                        ln,
                    )
                )
            try:
                value.encode(codec)
            except UnicodeEncodeError:
                if (ln.entry_id, fname, "enc") not in reported:
                    reported.add((ln.entry_id, fname, "enc"))
                    out.append(
                        _a(
                            "ENCODING",
                            "blocking",
                            "Jeu de caractères",
                            f"La zone {fname} contient un caractère non représentable en {ENCODING_LABELS[opts.encoding]}.",
                            "Choisir ISO 8859-15 ; aucune translittération automatique n'est faite.",
                            ln,
                        )
                    )
    return out


# Anomalies qui empêchent de produire un fichier, même de travail (nom ou contenu impossibles à écrire fidèlement)
FATAL = {"IFU_MISSING", "IFU_FORMAT", "NO_ENTRIES", "SOURCE_IMPORTED_ONLY", "ENCODING", "SEPARATOR_IN_VALUE"}


@dataclass
class CheckResult:
    anomalies: list[Anomaly]
    lines: list[FecLine]

    @property
    def blocking(self) -> int:
        return sum(1 for a in self.anomalies if a.severity == "blocking")

    @property
    def warnings(self) -> int:
        return sum(1 for a in self.anomalies if a.severity == "warning")

    @property
    def fatal(self) -> list[Anomaly]:
        return [a for a in self.anomalies if a.code in FATAL]

    @property
    def compliance(self) -> str:
        if self.blocking:
            return "non_compliant"
        return "compliant" if SPEC_CONFIRMED else "spec_pending"

    def entry_counts(self) -> dict:
        """Écritures de la période et écritures éligibles (sans anomalie bloquante qui leur soit propre)."""
        entries = {ln.entry_id for ln in self.lines}
        blocked = {a.entry_id for a in self.anomalies if a.severity == "blocking" and a.entry_id}
        return {"entries": len(entries), "eligible": len(entries - blocked), "lines": len(self.lines)}


def check(lines: list[FecLine], ctx: FecContext, opts: FecOptions | None = None) -> CheckResult:
    an = data_controls(lines, ctx)
    if opts is not None:
        an += format_controls(lines, opts)
    rank = {"blocking": 0, "warning": 1}
    an.sort(key=lambda a: (rank[a.severity], a.entry_date or date.min, a.journal or "", a.number or "", a.code))
    return CheckResult(an, lines)


# ------------------------------------------------------------------------------------------------------------ rendu
@dataclass(frozen=True)
class FilePart:
    part: int | None
    filename: str
    content: bytes
    line_count: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def render(lines: list[FecLine], opts: FecOptions, ifu: str, fy_end: date) -> list[FilePart]:
    """Fichier(s) plat(s) : une ligne par ligne d'écriture, champs dans l'ordre de l'article 5, sans ligne d'en-tête ni
    guillemets, chaque enregistrement terminé par le séparateur choisi. Fractionné seulement à la demande (art. 6)."""
    errs = opts.validate()
    if errs:
        raise ValueError(" ".join(errs))
    sep, eol, codec = SEPARATORS[opts.field_separator], RECORD_SEPARATORS[opts.record_separator], ENCODINGS[opts.encoding]
    records = [sep.join(row(ln, opts)) for ln in ordered(lines)]
    size = opts.max_lines_per_file
    chunks = [records] if not size or len(records) <= size else [records[i : i + size] for i in range(0, len(records), size)]
    single = len(chunks) == 1
    return [
        FilePart(
            None if single else i,
            filename(ifu, fy_end, opts.file_format, None if single else i),
            "".join(r + eol for r in chunk).encode(codec),
            len(chunk),
        )
        for i, chunk in enumerate(chunks, 1)
    ]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def global_sha256(parts: list[FilePart]) -> str:
    """Empreinte de l'ensemble du FEC : SHA-256 du contenu des fichiers mis bout à bout, dans l'ordre des parties."""
    h = hashlib.sha256()
    for p in parts:
        h.update(p.content)
    return h.hexdigest()


def documentation(opts: FecOptions, meta: dict) -> bytes:
    """Art. 7 : nom, description et signification de chaque champ, jeu de caractères, caractère de séparation des
    champs et des enregistrements. Archivée avec le fichier."""
    out = [
        "DOCUMENTATION DU FICHIER DES ÉCRITURES COMPTABLES (FEC) — RÉPUBLIQUE DU BÉNIN",
        "Arrêté n° 1085/MEF/CAB/SGM/DGI/DLC/159SGG20 du 23 avril 2020 (article 7)",
        "",
        f"Entreprise                       : {meta.get('company', '')}",
        f"IFU                              : {meta.get('ifu', '')}",
        f"Exercice                         : {meta.get('fiscal_year', '')} (date de clôture {meta.get('fy_end', '')})",
        f"Période                          : du {meta.get('period_start', '')} au {meta.get('period_end', '')}",
        f"Généré le                        : {meta.get('generated_at', '')} par {meta.get('generated_by', '')}",
        f"Type de comptabilité             : {'trésorerie (champs 19 à 21)' if opts.accounting_type == 'cash' else 'engagement'}",
        "",
        "FICHIERS",
    ]
    for p in meta.get("parts", []):
        out.append(f"  {p['filename']} : {p['line_count']} enregistrement(s), {p['size_bytes']} octets, SHA-256 {p['sha256']}")
    out += [
        f"Empreinte SHA-256 de l'ensemble  : {meta.get('sha256', '')} (contenu des fichiers mis bout à bout, dans l'ordre)",
        "",
        "FORMAT (article 4)",
        f"Format                           : fichier plat {opts.file_format.upper()}, organisation séquentielle",
        f"Jeu de caractères                : {ENCODING_LABELS[opts.encoding]}",
        f"Séparateur des champs            : {SEPARATOR_LABELS[opts.field_separator]}",
        f"Séparateur des enregistrements   : {RECORD_LABELS[opts.record_separator]}",
        "Enregistrements                  : une ligne par ligne d'écriture comptable, sans ligne d'en-tête",
        "Zones                            : longueur variable, sans cadrage ni remplissage, sans guillemets",
        "Valeurs numériques               : en caractères, base décimale, signe en premier caractère, virgule décimale,",
        "                                   deux décimales, aucun séparateur de milliers",
        "Dates                            : AAAAMMJJ, sans séparateur",
        "Ordre                            : chronologique de validation, puis journal, numéro et rang de ligne (article 2)",
        "Écritures reprises               : écritures validées (y compris extournées et leurs extournes) et écritures de",
        "                                   report ; ni écritures non validées, ni grand livre importé",
        "Écritures de report              : LibEcriture = REPORT",
        "",
        "CHAMPS (article 5) — n°, nom, information portée, type, valeur obligatoire, format, origine dans KOFINEX",
    ]
    for f in opts.specs:
        out.append(
            f"{f.order:>2}. {f.name} — {f.information} — {f.type} — {'OUI' if f.mandatory else 'NON'}"
            f"{' — ' + f.value_format if f.value_format else ''} — {f.kofinex_source}"
        )
    out += ["", f"Référence : {SPEC_VERSION}. Générateur : {GENERATOR_VERSION}."]
    if UNCONFIRMED:
        out.append("Points réglementaires restant à confirmer :")
        out += [f"  - {u['label']} : {u['detail']}" for u in UNCONFIRMED]
    return ("\r\n".join(out) + "\r\n").encode("utf-8")


def anomalies_csv(anomalies: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(
        ["Gravité", "Numéro de l'écriture", "Date", "Journal", "Compte", "Nature", "Description", "Action recommandée", "Code"]
    )
    for a in anomalies:
        w.writerow(
            [
                {"blocking": "Bloquante", "warning": "Avertissement"}[a["severity"]],
                a.get("number") or "",
                a.get("entry_date") or "",
                a.get("journal") or "",
                a.get("account") or "",
                a["nature"],
                a["description"],
                a["action"],
                a["code"],
            ]
        )
    return buf.getvalue().encode("utf-8-sig")


def spec() -> dict:
    def fs(f: FieldSpec) -> dict:
        return {
            "order": f.order,
            "name": f.name,
            "information": f.information,
            "type": f.type,
            "mandatory": f.mandatory,
            "format": f.value_format,
            "source": f.kofinex_source,
        }

    return {
        "version": SPEC_VERSION,
        "confirmed": SPEC_CONFIRMED,
        "fields": [fs(f) for f in FIELD_SPECS],
        "cash_fields": [fs(f) for f in CASH_FIELD_SPECS],
        "formats": list(FORMATS),
        "encodings": ENCODING_LABELS,
        "separators": SEPARATOR_LABELS,
        "record_separators": RECORD_LABELS,
        "filename_pattern": "FEC_IFU_AAAAMMJJ",
        "split_pattern": "FEC_IFU_AAAAMMJJ_X",
        "applied": list(APPLIED),
        "unconfirmed": list(UNCONFIRMED),
    }
