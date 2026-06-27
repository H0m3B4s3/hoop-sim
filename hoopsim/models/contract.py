"""Player contracts.

A contract is a list of annual salaries (index 0 == the current season). Options and
guarantees are tracked per year. When a season ends the current year is dropped; an empty
contract means the player reaches free agency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Contract:
    salaries: List[int] = field(default_factory=list)          # dollars per remaining year
    guaranteed: List[bool] = field(default_factory=list)       # parallel to salaries
    # year_index -> "player" | "team"; that year is an option to be decided in the offseason.
    options: Dict[int, str] = field(default_factory=dict)
    no_trade: bool = False
    signed_year: int = 0            # season year the deal was signed
    years_with_team: int = 0        # for Bird rights (re-signing own FAs over the cap)
    is_rookie_scale: bool = False

    # -- queries ------------------------------------------------------------
    @property
    def years_remaining(self) -> int:
        return len(self.salaries)

    @property
    def is_expiring(self) -> bool:
        return self.years_remaining <= 1

    @property
    def current_salary(self) -> int:
        return self.salaries[0] if self.salaries else 0

    @property
    def total_remaining(self) -> int:
        return sum(self.salaries)

    @property
    def has_bird_rights(self) -> bool:
        return self.years_with_team >= 3

    @property
    def has_early_bird_rights(self) -> bool:
        return self.years_with_team >= 2

    def option_for_year(self, year_index: int) -> Optional[str]:
        return self.options.get(year_index)

    # -- mutation -----------------------------------------------------------
    def advance_year(self) -> None:
        """Drop the just-completed season; shift option indices down by one."""
        if self.salaries:
            self.salaries.pop(0)
            if self.guaranteed:
                self.guaranteed.pop(0)
        self.years_with_team += 1
        self.options = {idx - 1: kind for idx, kind in self.options.items() if idx - 1 >= 0}

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "salaries": list(self.salaries),
            "guaranteed": list(self.guaranteed),
            "options": {str(k): v for k, v in self.options.items()},
            "no_trade": self.no_trade,
            "signed_year": self.signed_year,
            "years_with_team": self.years_with_team,
            "is_rookie_scale": self.is_rookie_scale,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Contract":
        return cls(
            salaries=list(d.get("salaries", [])),
            guaranteed=list(d.get("guaranteed", [])),
            options={int(k): v for k, v in d.get("options", {}).items()},
            no_trade=d.get("no_trade", False),
            signed_year=d.get("signed_year", 0),
            years_with_team=d.get("years_with_team", 0),
            is_rookie_scale=d.get("is_rookie_scale", False),
        )

    @classmethod
    def free_agent(cls) -> "Contract":
        return cls()


def flat_contract(annual: int, years: int, signed_year: int, *,
                  rookie_scale: bool = False, years_with_team: int = 0) -> Contract:
    """Build a simple fully-guaranteed flat-salary contract."""
    return Contract(
        salaries=[annual] * years,
        guaranteed=[True] * years,
        signed_year=signed_year,
        is_rookie_scale=rookie_scale,
        years_with_team=years_with_team,
    )
