"""Lot ingestion and normalization (spec §13.2).

Canonical schema:
  account,symbol,lot_id,quantity,acquired_date,cost_basis,current_price,as_of,asset_class,is_ira

Validation is total: every malformed row is reported, together (spec §15.2).
"""

from __future__ import annotations

import csv
import datetime as _dt
from decimal import Decimal, InvalidOperation
from pathlib import Path

from platformdirs import user_data_dir

from ouch.errors import ValidationInputError
from ouch.model.money import Money
from ouch.model.portfolio import Lot

REQUIRED_COLUMNS = ["account", "symbol", "lot_id", "quantity", "acquired_date",
                    "cost_basis", "current_price", "as_of"]
OPTIONAL_COLUMNS = ["asset_class", "is_ira"]

_TRUE = {"1", "true", "yes", "y"}
_FALSE = {"0", "false", "no", "n", ""}


def portfolio_path() -> Path:
    return Path(user_data_dir("ouch")) / "portfolio" / "lots.csv"


def _parse_row(row: dict[str, str], line: int,
               errors: list[str]) -> Lot | None:
    def err(msg: str) -> None:
        errors.append(f"  line {line}: {msg}")

    for col in REQUIRED_COLUMNS:
        if not (row.get(col) or "").strip():
            err(f"missing required column '{col}'")
            return None
    try:
        quantity = Decimal(row["quantity"].replace(",", ""))
        if quantity <= 0:
            err("quantity must be positive")
            return None
    except InvalidOperation:
        err(f"quantity '{row['quantity']}' is not a number")
        return None
    try:
        cost_basis = Money(row["cost_basis"].replace(",", "").replace("$", ""))
        price = Money(row["current_price"].replace(",", "").replace("$", ""))
    except (InvalidOperation, TypeError, Exception):
        err("cost_basis/current_price must be numbers")
        return None
    try:
        acquired = _dt.date.fromisoformat(row["acquired_date"].strip())
        as_of = _dt.date.fromisoformat(row["as_of"].strip())
    except ValueError as e:
        err(f"bad date: {e} (use YYYY-MM-DD)")
        return None
    if acquired > as_of:
        err(f"acquired_date {acquired} is after as_of {as_of}")
        return None
    ira_raw = (row.get("is_ira") or "").strip().lower()
    if ira_raw in _TRUE:
        is_ira = True
    elif ira_raw in _FALSE:
        is_ira = False
    else:
        err(f"is_ira '{row['is_ira']}' is not a boolean")
        return None
    return Lot(
        account=row["account"].strip(), symbol=row["symbol"].strip().upper(),
        lot_id=row["lot_id"].strip(), quantity=quantity,
        acquired_date=acquired, cost_basis=cost_basis, current_price=price,
        as_of=as_of, asset_class=(row.get("asset_class") or "").strip(),
        is_ira=is_ira)


def parse_lots_csv(path: Path) -> list[Lot]:
    if not path.is_file():
        raise ValidationInputError(
            f"lot file not found: {path}",
            hint="expected the canonical CSV schema — see `ouch harvest import --help`")
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValidationInputError(f"{path} is empty")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValidationInputError(
                f"{path}: missing columns: {', '.join(missing)}",
                hint="canonical header: " + ",".join(REQUIRED_COLUMNS
                                                    + OPTIONAL_COLUMNS))
        errors: list[str] = []
        lots: list[Lot] = []
        seen_ids: dict[str, int] = {}
        for i, row in enumerate(reader, start=2):
            lot = _parse_row(row, i, errors)
            if lot is None:
                continue
            if lot.lot_id in seen_ids:
                errors.append(f"  line {i}: duplicate lot_id '{lot.lot_id}' "
                              f"(first seen line {seen_ids[lot.lot_id]})")
                continue
            seen_ids[lot.lot_id] = i
            lots.append(lot)
    if errors:
        raise ValidationInputError(
            f"lot file failed validation ({len(errors)} error"
            f"{'s' if len(errors) != 1 else ''}) — {path}\n" + "\n".join(errors))
    if not lots:
        raise ValidationInputError(f"{path} contains no lots")
    return lots


def save_portfolio(lots: list[Lot], path: Path | None = None) -> Path:
    target = path or portfolio_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)
        for lot in lots:
            writer.writerow([
                lot.account, lot.symbol, lot.lot_id, str(lot.quantity),
                lot.acquired_date.isoformat(), str(lot.cost_basis.amount),
                str(lot.current_price.amount), lot.as_of.isoformat(),
                lot.asset_class, "true" if lot.is_ira else "false"])
    return target


def load_portfolio(path: Path | None = None) -> list[Lot]:
    target = path or portfolio_path()
    if not target.is_file():
        raise ValidationInputError(
            "no portfolio on file",
            hint="run `ouch harvest import LOTS.csv` first")
    return parse_lots_csv(target)
