from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.models.analysis import AnalysisResult
from app.models.market import MarketResearchResult


OUTLIER_RISK_FLAG = "unreliable_outlier_sold_comps"
ESTIMATE_RISK_FLAG = "estimated_value_conflicts_with_sold_comps"
LOWER_COMP_RISK_FLAG = "valuation_capped_to_lower_sold_comps"


@dataclass(frozen=True)
class SoldCompSanityCheck:
    unreliable: bool
    reason: str | None = None
    median_price: float | None = None
    largest_gap_ratio: float | None = None
    low_cluster: tuple[float, ...] = ()
    high_cluster: tuple[float, ...] = ()


@dataclass(frozen=True)
class ConservativeSoldCompValue:
    value: float
    max_bid_cap: float
    bid_fraction: float
    lower_comp_prices: tuple[float, ...]
    spread_ratio: float
    reason: str


def check_sold_comp_sanity(
    prices: list[float],
    estimated_market_value: float | None = None,
    max_cluster_gap_ratio: float = 3.0,
    max_estimate_to_median_ratio: float = 1.5,
) -> SoldCompSanityCheck:
    clean_prices = sorted(price for price in prices if price > 0)
    if len(clean_prices) < 3:
        return SoldCompSanityCheck(
            unreliable=False,
            median_price=round(median(clean_prices), 2) if clean_prices else None,
        )

    median_price = float(median(clean_prices))
    largest_gap_ratio = 1.0
    largest_gap_index: int | None = None
    for index in range(1, len(clean_prices)):
        previous = clean_prices[index - 1]
        current = clean_prices[index]
        if previous <= 0:
            continue
        gap_ratio = current / previous
        if gap_ratio > largest_gap_ratio:
            largest_gap_ratio = gap_ratio
            largest_gap_index = index

    if largest_gap_index is not None and largest_gap_ratio >= max_cluster_gap_ratio:
        low_cluster = tuple(clean_prices[:largest_gap_index])
        high_cluster = tuple(clean_prices[largest_gap_index:])
        return SoldCompSanityCheck(
            unreliable=True,
            reason=(
                "Recent sold prices split into incompatible clusters "
                f"(${low_cluster[0]:.2f}-${low_cluster[-1]:.2f} and "
                f"${high_cluster[0]:.2f}-${high_cluster[-1]:.2f})."
            ),
            median_price=round(median_price, 2),
            largest_gap_ratio=round(largest_gap_ratio, 2),
            low_cluster=low_cluster,
            high_cluster=high_cluster,
        )

    if median_price > 0 and estimated_market_value is not None:
        estimate_ratio = estimated_market_value / median_price
        if estimate_ratio > max_estimate_to_median_ratio:
            return SoldCompSanityCheck(
                unreliable=True,
                reason=(
                    "Estimated market value is far above the median recent sold price "
                    f"(${estimated_market_value:.2f} vs ${median_price:.2f})."
                ),
                median_price=round(median_price, 2),
            )

    return SoldCompSanityCheck(
        unreliable=False,
        median_price=round(median_price, 2),
        largest_gap_ratio=round(largest_gap_ratio, 2),
    )


def conservative_sold_comp_value(prices: list[float]) -> ConservativeSoldCompValue | None:
    clean_prices = tuple(sorted(price for price in prices if price > 0))
    if not clean_prices:
        return None

    lower_count = max(1, (len(clean_prices) + 1) // 2)
    lower_comp_prices = clean_prices[:lower_count]
    value = round(float(median(lower_comp_prices)), 2)
    spread_ratio = round(clean_prices[-1] / clean_prices[0], 2) if clean_prices[0] > 0 else 1.0
    bid_fraction = 0.70 if spread_ratio >= 2.0 else 0.80
    max_bid_cap = round(value * bid_fraction, 2)
    reason = (
        "Using lower sold comps instead of median/top-of-range comps "
        f"because bidding should preserve downside margin. Lower comps={list(lower_comp_prices)}, "
        f"spread_ratio={spread_ratio}, bid_fraction={bid_fraction:.2f}."
    )
    return ConservativeSoldCompValue(
        value=value,
        max_bid_cap=max_bid_cap,
        bid_fraction=bid_fraction,
        lower_comp_prices=lower_comp_prices,
        spread_ratio=spread_ratio,
        reason=reason,
    )


def sanitize_market_research_result(result: MarketResearchResult) -> MarketResearchResult:
    check = check_sold_comp_sanity(
        result.recent_sold_prices,
        estimated_market_value=result.estimated_market_value,
    )
    if not check.unreliable:
        conservative_value = conservative_sold_comp_value(result.recent_sold_prices)
        if (
            conservative_value is None
            or result.estimated_market_value is None
            or result.estimated_market_value <= conservative_value.value
        ):
            return result

        warnings = list(dict.fromkeys([*result.warnings, LOWER_COMP_RISK_FLAG]))
        evidence_summary = (
            f"{result.evidence_summary} Conservative valuation override: "
            f"{conservative_value.reason} Estimated market value was capped from "
            f"${result.estimated_market_value:.2f} to ${conservative_value.value:.2f}."
        )
        return result.model_copy(
            update={
                "estimated_market_value": conservative_value.value,
                "warnings": warnings,
                "evidence_summary": evidence_summary,
            }
        )

    warnings = list(dict.fromkeys([*result.warnings, OUTLIER_RISK_FLAG]))
    evidence_summary = (
        f"{result.evidence_summary} Safety check: {check.reason} "
        "Clearing estimated market value so downstream analysis does not anchor to mismatched comps."
    )
    return result.model_copy(
        update={
            "estimated_market_value": None,
            "warnings": warnings,
            "evidence_summary": evidence_summary,
        }
    )


def sanitize_analysis_result(analysis: AnalysisResult) -> AnalysisResult:
    check = check_sold_comp_sanity(
        analysis.recent_sold_prices,
        estimated_market_value=analysis.estimated_market_value,
    )
    if not check.unreliable:
        conservative_value = conservative_sold_comp_value(analysis.recent_sold_prices)
        if conservative_value is None:
            return analysis

        should_cap_value = (
            analysis.estimated_market_value is not None
            and analysis.estimated_market_value > conservative_value.value
        )
        should_cap_bid = (
            analysis.recommended_max_bid is not None
            and analysis.recommended_max_bid > conservative_value.max_bid_cap
        )
        if not should_cap_value and not should_cap_bid:
            return analysis

        risk_flags = list(dict.fromkeys([*analysis.risk_flags, LOWER_COMP_RISK_FLAG]))
        capped_market_value = (
            conservative_value.value
            if should_cap_value
            else analysis.estimated_market_value
        )
        capped_max_bid = (
            min(
                value
                for value in [
                    analysis.recommended_max_bid,
                    conservative_value.max_bid_cap,
                ]
                if value is not None
            )
            if analysis.recommended_max_bid is not None
            else conservative_value.max_bid_cap
        )
        reasoning = (
            f"{analysis.reasoning} Conservative valuation override: {conservative_value.reason} "
            f"Market value capped to ${capped_market_value:.2f}; max bid capped to "
            f"${capped_max_bid:.2f}."
        )
        market_evidence = analysis.market_evidence or ""
        market_evidence = (
            f"{market_evidence} Conservative valuation override: {conservative_value.reason}".strip()
        )
        return analysis.model_copy(
            update={
                "estimated_market_value": capped_market_value,
                "recommended_max_bid": capped_max_bid,
                "reasoning": reasoning,
                "risk_flags": risk_flags,
                "market_evidence": market_evidence,
            }
        )

    risk_flags = list(dict.fromkeys([*analysis.risk_flags, OUTLIER_RISK_FLAG, ESTIMATE_RISK_FLAG]))
    reasoning = (
        f"{analysis.reasoning} Safety override: {check.reason} "
        "The bid recommendation was removed because the comp set is likely mismatched or too noisy."
    )
    market_evidence = analysis.market_evidence or ""
    market_evidence = (
        f"{market_evidence} Safety check: {check.reason}".strip()
        if check.reason
        else market_evidence
    )
    return analysis.model_copy(
        update={
            "should_bid": False,
            "confidence": min(analysis.confidence, 0.55),
            "estimated_market_value": None,
            "recommended_max_bid": None,
            "trend_outlook": "uncertain",
            "reasoning": reasoning,
            "risk_flags": risk_flags,
            "market_evidence": market_evidence,
        }
    )
