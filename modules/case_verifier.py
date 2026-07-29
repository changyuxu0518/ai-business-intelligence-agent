from __future__ import annotations

AI_PROVIDERS = ("openai", "anthropic", "deepmind", "nvidia", "hugging face", "meta ai")
ADOPTION = ("deployed", "implemented", "adopted", "launched", "uses", "integrated")
SCENARIOS = ("marketing", "advertising", "customer service", "sales", "personalization", "shopping", "operations", "workflow", "supply chain")
WEAK = ("exploring", "future", "potential", "could", "might")


def verify_discovery_candidates(candidates: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    verified = []
    for candidate in candidates:
        text = f"{candidate.get('title', '')} {candidate.get('summary', '')}".lower()
        provider = any(term in text for term in AI_PROVIDERS)
        action = any(term in text for term in ADOPTION)
        scenario = any(term in text for term in SCENARIOS)
        weak = any(term in text for term in WEAK)
        score = 5 if action and scenario and not provider and not weak else 3 if (action or scenario) and not provider else 1
        candidate["verification_score"] = str(score)
        candidate["company_role"] = "enterprise_adopter" if score >= 4 else "ai_provider" if provider else "unknown"
        candidate["candidate_category"] = "enterprise_application" if score >= 4 else "ai_industry" if provider else "business_trend"
        if score >= 4:
            verified.append(candidate)
    return verified, {"discovery_candidates": len(candidates), "verified_enterprise_cases": len(verified), "rejected_trend_articles": len(candidates) - len(verified)}
