# Audit Report Schema

Extends the contest's minimum required schema. Required fields (per the brief) are marked **(required)**; everything else is an extension.

```json
{
  "site": "example.com",                      // (required)
  "audited_at": "2026-09-20T14:32:00Z",        // (required, ISO-8601)
  "run_metadata": {
    "depth": "standard",
    "pages_audited": ["https://example.com", "https://example.com/pricing"],
    "capabilities_available": {
      "headless_browser": false,
      "web_search": true,
      "python_execution": true
    }
  },
  "summary": {                                  // (required)
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 0                                    // extension field
  },
  "findings": [
    {
      "id": "F-001",                            // (required)
      "title": "No JSON-LD structured data on product pages",   // (required)
      "severity": "high",                       // (required)
      "category": "discoverability",            // extension: "discoverability" | "engagement"
      "affected_urls": ["https://example.com/products/widget"], // extension
      "confidence": "high",                     // extension: "high" | "medium" | "low"
      "evidence": "Crawled 12 product pages; 0/12 contain schema.org markup.", // (required)
      "suggested_action": {                     // (required)
        "summary": "Add Product/Offer JSON-LD to every product page.",
        "priority": "high",                     // (required)
        "effort": "low"                         // extension: "low" | "medium" | "high"
      }
    }
  ]
}
```

## Field notes

- `category`: which half of the Round-2 problem this addresses — `discoverability` (crawl-render-audit, freshness-corroboration) or `engagement` (engagement-audit).
- `confidence`: honest about measurement limits — render-gap findings without a headless browser, corroboration findings from a capped search sample, and load-time approximations should all be marked `medium` or `low`, not `high`.
- `effort`: separate from `priority`. A `high`-priority, `low`-effort fix (add a meta tag) should visibly outrank a `high`-priority, `high`-effort fix (rebuild rendering pipeline) in the order actions are presented, even though both are "high priority" — this is what lets a non-expert reader act on the report immediately.
- Findings should be ordered: `critical` → `high` → `medium` → `low`, and within a tier, lower `effort` first.
